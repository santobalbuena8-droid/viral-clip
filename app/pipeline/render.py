"""Exporta un intervalo a vertical 9:16 con FFmpeg.

Escala hasta cubrir el cuadro y recorta el centro. El video queda en
libx264 y yuv420p para que un reproductor de teléfono lo abra sin sorpresas.
"""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path

from app.config import output_size
from app.models import SubtitleStyle
from app.pipeline.errors import PipelineError
from app.pipeline.ffprobe import has_stream, probe_video, require_binary
from app.pipeline.subtitles import Caption, build_ass, ffmpeg_subtitle_path

logger = logging.getLogger(__name__)


def render_clip(
    source: Path,
    dest: Path,
    start_sec: float,
    end_sec: float,
    *,
    captions: list[Caption] | None = None,
    style: SubtitleStyle | None = None,
) -> None:
    require_binary("ffmpeg")
    if end_sec - start_sec < 0.5:
        raise PipelineError("El intervalo del clip es demasiado corto.")
    dest.parent.mkdir(parents=True, exist_ok=True)
    width, height = output_size()
    duration = end_sec - start_sec
    video_filter = (
        f"scale={width}:{height}:force_original_aspect_ratio=increase:flags=bicubic,"
        f"crop={width}:{height},setsar=1,setpts=PTS-STARTPTS"
    )
    if captions:
        ass_path = dest.with_suffix(".ass")
        ass_path.write_text(
            build_ass(captions, style or SubtitleStyle(), width=width, height=height),
            encoding="utf-8",
        )
        video_filter += f",subtitles='{ffmpeg_subtitle_path(ass_path)}'"
    video_filter += ",format=yuv420p"
    command = [
        "ffmpeg",
        "-y",
        "-ss",
        f"{max(0.0, start_sec):.3f}",
        "-i",
        str(source),
        "-t",
        f"{duration:.3f}",
        "-vf",
        video_filter,
        "-map",
        "0:v:0",
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "23",
        "-pix_fmt",
        "yuv420p",
        "-movflags",
        "+faststart",
    ]
    if has_stream(source, "a"):
        command.extend(["-map", "0:a:0", "-c:a", "aac", "-b:a", "128k", "-ac", "2"])
    else:
        command.append("-an")
    command.append(str(dest))

    logger.info(
        "render %s %.2f-%.2f -> %s",
        source.name,
        start_sec,
        end_sec,
        dest.name,
    )
    proc = subprocess.run(
        command,
        capture_output=True,
        text=True,
        check=False,
        timeout=300,
    )
    if proc.returncode != 0 or not dest.is_file():
        tail = (proc.stderr or proc.stdout or "ffmpeg falló").strip()[-2000:]
        raise PipelineError(f"FFmpeg no pudo exportar el clip: {tail}")
    _assert_vertical(dest, width, height)


def _assert_vertical(path: Path, width: int, height: int) -> None:
    info = probe_video(path)
    actual_width = int(info["width"])
    actual_height = int(info["height"])
    if actual_width != width or actual_height != height:
        raise PipelineError(
            f"El clip salió {actual_width}x{actual_height}; se esperaba {width}x{height}."
        )
    if info["pix_fmt"] != "yuv420p":
        raise PipelineError(f"pix_fmt inesperado: {info['pix_fmt']}.")
    if info["codec"] != "h264":
        raise PipelineError(f"Códec inesperado: {info['codec']}.")
    ratio = actual_width / actual_height
    if abs(ratio - (9 / 16)) > 0.02 and abs(ratio - (width / height)) > 0.001:
        raise PipelineError(f"El aspecto {actual_width}x{actual_height} no es vertical 9:16.")
