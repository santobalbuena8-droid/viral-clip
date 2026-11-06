"""Video y clip de muestra para usar la app cuando YouTube bloquea la descarga.

El MP4 de origen se genera en el build de Docker (scripts/generate_demo.sh).
El clip ya renderizado se crea al arrancar y vive en DATA_DIR/demo, así que
/demo/sample.mp4 funciona después de cada redeploy aunque el disco sea efímero.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
import threading
from pathlib import Path

from app.config import REPO_ROOT, data_dir

logger = logging.getLogger(__name__)

DEMO_DIR = REPO_ROOT / "demo"
DEMO_SOURCE = DEMO_DIR / "muestra_45s.mp4"
_lock = threading.Lock()


def sample_clip_path() -> Path:
    return data_dir() / "demo" / "clip_muestra.mp4"


def ensure_source() -> Path:
    if not DEMO_SOURCE.is_file() or DEMO_SOURCE.stat().st_size == 0:
        script = REPO_ROOT / "scripts" / "generate_demo.sh"
        subprocess.run(["sh", str(script), str(DEMO_SOURCE)], check=True)
    return DEMO_SOURCE


def ensure_sample_clip() -> Path | None:
    """Renderiza una vez un clip 9:16 con subtítulos desde la muestra."""
    target = sample_clip_path()
    if target.is_file() and target.stat().st_size > 0:
        return target
    with _lock:
        if target.is_file() and target.stat().st_size > 0:
            return target
        try:
            from app.models import SubtitleStyle
            from app.pipeline.jobs import clip_file, create_job, run_job

            style = SubtitleStyle(text_color="#FFD23F", font_size=60)
            job = create_job(str(ensure_source()), 1, style)
            job = run_job(job.id)
            ready = next((c for c in job.clips if c.status.value == "ready"), None)
            if ready is None:
                logger.warning("demo sample failed: %s", job.error)
                return None
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(clip_file(job.id, ready.id), target)
            logger.info("demo sample ready at %s", target)
            return target
        except Exception:  # noqa: BLE001 - la muestra no debe tumbar el servidor
            logger.exception("demo sample failed")
            return None


def warm_up_in_background() -> None:
    threading.Thread(target=ensure_sample_clip, name="demo-warmup", daemon=True).start()
