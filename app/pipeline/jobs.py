"""Orquesta descarga, análisis y render.

`run_job` es el punto de entrada del worker. En este POC lo dispara un
BackgroundTask de FastAPI. El mismo método puede colgarse después de un
push de Pub/Sub: los pasos no conocen HTTP ni el bus.
"""

from __future__ import annotations

import logging
import threading
from datetime import datetime, timezone
from uuid import uuid4

from app.models import Clip, ClipStatus, Job, JobStatus, SubtitleStyle
from app.pipeline.analyze import analyze, estimate_virality, transcript_from_vtt
from app.pipeline.download import acquire
from app.pipeline.errors import PipelineError
from app.pipeline.render import render_clip
from app.pipeline.subtitles import captions_for_clip, spoken_chars
from app import store

logger = logging.getLogger(__name__)

_GUARD = threading.Lock()
_JOB_LOCKS: dict[str, threading.Lock] = {}


def create_job(
    source: str,
    max_clips: int,
    subtitle_style: SubtitleStyle | None = None,
) -> Job:
    if not source.strip():
        raise PipelineError("Indica una URL o una ruta local.")
    if not 1 <= max_clips <= 5:
        raise PipelineError("max_clips tiene que estar entre 1 y 5.")
    now = datetime.now(timezone.utc)
    job = Job(
        id=uuid4().hex[:12],
        url=source.strip(),
        max_clips=max_clips,
        status=JobStatus.queued,
        created_at=now,
        updated_at=now,
        subtitle_style=subtitle_style or SubtitleStyle(),
    )
    return store.save(job)


def get_job(job_id: str) -> Job | None:
    return store.load(job_id)


def clip_file(job_id: str, clip_id: str):
    return store.clip_path(job_id, clip_id)


def run_job(job_id: str) -> Job:
    with _lock_for(job_id):
        return _run_job(job_id)


def _lock_for(job_id: str) -> threading.Lock:
    with _GUARD:
        return _JOB_LOCKS.setdefault(job_id, threading.Lock())


def _run_job(job_id: str) -> Job:
    job = store.load(job_id)
    if job is None:
        raise PipelineError(f"No existe el job {job_id}.")
    if job.status not in {JobStatus.queued, JobStatus.failed}:
        return job

    try:
        job.status = JobStatus.downloading
        job.error = None
        store.save(job)
        media = acquire(job.url, store.job_dir(job.id))
        job = _reload(job.id)
        job.source_path = str(media.path)
        job.duration_sec = round(media.duration_sec, 3)
        job.title = media.title
        store.save(job)

        job.status = JobStatus.analyzing
        store.save(job)
        transcript = _read_transcript(media.transcript_path)
        result = analyze(
            duration_sec=media.duration_sec,
            transcript=transcript,
            max_clips=job.max_clips,
            title=media.title,
        )
        vtt_raw = _read_vtt(media.transcript_path)
        job = _reload(job.id)
        job.analyze_mode = result.mode
        job.analyze_note = result.note
        job.clips = [
            Clip(
                id=f"clip-{index}",
                title=spec.title,
                reason=spec.reason,
                start_sec=spec.start_sec,
                end_sec=spec.end_sec,
                status=ClipStatus.pending,
                virality=estimate_virality(
                    title=spec.title,
                    reason=spec.reason,
                    start_sec=spec.start_sec,
                    end_sec=spec.end_sec,
                    duration_sec=media.duration_sec,
                    spoken_chars=spoken_chars(vtt_raw, spec.start_sec, spec.end_sec),
                ),
            )
            for index, spec in enumerate(result.clips, start=1)
        ]
        store.save(job)

        job.status = JobStatus.rendering
        store.save(job)
        ready = 0
        for clip in job.clips:
            clip.status = ClipStatus.rendering
            store.save(job)
            dest = store.clip_path(job.id, clip.id)
            captions = captions_for_clip(
                vtt_text=vtt_raw,
                start_sec=clip.start_sec,
                end_sec=clip.end_sec,
                fallback=clip.title,
            )
            try:
                render_clip(
                    media.path,
                    dest,
                    clip.start_sec,
                    clip.end_sec,
                    captions=captions,
                    style=job.subtitle_style,
                )
            except Exception as exc:
                logger.exception("clip %s of job %s failed", clip.id, job.id)
                clip.status = ClipStatus.failed
                clip.error = str(exc)
            else:
                clip.status = ClipStatus.ready
                clip.output_path = str(dest)
                clip.playback_path = f"/jobs/{job.id}/clips/{clip.id}"
                clip.error = None
                ready += 1
            store.save(job)

        job = _reload(job.id)
        if ready == 0:
            details = "; ".join(
                f"{clip.id}: {clip.error}" for clip in job.clips if clip.error
            )
            raise PipelineError(details or "Ningún clip se pudo exportar.")
        job.status = JobStatus.completed
        job.error = None
        store.save(job)
        logger.info("job %s completed with %s clips", job.id, ready)
        return job
    except Exception as exc:
        logger.exception("job %s failed", job_id)
        current = store.load(job_id) or job
        current.status = JobStatus.failed
        current.error = str(exc)
        store.save(current)
        return current


def _reload(job_id: str) -> Job:
    job = store.load(job_id)
    if job is None:
        raise PipelineError(f"El job {job_id} desapareció durante el pipeline.")
    return job


def _read_vtt(path) -> str | None:
    if path is None or not path.is_file():
        return None
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        logger.warning("no se pudo leer el VTT: %s", exc)
        return None


def _read_transcript(path) -> str | None:
    if path is None or not path.is_file():
        return None
    try:
        raw = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        logger.warning("no se pudo leer la transcripción: %s", exc)
        return None
    text = transcript_from_vtt(raw).strip()
    return text or None
