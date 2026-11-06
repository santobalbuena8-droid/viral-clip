"""Adaptador HTTP de Viral Clip.

Cloud Run puede servir este módulo tal cual. El trabajo pesado vive en
`app.pipeline.jobs.run_job`, que no depende de la petición.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
from contextlib import asynccontextmanager

from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse

from app import __version__, demo
from app.config import REPO_ROOT, analyze_config, max_duration_sec, output_size
from app.models import ClipStatus, CreateJobRequest, DemoJobRequest, Job
from app.pipeline.errors import PipelineError
from app.pipeline.jobs import clip_file, create_job, get_job, run_job
from app.store import ensure_data_dir

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)


@asynccontextmanager
async def _lifespan(_app: FastAPI):
    ensure_data_dir()
    demo.warm_up_in_background()
    yield


app = FastAPI(
    title="Viral Clip",
    version=__version__,
    summary="De un video de YouTube a clips verticales 9:16.",
    lifespan=_lifespan,
)

# POC local: la app Android y cualquier origen pueden llamar a la API.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def root():
    return RedirectResponse(url="/web.html", status_code=307)


@app.get("/web.html")
def web_ui() -> FileResponse:
    page = REPO_ROOT / "web.html"
    if not page.is_file():
        raise HTTPException(status_code=404, detail="No está web.html.")
    return FileResponse(page, media_type="text/html; charset=utf-8")


@app.get("/health")
def health() -> dict[str, object]:
    config = analyze_config()
    width, height = output_size()
    return {
        "status": "ok",
        "service": "Viral Clip",
        "ffmpeg": shutil.which("ffmpeg") is not None,
        "ffprobe": shutil.which("ffprobe") is not None,
        "mock_analyze": config.mock,
        "gemini_configured": config.gemini_configured,
        "analyze_error": config.error,
        "max_duration_sec": max_duration_sec(),
        "output_width": width,
        "output_height": height,
    }


@app.post("/jobs/demo", response_model=Job, status_code=202)
def post_demo_job(background: BackgroundTasks, body: DemoJobRequest | None = None) -> Job:
    """Crea clips desde el video de muestra del servidor (sin YouTube)."""
    body = body or DemoJobRequest()
    try:
        source = demo.ensure_source()
        job = create_job(str(source), body.max_clips, body.subtitle_style)
    except (OSError, subprocess.CalledProcessError) as exc:
        raise HTTPException(status_code=500, detail="Falta el video de muestra en el servidor.") from exc
    except PipelineError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    background.add_task(run_job, job.id)
    return job


@app.get("/demo/sample.mp4")
def demo_sample() -> FileResponse:
    """Clip 9:16 ya renderizado, incluido en la imagen: nunca depende de un job."""
    path = demo.ensure_sample_clip()
    if path is None:
        raise HTTPException(status_code=503, detail="El clip de muestra no se pudo preparar. Prueba en unos segundos.")
    return FileResponse(path, media_type="video/mp4", filename="viral-clip-muestra.mp4")


@app.get("/demo/source.mp4")
def demo_source() -> FileResponse:
    try:
        source = demo.ensure_source()
    except (OSError, subprocess.CalledProcessError) as exc:
        raise HTTPException(status_code=404, detail="No está el video de muestra.") from exc
    return FileResponse(source, media_type="video/mp4", filename="muestra_45s.mp4")


@app.post("/jobs", response_model=Job, status_code=202)
def post_job(body: CreateJobRequest, background: BackgroundTasks) -> Job:
    try:
        job = create_job(body.resolved_source(), body.max_clips, body.subtitle_style)
    except PipelineError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    background.add_task(run_job, job.id)
    return job


@app.get("/jobs/{job_id}", response_model=Job)
def read_job(job_id: str) -> Job:
    job = get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="No existe ese job.")
    return job


@app.get("/jobs/{job_id}/clips/{clip_id}")
def download_clip(job_id: str, clip_id: str) -> FileResponse:
    job = get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="No existe ese job.")
    clip = next((item for item in job.clips if item.id == clip_id), None)
    if clip is None:
        raise HTTPException(status_code=404, detail="No existe ese clip.")
    if clip.status != ClipStatus.ready:
        raise HTTPException(status_code=409, detail="El clip todavía no está listo.")
    try:
        path = clip_file(job_id, clip_id)
    except PipelineError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not path.is_file():
        raise HTTPException(status_code=404, detail="El archivo del clip no está.")
    return FileResponse(
        path,
        media_type="video/mp4",
        filename=f"viral-clip-{clip_id}.mp4",
    )
