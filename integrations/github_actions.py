from __future__ import annotations

import io
import json
import os
import re
import urllib.error
import urllib.request
import zipfile
from dataclasses import dataclass
from typing import Any

from contracts import IncidentInput


class GitHubActionsError(RuntimeError):
    """Safe integration error; never contains tokens or response bodies."""


_SECRET_PATTERNS = [
    (re.compile(r"(?i)(authorization\s*:\s*bearer\s+)[A-Za-z0-9._~+/=-]+"), r"\1[REDACTED]"),
    (re.compile(r"(?i)\b(password|passwd|pwd|token|secret|api[_-]?key)\s*[:=]\s*[^\s,;]+"), r"\1=[REDACTED]"),
]


def _sanitize_remote_text(text: str) -> str:
    result = text
    for pattern, replacement in _SECRET_PATTERNS:
        result = pattern.sub(replacement, result)
    return result


@dataclass(frozen=True)
class GitHubActionsClient:
    token: str
    base_url: str = "https://api.github.com"
    timeout_seconds: int = 30
    max_response_bytes: int = 8_000_000
    max_log_bytes: int = 120_000

    @classmethod
    def from_environment(cls) -> "GitHubActionsClient":
        token = os.environ.get("GITHUB_READ_TOKEN", "")
        if not token.strip():
            raise GitHubActionsError("Falta GITHUB_READ_TOKEN para el conector de lectura")
        return cls(token=token)

    def fetch_incident(self, owner: str, repository: str, run_id: int) -> dict[str, Any]:
        self._validate_repo(owner, repository)
        if type(run_id) is not int or run_id <= 0:
            raise GitHubActionsError("run_id inválido")

        run = self._get_json(f"/repos/{owner}/{repository}/actions/runs/{run_id}")
        jobs_payload = self._get_json(f"/repos/{owner}/{repository}/actions/runs/{run_id}/jobs?per_page=100")
        jobs = jobs_payload.get("jobs", []) if type(jobs_payload) is dict else []
        if type(jobs) is not list:
            raise GitHubActionsError("Respuesta de jobs inválida")

        failed_jobs = [job for job in jobs if isinstance(job, dict) and job.get("conclusion") in {"failure", "cancelled", "timed_out"}]
        selected_jobs = failed_jobs[:3] or [job for job in jobs if isinstance(job, dict)][:1]
        log_parts = []
        for job in selected_jobs:
            job_id = job.get("id")
            if type(job_id) is int and job_id > 0:
                log_parts.append(self._get_job_logs(owner, repository, job_id))

        run_name = str(run.get("name", "GitHub Actions workflow"))[:200]
        head_branch = str(run.get("head_branch", ""))[:120]
        status = str(run.get("conclusion") or run.get("status") or "unknown")[:80]
        service = str(run.get("repository", {}).get("name", repository))[:200] if isinstance(run.get("repository"), dict) else repository
        description = f"Workflow {run_name} en branch {head_branch}. Run {run_id}. Estado: {status}."
        logs = _sanitize_remote_text("\n\n".join(log_parts))[: self.max_log_bytes]
        incident = IncidentInput(
            source="github_actions",
            environment="unknown",
            service=service,
            technology="GitHub Actions",
            pipeline=run_name,
            status=status,
            logs=logs or None,
            description=description,
            timestamp=str(run.get("created_at", ""))[:80] or None,
            metadata={
                "owner": owner,
                "repository": repository,
                "run_id": str(run_id),
                "workflow_url": str(run.get("html_url", ""))[:500],
                "jobs_considered": str(len(selected_jobs)),
            },
        )
        return incident.to_dict()

    def _get_job_logs(self, owner: str, repository: str, job_id: int) -> str:
        raw = self._request_bytes(f"/repos/{owner}/{repository}/actions/jobs/{job_id}/logs", accept="application/vnd.github+json")
        try:
            with zipfile.ZipFile(io.BytesIO(raw)) as archive:
                names = [name for name in archive.namelist() if not name.endswith("/")]
                if len(names) > 20:
                    raise GitHubActionsError("Respuesta de logs contiene demasiados archivos")
                chunks = []
                total = 0
                for name in names:
                    if ".." in name.replace("\\", "/").split("/"):
                        raise GitHubActionsError("Ruta insegura en archivo de logs")
                    data = archive.read(name)
                    total += len(data)
                    if total > self.max_log_bytes:
                        break
                    chunks.append(data.decode("utf-8", errors="replace"))
                return "\n".join(chunks)
        except zipfile.BadZipFile:
            return raw.decode("utf-8", errors="replace")[: self.max_log_bytes]

    def _get_json(self, path: str) -> dict[str, Any]:
        raw = self._request_bytes(path, accept="application/vnd.github+json")
        try:
            body = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise GitHubActionsError("GitHub devolvió JSON inválido") from exc
        if type(body) is not dict:
            raise GitHubActionsError("GitHub devolvió una respuesta inválida")
        return body

    def _request_bytes(self, path: str, accept: str) -> bytes:
        request = urllib.request.Request(
            f"{self.base_url.rstrip('/')}{path}",
            headers={
                "Authorization": f"Bearer {self.token}",
                "Accept": accept,
                "User-Agent": "devops-triage-mvp/0.1",
            },
            method="GET",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                content_length = response.headers.get("Content-Length")
                if content_length and int(content_length) > self.max_response_bytes:
                    raise GitHubActionsError("Respuesta de GitHub demasiado grande")
                data = response.read(self.max_response_bytes + 1)
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ValueError) as exc:
            raise GitHubActionsError("GitHub Actions no respondió a una consulta de lectura") from exc
        if len(data) > self.max_response_bytes:
            raise GitHubActionsError("Respuesta de GitHub demasiado grande")
        return data

    @staticmethod
    def _validate_repo(owner: str, repository: str) -> None:
        valid = re.compile(r"^[A-Za-z0-9_.-]{1,100}$")
        if type(owner) is not str or not valid.fullmatch(owner):
            raise GitHubActionsError("owner inválido")
        if type(repository) is not str or not valid.fullmatch(repository):
            raise GitHubActionsError("repository inválido")
