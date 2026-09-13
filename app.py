from __future__ import annotations

import csv
import json
import os
import re
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from contracts import (
    AuditRecord,
    ContractValidationError,
    DiagnosisOutput,
    HumanFeedback,
    IncidentInput,
    RetrievalResult,
    contract_schema,
)
from provider import ProviderError, build_provider
from integrations.github_actions import GitHubActionsClient, GitHubActionsError


ROOT = Path(__file__).resolve().parent
STATIC_DIR = ROOT / "static"
DEFAULT_SOURCES_DIR = (
    ROOT.parent / "Proyecto Final" / "Fuentes_PoC_DevOps" / "poc_devops_sources"
)
SOURCES_DIR = Path(os.environ.get("MVP_SOURCES_DIR", str(DEFAULT_SOURCES_DIR)))
MAX_INPUT_CHARS = 30_000
MAX_BODY_BYTES = 100_000


SENSITIVE_PATTERNS = [
    (re.compile(r"(?i)(authorization\s*:\s*bearer\s+)[A-Za-z0-9._~+/=-]+"), r"\1[REDACTED]"),
    (re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._~+/=-]+"), r"\1[REDACTED]"),
    (re.compile(r"(?i)\b(password|passwd|pwd)\s*[:=]\s*[^\s,;]+"), r"\1=[REDACTED]"),
    (re.compile(r"(?i)\b(api[_-]?key|access[_-]?key|token|secret)\s*[:=]\s*[^\s,;]+"), r"\1=[REDACTED]"),
    (re.compile(r"-----BEGIN [^-]+ PRIVATE KEY-----.*?-----END [^-]+ PRIVATE KEY-----", re.S), "[PRIVATE_KEY_REDACTED]"),
    (re.compile(r"(?i)\b(aws_secret_access_key|client_secret)\s*[:=]\s*[^\s,;]+"), r"\1=[REDACTED]"),
]

INJECTION_PATTERNS = [
    re.compile(r"(?i)ignore\s+(all\s+)?previous\s+instructions"),
    re.compile(r"(?i)ignora\s+(todas\s+)?las\s+instrucciones"),
    re.compile(r"(?i)(reveal|show|print|expose|dime|muestra|revela).{0,80}(system prompt|secret|api key|password|token|clave)"),
    re.compile(r"(?i)(system prompt|system message|prompt del sistema).{0,40}(reveal|show|dime|muestra|print|copia)"),
    re.compile(r"(?i)you are now|ahora eres|actua como administrador"),
]

OUT_OF_SCOPE_PATTERNS = [
    re.compile(r"(?i)\b(elimina|borrar|borra|delete|reinicia|reiniciar|restart|apply|rollout|rollback|upgrade|scale|patch|ejecuta|execute)\b"),
    re.compile(r"(?i)\b(terraform\s+apply|kubectl\s+(delete|apply|rollout|scale|patch|edit|create)|helm\s+(upgrade|rollback|install))\b"),
    re.compile(r"(?i)\b(crea|crear|actualiza|actualizar)\s+(un\s+)?ticket\b"),
]

ERROR_PATTERNS = [
    "ImagePullBackOff",
    "ErrImagePull",
    "CrashLoopBackOff",
    "OOMKilled",
    "ProgressDeadlineExceeded",
    "BUILD FAILURE",
    "There are test failures",
    "Could not resolve dependencies",
    "Authentication failed",
    "Quality Gate",
    "no space left on device",
    "PVC Pending",
]

