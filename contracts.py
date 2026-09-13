from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


class ContractValidationError(ValueError):
    """A strict contract violation; values are never coerced silently."""


def _require_string(value: Any, field_name: str, allow_none: bool = True) -> str | None:
    if value is None and allow_none:
        return None
    if type(value) is not str:
        raise ContractValidationError(f"{field_name} debe ser string")
    return value


def _require_string_list(value: Any, field_name: str) -> list[str]:
    if type(value) is not list or any(type(item) is not str for item in value):
        raise ContractValidationError(f"{field_name} debe ser una lista de strings")
    return list(value)


def _require_bool(value: Any, field_name: str) -> bool:
    if type(value) is not bool:
        raise ContractValidationError(f"{field_name} debe ser booleano")
    return value


@dataclass(frozen=True)
class IncidentInput:
    source: str
    environment: str | None = None
    service: str | None = None
    technology: str | None = None
    pipeline: str | None = None
    job: str | None = None
    status: str | None = None
    error_message: str | None = None
    logs: str | None = None
    description: str | None = None
    timestamp: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_payload(cls, payload: Any) -> "IncidentInput":
        if type(payload) is str:
            if not payload.strip():
                raise ContractValidationError("incident no puede estar vacío")
            return cls(source="manual", description=payload)
        if type(payload) is not dict:
            raise ContractValidationError("incident debe ser string u objeto")
        allowed = {
            "source", "environment", "service", "technology", "pipeline", "job",
            "status", "error_message", "logs", "description", "timestamp", "metadata",
        }
        unknown = set(payload) - allowed
        if unknown:
            raise ContractValidationError(f"Campos no permitidos en IncidentInput: {sorted(unknown)}")
        source = _require_string(payload.get("source", "api"), "source", allow_none=False)
        metadata = payload.get("metadata", {})
        if type(metadata) is not dict:
            raise ContractValidationError("metadata debe ser objeto")
        values = {
            name: _require_string(payload.get(name), name)
            for name in (
                "environment", "service", "technology", "pipeline", "job", "status",
                "error_message", "logs", "description", "timestamp",
            )
        }
        if not any(values.get(name) for name in ("description", "logs", "error_message")):
            raise ContractValidationError("IncidentInput requiere description, logs o error_message")
        return cls(source=source, metadata=dict(metadata), **values)

    @classmethod
    def from_text(cls, text: str, source: str = "manual") -> "IncidentInput":
        if type(text) is not str or not text.strip():
            raise ContractValidationError("El incidente debe contener texto")
        return cls(source=source, description=text)

    def to_text(self) -> str:
        fields = [
            ("Ambiente", self.environment), ("Tecnología", self.technology),
            ("Servicio", self.service), ("Pipeline", self.pipeline), ("Job", self.job),
            ("Estado", self.status), ("Error", self.error_message),
            ("Descripción", self.description), ("Logs", self.logs),
        ]
        return "\n".join(f"{name}: {value}" for name, value in fields if value)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class DiagnosisOutput:
    categoria: str | None
    tecnologia: str | None
    error_detectado: str
    confianza: float
    evidencia: list[str]
    causas_probables: list[str]
    validaciones_recomendadas: list[str]
    soluciones_sugeridas: list[str]
    informacion_faltante: list[str]
    fuentes_utilizadas: list[str]
    incidentes_similares: list[str]
    fuera_de_alcance: bool
    requiere_revision_humana: bool
    mensaje_al_especialista: str

    @classmethod
    def from_dict(cls, value: Any) -> "DiagnosisOutput":
        if type(value) is not dict:
            raise ContractValidationError("DiagnosisOutput debe ser un objeto")
        required = {
            "categoria", "tecnologia", "error_detectado", "confianza", "evidencia",
            "causas_probables", "validaciones_recomendadas", "soluciones_sugeridas",
            "informacion_faltante", "fuentes_utilizadas", "incidentes_similares",
            "fuera_de_alcance", "requiere_revision_humana", "mensaje_al_especialista",
        }
        missing = required - set(value)
        if missing:
            raise ContractValidationError(f"Faltan campos en DiagnosisOutput: {sorted(missing)}")
        confidence = value["confianza"]
        if type(confidence) not in (int, float) or isinstance(confidence, bool) or not 0 <= confidence <= 1:
            raise ContractValidationError("confianza debe ser número entre 0 y 1")
        return cls(
            categoria=_require_string(value["categoria"], "categoria"),
            tecnologia=_require_string(value["tecnologia"], "tecnologia"),
            error_detectado=_require_string(value["error_detectado"], "error_detectado", allow_none=False),
            confianza=float(confidence),
            evidencia=_require_string_list(value["evidencia"], "evidencia"),
            causas_probables=_require_string_list(value["causas_probables"], "causas_probables"),
            validaciones_recomendadas=_require_string_list(value["validaciones_recomendadas"], "validaciones_recomendadas"),
            soluciones_sugeridas=_require_string_list(value["soluciones_sugeridas"], "soluciones_sugeridas"),
            informacion_faltante=_require_string_list(value["informacion_faltante"], "informacion_faltante"),
            fuentes_utilizadas=_require_string_list(value["fuentes_utilizadas"], "fuentes_utilizadas"),
            incidentes_similares=_require_string_list(value["incidentes_similares"], "incidentes_similares"),
            fuera_de_alcance=_require_bool(value["fuera_de_alcance"], "fuera_de_alcance"),
            requiere_revision_humana=_require_bool(value["requiere_revision_humana"], "requiere_revision_humana"),
            mensaje_al_especialista=_require_string(value["mensaje_al_especialista"], "mensaje_al_especialista", allow_none=False),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RetrievalResult:
    source_id: str
    source_type: str
    score: int | float
    excerpt: str
    metadata: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, value: Any) -> "RetrievalResult":
        if type(value) is not dict:
            raise ContractValidationError("RetrievalResult debe ser objeto")
        return cls(
            source_id=_require_string(value.get("source_id"), "source_id", allow_none=False),
            source_type=_require_string(value.get("source_type"), "source_type", allow_none=False),
            score=value.get("score", 0),
            excerpt=_require_string(value.get("excerpt", ""), "excerpt", allow_none=False),
            metadata=dict(value.get("metadata", {})),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class HumanFeedback:
    trace_id: str
    label: str
    comment: str = ""

    VALID_LABELS = {"useful", "needs_correction", "unsafe"}

    @classmethod
    def from_dict(cls, value: Any) -> "HumanFeedback":
        if type(value) is not dict:
            raise ContractValidationError("HumanFeedback debe ser objeto")
        trace_id = _require_string(value.get("trace_id"), "trace_id", allow_none=False)
        label = _require_string(value.get("label"), "label", allow_none=False)
        comment = _require_string(value.get("comment", ""), "comment", allow_none=False)
        if label not in cls.VALID_LABELS:
            raise ContractValidationError("label de feedback no permitido")
        return cls(trace_id=trace_id[:100], label=label, comment=comment[:2_000])


@dataclass(frozen=True)
class AuditRecord:
    trace_id: str
    created_at: str
    source: str
    selected_tools: list[str]
    retrieval_count: int
    model_provider: str
    latency_ms: float
    security_status: str
    input_was_sanitized: bool
    injection_signals: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def contract_schema() -> dict[str, Any]:
    return {
        "IncidentInput": {"source": "string", "description": "string|null", "logs": "string|null", "metadata": "object"},
        "DiagnosisOutput": {"error_detectado": "string", "confianza": "number[0,1]", "fuera_de_alcance": "boolean", "requiere_revision_humana": "boolean"},
        "RetrievalResult": {"source_id": "string", "source_type": "string", "excerpt": "string"},
        "HumanFeedback": {"trace_id": "string", "label": "useful|needs_correction|unsafe", "comment": "string"},
        "AuditRecord": {"trace_id": "string", "selected_tools": "string[]", "security_status": "string"},
    }
