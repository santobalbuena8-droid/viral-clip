"""Lecturas puntuales con ffprobe. Download y render las comparten."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from app.pipeline.errors import PipelineError


def _run(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        capture_output=True,
        text=True,
        check=False,
    )


def require_binary(name: str) -> str:
    from shutil import which

    path = which(name)
    if not path:
        raise PipelineError(
            f"No está `{name}` en el PATH. Instálalo antes de crear un job."
        )
    return path


def probe_duration(path: Path) -> float:
    require_binary("ffprobe")
    proc = _run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ]
    )
    if proc.returncode != 0:
        detail = proc.stderr.strip() or "ffprobe falló"
        raise PipelineError(f"No se pudo leer la duración de {path.name}: {detail}")
    try:
        duration = float(proc.stdout.strip())
    except ValueError as exc:
        raise PipelineError(f"Duración ilegible en {path.name}.") from exc
    if duration <= 0:
        raise PipelineError(f"{path.name} no tiene duración útil.")
    return duration


def has_stream(path: Path, kind: str) -> bool:
    selector = "v:0" if kind == "v" else "a"
    proc = _run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            selector,
            "-show_entries",
            "stream=index",
            "-of",
            "csv=p=0",
            str(path),
        ]
    )
    return proc.returncode == 0 and bool(proc.stdout.strip())


def probe_video(path: Path) -> dict[str, object]:
    require_binary("ffprobe")
    proc = _run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=width,height,pix_fmt,codec_name",
            "-of",
            "json",
            str(path),
        ]
    )
    if proc.returncode != 0:
        detail = proc.stderr.strip() or "ffprobe falló"
        raise PipelineError(detail)
    try:
        payload = json.loads(proc.stdout or "{}")
        stream = (payload.get("streams") or [])[0]
    except (json.JSONDecodeError, IndexError, KeyError) as exc:
        raise PipelineError(f"{path.name} no tiene una pista de video legible.") from exc
    return {
        "width": int(stream["width"]),
        "height": int(stream["height"]),
        "pix_fmt": stream.get("pix_fmt"),
        "codec": stream.get("codec_name"),
    }