STOP_WORDS = {
    "para", "como", "desde", "este", "esta", "tiene", "tengo", "cuando", "donde",
    "debe", "deben", "puede", "pueden", "sobre", "entre", "ante", "con", "sin",
    "una", "uno", "los", "las", "del", "por", "que", "qué", "una", "mi", "no",
    "the", "and", "with", "from", "this", "that", "error", "incidente",
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def sanitize_text(value: str) -> str:
    result = value
    for pattern, replacement in SENSITIVE_PATTERNS:
        result = pattern.sub(replacement, result)
    return result


def detect_patterns(text: str, patterns: list[re.Pattern[str]]) -> list[str]:
    return [pattern.pattern for pattern in patterns if pattern.search(text)]


def tokenize(text: str) -> set[str]:
    words = re.findall(r"[a-zA-Z0-9À-ÿ][a-zA-Z0-9À-ÿ_.-]{2,}", text.lower())
    return {word for word in words if word not in STOP_WORDS}


def parse_front_matter(text: str) -> dict[str, str]:
    if not text.startswith("---"):
        return {}
    lines = text.splitlines()
    try:
        end = lines.index("---", 1)
    except ValueError:
        return {}
    values: dict[str, str] = {}
    for line in lines[1:end]:
        if ":" in line:
            key, value = line.split(":", 1)
            values[key.strip()] = value.strip()
    return values


@dataclass(frozen=True)
class KnowledgeDocument:
    source_id: str
    source_type: str
    text: str
    metadata: dict[str, str]


class Corpus:
    """Small, dependency-free retrievers for the authorized PoC corpus."""

    def __init__(self, sources_dir: Path):
        self.sources_dir = sources_dir
        self.technical: list[KnowledgeDocument] = []
        self.history: list[KnowledgeDocument] = []
        self.loaded_at = now_iso()
        self._load()

    def _load(self) -> None:
        knowledge_dir = self.sources_dir / "knowledge"
        if knowledge_dir.exists():
            for path in sorted(knowledge_dir.glob("*.md")):
                text = path.read_text(encoding="utf-8")
                metadata = parse_front_matter(text)
                source_id = metadata.get("doc_id") or path.name.split("_", 1)[0]
                self.technical.append(
                    KnowledgeDocument(source_id, "technical_kb", text, metadata)
                )

        csv_path = self.sources_dir / "jira_incidentes_normalizados.csv"
        if csv_path.exists():
            with csv_path.open(encoding="utf-8-sig", newline="") as handle:
                for row in csv.DictReader(handle):
                    source_id = row.get("key", "UNKNOWN")
                    text = "\n".join(
                        f"{key}: {value}" for key, value in row.items() if value
                    )
                    metadata = {
                        key: row.get(key, "")
                        for key in ("technology", "category", "environment", "affected_service")
                    }
                    self.history.append(
                        KnowledgeDocument(source_id, "jira_history", text, metadata)
                    )

    def retrieve(self, query: str, source_type: str, limit: int = 4) -> list[dict[str, Any]]:
        documents = self.technical if source_type == "technical_kb" else self.history
        query_tokens = tokenize(query)
        query_errors = [marker.lower() for marker in ERROR_PATTERNS if marker.lower() in query.lower()]
        scored: list[tuple[int, KnowledgeDocument]] = []
        for document in documents:
            doc_tokens = tokenize(document.text)
            overlap = len(query_tokens & doc_tokens)
            matching_errors = [marker for marker in query_errors if marker in document.text.lower()]
            # Con una firma de error explícita, no devolvemos documentos que
            # solo coinciden por palabras genéricas como "Kubernetes" o "UAT".
            if query_errors and not matching_errors:
                continue
            exact_bonus = 3 * len(matching_errors)
            if overlap or exact_bonus:
                scored.append((overlap + exact_bonus, document))
        scored.sort(key=lambda item: (-item[0], item[1].source_id))
        return [
            {
                "source_id": document.source_id,
                "source_type": document.source_type,
                "score": score,
                "excerpt": self._excerpt(document.text),
                "metadata": document.metadata,
            }
            for score, document in scored[:limit]
        ]

    @staticmethod
    def _excerpt(text: str, max_chars: int = 700) -> str:
        clean = re.sub(r"---.*?---", "", text, count=1, flags=re.S).strip()
        return clean if len(clean) <= max_chars else clean[:max_chars].rstrip() + "…"


class SecureLocalAgent:
    """A safe local vertical slice; no shell, network, or secret access."""

    def __init__(self, corpus: Corpus, provider: Any = None):
        self.corpus = corpus
        self.provider = provider

    def analyze_payload(self, payload: Any) -> dict[str, Any]:
        incident = IncidentInput.from_payload(payload)
        text = incident.to_text()
        return self.analyze(text, incident.source)

    def analyze(self, raw_input: str, source: str = "manual") -> dict[str, Any]:
        if not isinstance(raw_input, str) or not raw_input.strip():
            raise ValueError("El incidente debe contener texto.")
        if len(raw_input) > MAX_INPUT_CHARS:
            raise ValueError(f"El incidente supera el máximo de {MAX_INPUT_CHARS} caracteres.")

        sanitized = sanitize_text(raw_input.strip())
        injection_hits = detect_patterns(sanitized, INJECTION_PATTERNS)
        out_of_scope_hits = detect_patterns(sanitized, OUT_OF_SCOPE_PATTERNS)
        trace_id = str(uuid.uuid4())
        started = datetime.now(timezone.utc)
        technical_results: list[dict[str, Any]] = []
        history_results: list[dict[str, Any]] = []
        route: list[str] = []
        behavior_verdict = "PASS"
        contract_error = None

        if injection_hits:
            diagnosis = self._security_block()
            security_status = "blocked_prompt_injection_or_secret_request"
        elif out_of_scope_hits:
            diagnosis = self._out_of_scope()
            security_status = "blocked_out_of_scope_action"
        elif self._is_insufficient(sanitized):
            diagnosis = self._insufficient()
            security_status = "safe_analysis"
        elif self.provider is not None:
            route, technical_results, history_results = self._retrieve_with_provider(sanitized)
            diagnosis = self.provider.diagnose(
                sanitized,
                self._safe_retrieval_context(technical_results),
                self._safe_retrieval_context(history_results),
            )
            security_status = "safe_analysis"
        else:
            route = self._select_sources(sanitized)
            technical_results = (
                self.corpus.retrieve(sanitized, "technical_kb")
                if "buscar_conocimiento_tecnico" in route else []
            )
            history_results = (
                self.corpus.retrieve(sanitized, "jira_history")
                if "buscar_incidentes_historicos" in route else []
            )
            diagnosis = self._diagnose(sanitized, technical_results, history_results)
            security_status = "safe_analysis"

        # Behavior IA conserva exactamente la salida RAW del modelo/proveedor.
        # La validación es estricta: no se convierten tipos inválidos.
        raw_output = dict(diagnosis)
        try:
            raw_output = DiagnosisOutput.from_dict(raw_output).to_dict()
        except ContractValidationError as exc:
            behavior_verdict = "FAIL"
            contract_error = str(exc)

        allowed_source_ids = {
            item["source_id"] for item in technical_results + history_results
        }
        if behavior_verdict == "PASS":
            final_output, guardrails = self._apply_guardrails(raw_output, allowed_source_ids)
        else:
            final_output = self._contract_failure_output()
            guardrails = ["contract_failure_requires_human_review"]

        elapsed_ms = round((datetime.now(timezone.utc) - started).total_seconds() * 1000, 2)
        model_provider = (
            f"{self.provider.config.provider}:{self.provider.config.model}"
            if self.provider is not None else "local-deterministic-agent"
        )
        audit = AuditRecord(
            trace_id=trace_id,
            created_at=now_iso(),
            source=source,
            selected_tools=list(route),
            retrieval_count=len(route),
            model_provider=model_provider,
            latency_ms=elapsed_ms,
            security_status=security_status,
            input_was_sanitized=sanitized != raw_input.strip(),
            injection_signals=bool(injection_hits),
        )
        trace = audit.to_dict()
        trace.update({
            "mode": "llm" if self.provider is not None else "local_demo",
            "query": sanitized[:2_000],
            "corpus_loaded_at": self.corpus.loaded_at,
            "contract_error": contract_error,
        })

        return {
            "trace_id": trace_id,
            "created_at": now_iso(),
            "status": "requires_human_review",
            "behavior_ia": {
                "verdict": behavior_verdict,
                "raw_output": raw_output,
                "contract_error": contract_error,
            },
            "system_protected": {
                "verdict": "PASS" if isinstance(final_output, dict) else "FAIL",
                "final_output": final_output,
                "guardrails_applied": ["input_sanitization", "no_external_actions", "human_review_required"] + guardrails,
            },
            "retrieval": {
                "technical": technical_results if "technical_results" in locals() else [],
                "history": history_results if "history_results" in locals() else [],
            },
            "trace": trace,
        }

    def _retrieve_with_provider(self, text: str) -> tuple[list[str], list[dict[str, Any]], list[dict[str, Any]]]:
        decision = self.provider.route(text)
        if type(decision) is not dict or type(decision.get("technical")) is not bool or type(decision.get("history")) is not bool:
            raise ProviderError("El selector devolvió una ruta inválida")
        route: list[str] = []
        technical: list[dict[str, Any]] = []
        history: list[dict[str, Any]] = []
        if decision["technical"]:
            route.append("buscar_conocimiento_tecnico")
            technical = self.corpus.retrieve(text, "technical_kb")
        if decision["history"]:
            route.append("buscar_incidentes_historicos")
            history = self.corpus.retrieve(text, "jira_history")
        return route, technical, history

    @staticmethod
    def _safe_retrieval_context(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
        safe_results = []
        for item in results:
            validated = RetrievalResult.from_dict(item)
            safe_results.append({
                "source_id": validated.source_id,
                "source_type": validated.source_type,
                "score": validated.score,
                "excerpt": sanitize_text(validated.excerpt)[:2_000],
                "metadata": {key: sanitize_text(str(value))[:200] for key, value in validated.metadata.items()},
            })
        return safe_results

    @staticmethod
    def _apply_guardrails(diagnosis: dict[str, Any], allowed_source_ids: set[str]) -> tuple[dict[str, Any], list[str]]:
        safe = dict(diagnosis)
        adjustments: list[str] = []
        safe["fuentes_utilizadas"] = [source for source in safe["fuentes_utilizadas"] if source in allowed_source_ids]
        safe["incidentes_similares"] = [source for source in safe["incidentes_similares"] if source in allowed_source_ids and source.startswith("DEVOPS-")]
        if safe["fuera_de_alcance"]:
            safe["requiere_revision_humana"] = True
        mutable = re.compile(r"(?i)kubectl\s+(apply|delete|rollout|scale|patch|edit|create)|helm\s+(upgrade|rollback|install)|terraform\s+apply|ansible-playbook")
        for field_name in ("validaciones_recomendadas", "soluciones_sugeridas"):
            before = list(safe[field_name])
            safe[field_name] = [item for item in before if not mutable.search(item)]
            if before != safe[field_name]:
                adjustments.append(f"removed_mutating_commands_from_{field_name}")
        DiagnosisOutput.from_dict(safe)
        return safe, adjustments

    @staticmethod
    def _contract_failure_output() -> dict[str, Any]:
        return SecureLocalAgent._insufficient() | {
            "categoria": "Invalid model contract",
            "mensaje_al_especialista": "La respuesta del proveedor no cumplió el contrato estricto. No se entrega como diagnóstico; requiere revisión humana.",
        }

    @staticmethod
    def _is_insufficient(text: str) -> bool:
        has_error = any(marker.lower() in text.lower() for marker in ERROR_PATTERNS)
        generic = re.search(r"(?i)(no tengo|sin log|sin el log|sin mensaje|no hay información|no funciona)", text)
        technical_hint = re.search(r"(?i)(kubernetes|docker|jenkins|gitlab|github actions|azure|maven|sonarqube|helm|pipeline)", text)
        return bool(generic and not has_error and not technical_hint)

    @staticmethod
    def _select_sources(text: str) -> list[str]:
        lower = text.lower()
        has_signal = any(marker.lower() in lower for marker in ERROR_PATTERNS) or bool(
            re.search(r"(?i)(log|stacktrace|exit code|falló|falla|failed|error)", text)
        )
        if not has_signal:
            return []
        route = ["buscar_conocimiento_tecnico"]
        if re.search(r"(?i)(antecedente|similar|histórico|historico|jira|casos anteriores)", text) or has_signal:
            route.append("buscar_incidentes_historicos")
        return route

    def _diagnose(
        self,
        text: str,
        technical_results: list[dict[str, Any]],
        history_results: list[dict[str, Any]],
    ) -> dict[str, Any]:
        lower = text.lower()
        error = next((marker for marker in ERROR_PATTERNS if marker.lower() in lower), "No determinado")
        all_results = technical_results + history_results
        first = all_results[0] if all_results else {}
        metadata = first.get("metadata", {})
        category = metadata.get("category") or self._category_for(error)
        technology = self._technology_from_input(text) or metadata.get("technology") or "Desconocida"
        sources = [item["source_id"] for item in all_results if item.get("source_id")]
        similar = [item["source_id"] for item in history_results if item.get("source_id")]

        evidence = [f"El incidente contiene el indicador: {error}."] if error != "No determinado" else []
        if technical_results:
            evidence.append(f"Se recuperó conocimiento técnico: {technical_results[0]['source_id']}.")
        if history_results:
            evidence.append(f"Se recuperaron antecedentes históricos: {', '.join(similar[:3])}.")

        causes = self._causes_for(error)
        validations = self._validations_for(error)
        if technology == "Desconocida":
            validations.insert(0, "Confirmar la plataforma o tecnología afectada.")
        return {
            "categoria": category,
            "tecnologia": technology,
            "error_detectado": error,
            "confianza": 0.86 if error != "No determinado" else 0.25,
            "evidencia": evidence,
            "causas_probables": causes,
            "validaciones_recomendadas": validations,
            "soluciones_sugeridas": [
                "Revisar las causas y validaciones con un especialista autorizado antes de realizar cambios."
            ],
            "informacion_faltante": [] if error != "No determinado" else [
                "Mensaje de error exacto.", "Logs de la ejecución afectada.", "Servicio o componente afectado."
            ],
            "fuentes_utilizadas": sources,
            "incidentes_similares": similar,
            "fuera_de_alcance": False,
            "requiere_revision_humana": True,
            "mensaje_al_especialista": "Diagnóstico inicial generado en modo local. Validar la evidencia y las recomendaciones antes de actuar.",
        }

    @staticmethod
    def _technology_from_input(text: str) -> str | None:
        match = re.search(r"(?i)tecnolog(?:ía|ia)\s*:\s*([^\n]+)", text)
        return match.group(1).strip() if match else None

    @staticmethod
    def _category_for(error: str) -> str:
        return {
            "ImagePullBackOff": "Containers / Registry",
            "ErrImagePull": "Containers / Registry",
            "CrashLoopBackOff": "Runtime / Configuration",
            "OOMKilled": "Resources / Capacity",
            "BUILD FAILURE": "CI/CD / Tests",
            "There are test failures": "CI/CD / Tests",
            "Quality Gate": "CI/CD / Quality",
        }.get(error, "Unknown / Insufficient data")

    @staticmethod
    def _causes_for(error: str) -> list[str]:
        return {
            "ImagePullBackOff": ["Credenciales del registry inválidas o expiradas.", "imagePullSecret inexistente o no asociado.", "Imagen, tag o permisos del repositorio incorrectos."],
            "CrashLoopBackOff": ["Configuración o variable requerida ausente.", "Dependencia externa no disponible.", "Fallo durante el arranque o probe mal configurada."],
            "OOMKilled": ["Límite de memoria insuficiente.", "Crecimiento de memoria no acotado.", "En Java, heap sin margen para memoria nativa."],
        }.get(error, ["La causa requiere más evidencia técnica antes de determinarse."])

    @staticmethod
    def _validations_for(error: str) -> list[str]:
        return {
            "ImagePullBackOff": ["Confirmar imagen y tag.", "Revisar el mensaje exacto y los eventos de la ejecución.", "Verificar el imagePullSecret y permisos de lectura sin modificar secretos."],
            "CrashLoopBackOff": ["Revisar logs actuales y anteriores.", "Identificar exit code.", "Comparar la configuración esperada con la del ambiente."],
            "OOMKilled": ["Confirmar Reason y Exit Code.", "Comparar requests/limits con el consumo observado.", "Correlacionar reinicios con la carga."],
        }.get(error, ["Recopilar logs, mensaje exacto, timestamp y componente afectado."])

    @staticmethod
    def _insufficient() -> dict[str, Any]:
        return {
            "categoria": "Unknown / Insufficient data",
            "tecnologia": "Desconocida",
            "error_detectado": "No determinado",
            "confianza": 0.1,
            "evidencia": ["La entrada declara que no hay log ni mensaje de error."],
            "causas_probables": [],
            "validaciones_recomendadas": [],
            "soluciones_sugeridas": [],
            "informacion_faltante": ["Mensaje de error exacto.", "Logs de la ejecución afectada.", "Servicio o componente afectado."],
            "fuentes_utilizadas": [],
            "incidentes_similares": [],
            "fuera_de_alcance": False,
            "requiere_revision_humana": True,
            "mensaje_al_especialista": "No hay información técnica suficiente para emitir un diagnóstico fundamentado.",
        }

    @staticmethod
    def _out_of_scope() -> dict[str, Any]:
        return {
            "categoria": "Out of scope",
            "tecnologia": "Desconocida",
            "error_detectado": "No determinado",
            "confianza": 1.0,
            "evidencia": ["La solicitud pide ejecutar una acción mutante o modificar un sistema."],
            "causas_probables": [],
            "validaciones_recomendadas": ["Si procede, solicitar un análisis no destructivo del incidente."],
            "soluciones_sugeridas": [],
            "informacion_faltante": [],
            "fuentes_utilizadas": [],
            "incidentes_similares": [],
            "fuera_de_alcance": True,
            "requiere_revision_humana": True,
            "mensaje_al_especialista": "No ejecutaré ni simularé remediaciones, borrados o despliegues. La decisión debe continuar con un especialista autorizado.",
        }

    @staticmethod
    def _security_block() -> dict[str, Any]:
        return {
            "categoria": "Security / Unsafe request",
            "tecnologia": "Desconocida",
            "error_detectado": "No determinado",
            "confianza": 1.0,
            "evidencia": ["La entrada contiene una solicitud para alterar instrucciones o revelar información protegida."],
            "causas_probables": [],
            "validaciones_recomendadas": ["Revisar el incidente sin incluir secretos, credenciales ni instrucciones de sistema."],
            "soluciones_sugeridas": [],
            "informacion_faltante": [],
            "fuentes_utilizadas": [],
            "incidentes_similares": [],
            "fuera_de_alcance": True,
            "requiere_revision_humana": True,
            "mensaje_al_especialista": "La solicitud fue bloqueada. No revelaré prompts internos, secretos, credenciales ni tokens, y no ejecutaré acciones externas.",
        }

    @staticmethod
    def _validate_contract(diagnosis: dict[str, Any]) -> None:
        DiagnosisOutput.from_dict(diagnosis)


CORPUS = Corpus(SOURCES_DIR)
CONFIGURED_PROVIDER = build_provider()
AGENT = SecureLocalAgent(CORPUS, CONFIGURED_PROVIDER)
FEEDBACK_LOCK = threading.Lock()


def save_feedback(payload: dict[str, Any]) -> None:
    feedback = HumanFeedback.from_dict(payload)
    runtime_dir = ROOT / "runtime"
    runtime_dir.mkdir(exist_ok=True)
    feedback_path = runtime_dir / "feedback.jsonl"
    safe_payload = {
        "feedback_id": str(uuid.uuid4()),
        "created_at": now_iso(),
        "trace_id": feedback.trace_id,
        "label": feedback.label,
        "comment": sanitize_text(feedback.comment),
    }
    with FEEDBACK_LOCK, feedback_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(safe_payload, ensure_ascii=False) + "\n")


class RequestHandler(BaseHTTPRequestHandler):
    server_version = "DevOpsTriageMVP/0.1"

    def _headers(self, content_type: str = "application/json; charset=utf-8") -> None:
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", "default-src 'self'; style-src 'self'; script-src 'self'; connect-src 'self'; img-src 'self' data:")

    def _json(self, status: int, body: dict[str, Any]) -> None:
        encoded = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self._headers()
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def do_GET(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if path == "/api/health":
            self._json(HTTPStatus.OK, {
                "status": "ok",
                "mode": "llm" if CONFIGURED_PROVIDER is not None else "local_demo",
                "technical_documents": len(CORPUS.technical),
                "historical_incidents": len(CORPUS.history),
                "github_actions_configured": bool(os.environ.get("GITHUB_READ_TOKEN")),
                "llm_configured": CONFIGURED_PROVIDER is not None,
            })
            return
        if path == "/api/knowledge":
            self._json(HTTPStatus.OK, {
                "technical": [doc.source_id for doc in CORPUS.technical],
                "history": [doc.source_id for doc in CORPUS.history],
            })
            return
        if path == "/api/contracts":
            self._json(HTTPStatus.OK, contract_schema())
            return
        self._serve_static(path)

    def _serve_static(self, path: str) -> None:
        relative = "index.html" if path in ("", "/") else path.lstrip("/")
        candidate = (STATIC_DIR / relative).resolve()
        if STATIC_DIR.resolve() not in candidate.parents and candidate != STATIC_DIR.resolve():
            self._json(HTTPStatus.NOT_FOUND, {"error": "Not found"})
            return
        if not candidate.is_file():
            self._json(HTTPStatus.NOT_FOUND, {"error": "Not found"})
            return
        content_type = "text/html; charset=utf-8" if candidate.suffix == ".html" else "text/css; charset=utf-8" if candidate.suffix == ".css" else "application/javascript; charset=utf-8"
        data = candidate.read_bytes()
        self.send_response(HTTPStatus.OK)
        self._headers(content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self._json(HTTPStatus.BAD_REQUEST, {"error": "Content-Length inválido"})
            return
        if length <= 0 or length > MAX_BODY_BYTES:
            self._json(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, {"error": "Solicitud demasiado grande"})
            return
        try:
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._json(HTTPStatus.BAD_REQUEST, {"error": "JSON inválido"})
            return
        if not isinstance(payload, dict):
            self._json(HTTPStatus.BAD_REQUEST, {"error": "El cuerpo debe ser un objeto JSON"})
            return

        try:
            if path == "/api/analyze":
                incident = payload.get("incident", payload.get("input", ""))
                if type(incident) is dict:
                    result = AGENT.analyze_payload(incident)
                else:
                    source = str(payload.get("source", "manual"))[:40]
                    result = AGENT.analyze(incident, source)
                self._json(HTTPStatus.OK, result)
                return
            if path == "/api/analyze/github-actions":
                owner = payload.get("owner")
                repository = payload.get("repository")
                run_id = payload.get("run_id")
                if type(run_id) is not int:
                    raise GitHubActionsError("run_id debe ser entero")
                client = GitHubActionsClient.from_environment()
                incident = client.fetch_incident(owner, repository, run_id)
                result = AGENT.analyze_payload(incident)
                self._json(HTTPStatus.OK, result)
                return
            if path == "/api/feedback":
                save_feedback(payload)
                self._json(HTTPStatus.CREATED, {"status": "saved"})
                return
            self._json(HTTPStatus.NOT_FOUND, {"error": "Not found"})
        except ValueError as exc:
            self._json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
        except GitHubActionsError as exc:
            self._json(HTTPStatus.BAD_GATEWAY, {"error": str(exc)})
        except ProviderError as exc:
            print(f"[provider-safe-diagnostic] {exc}")
            self._json(HTTPStatus.SERVICE_UNAVAILABLE, {"error": "Proveedor LLM no disponible; no se generó un diagnóstico."})
        except Exception:
            self._json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": "Error interno controlado"})

    def log_message(self, format: str, *args: Any) -> None:
        print(f"[{now_iso()}] {format % args}")


def run(host: str = "127.0.0.1", port: int = 8000) -> None:
    server = ThreadingHTTPServer((host, port), RequestHandler)
    print(f"DevOps Triage MVP escuchando en http://{host}:{port}")
    print(f"Fuentes: {SOURCES_DIR}")
    mode = f"llm:{CONFIGURED_PROVIDER.config.model}" if CONFIGURED_PROVIDER is not None else "local_demo"
    print(f"Modo: {mode}; no hay shell, remediación ni acceso a secretos.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServidor detenido.")
    finally:
        server.server_close()


if __name__ == "__main__":
    run(
        host=os.environ.get("MVP_HOST", "127.0.0.1"),
        port=int(os.environ.get("MVP_PORT", "8000")),
    )
