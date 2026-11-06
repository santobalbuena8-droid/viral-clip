"""Persistencia local de jobs. Un archivo JSON por job, dentro de data/.

En Cloud Run este módulo se sustituye por Firestore o el payload de Pub/Sub.
El resto del pipeline habla con Job, no con el disco.
"""

from __future__ import annotations

import re
import threading
from datetime import datetime, timezone
from pathlib import Path

from app.config import data_dir
from app.models import Job
from app.pipeline.errors import PipelineError

_LOCK = threading.Lock()
_JOB_ID = re.compile(r"^[a-f0-9]{12}$")
_CLIP_ID = re.compile(r"^clip-\d+$")


def ensure_data_dir() -> Path:
    root = data_dir()
    (root / "jobs").mkdir(parents=True, exist_ok=True)
    return root


def validate_job_id(job_id: str) -> str:
    if not _JOB_ID.fullmatch(job_id):
        raise PipelineError("Identificador de job no válido.")
    return job_id


def validate_clip_id(clip_id: str) -> str:
    if not _CLIP_ID.fullmatch(clip_id):
        raise PipelineError("Identificador de clip no válido.")
    return clip_id


def job_dir(job_id: str) -> Path:
    return ensure_data_dir() / "jobs" / validate_job_id(job_id)


def job_file(job_id: str) -> Path:
    return job_dir(job_id) / "job.json"


def clip_path(job_id: str, clip_id: str) -> Path:
    path = (job_dir(job_id) / "clips" / f"{validate_clip_id(clip_id)}.mp4").resolve()
    root = job_dir(job_id).resolve()
    if not path.is_relative_to(root):
        raise PipelineError("La ruta del clip se sale del job.")
    return path


def save(job: Job) -> Job:
    job.updated_at = datetime.now(timezone.utc)
    payload = job.model_dump_json(indent=2)
    path = job_file(job.id)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".json.tmp")
    with _LOCK:
        temporary.write_text(payload, encoding="utf-8")
        temporary.replace(path)
    return job


def load(job_id: str) -> Job | None:
    try:
        path = job_file(job_id)
    except PipelineError:
        return None
    if not path.is_file():
        return None
    with _LOCK:
        raw = path.read_text(encoding="utf-8")
    return Job.model_validate_json(raw)
