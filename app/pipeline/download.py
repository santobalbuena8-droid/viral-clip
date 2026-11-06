"""Consigue el video de origen.

Acepta una URL de YouTube (yt-dlp) o un archivo local (`file://` o ruta).
No recorta ni elige momentos: solo deja un archivo y, si existe, la
transcripción en VTT para el paso de análisis.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote, urlparse

from app.config import max_duration_sec
from app.pipeline.errors import PipelineError, VideoTooLongError
from app.pipeline.ffprobe import has_stream, probe_duration, require_binary

logger = logging.getLogger(__name__)

def _ytdlp_network_opts() -> dict:
    """Usa el proxy de egress del box cuando exista, y Node para JS de YouTube."""
    import os

    opts: dict = {
        "quiet": True,
        "no_warnings": True,
        "socket_timeout": 30,
    }
    # Prefer explicit SAND egress, then HTTPS_PROXY.
    proxy = (
        os.environ.get("HTTPS_PROXY")
        or os.environ.get("HTTP_PROXY")
        or os.environ.get("https_proxy")
        or os.environ.get("http_proxy")
    )
    if not proxy:
        addr = os.environ.get("SAND_EGRESS_TUNNEL_PROXY_ADDR", "").strip()
        if addr:
            proxy = addr if "://" in addr else f"http://{addr}"
    if proxy:
        opts["proxy"] = proxy
    # yt-dlp 2025+ wants a JS runtime for some clients.
    opts["js_runtimes"] = {"node": {}}
    return opts



VIDEO_SUFFIXES = {".mp4", ".mkv", ".webm", ".mov", ".m4v"}


@dataclass(frozen=True)
class MediaSource:
    path: Path
    title: str
    duration_sec: float
    transcript_path: Path | None


def acquire(source: str, work_dir: Path) -> MediaSource:
    require_binary("ffprobe")
    work_dir.mkdir(parents=True, exist_ok=True)
    remote, local = _split_source(source)
    if local is not None:
        return _acquire_local(local, work_dir)
    return _acquire_youtube(remote, work_dir)


def _split_source(source: str) -> tuple[str, Path | None]:
    raw = source.strip()
    if not raw:
        raise PipelineError("La fuente está vacía.")
    if raw.startswith("file://"):
        parsed = urlparse(raw)
        path = Path(unquote(parsed.path)).expanduser()
        return str(path), path
    if raw.startswith(("http://", "https://")):
        return raw, None
    path = Path(raw).expanduser()
    if path.is_file():
        return str(path.resolve()), path
    if raw.startswith("/") or raw.startswith("~") or raw.startswith("."):
        raise PipelineError(f"No existe el archivo local: {path}")
    raise PipelineError(
        "La fuente tiene que ser una URL http(s), un file:// o una ruta local."
    )


def _reject_duration(duration: float, label: str) -> None:
    limit = max_duration_sec()
    if limit is None:
        return
    if duration > limit:
        raise VideoTooLongError(
            f"{label} dura {duration:.0f}s y el límite de este POC es {limit:.0f}s."
        )


def _acquire_local(path: Path, work_dir: Path) -> MediaSource:
    if not path.is_file():
        raise PipelineError(f"No existe el archivo local: {path}")
    if not has_stream(path, "v"):
        raise PipelineError(f"{path.name} no contiene una pista de video.")
    duration = probe_duration(path)
    _reject_duration(duration, path.name)
    suffix = path.suffix.lower() if path.suffix.lower() in VIDEO_SUFFIXES else ".mp4"
    dest = work_dir / f"source{suffix}"
    if dest.is_symlink() or dest.exists():
        dest.unlink()
    try:
        dest.symlink_to(path.resolve())
    except OSError:
        shutil.copy2(path, dest)
    logger.info("local source %s duration=%.1f", path, duration)
    return MediaSource(
        path=dest,
        title=path.stem,
        duration_sec=duration,
        transcript_path=_sidecar_vtt(path),
    )


def _sidecar_vtt(path: Path) -> Path | None:
    matches = sorted(path.parent.glob(f"{path.stem}*.vtt"))
    return matches[0] if matches else None


def _acquire_youtube(url: str, work_dir: Path) -> MediaSource:
    try:
        import yt_dlp
    except ImportError as exc:
        raise PipelineError(
            "Falta el paquete yt-dlp. Instálalo con pip install -r requirements.txt."
        ) from exc

    probe_opts = {
        **_ytdlp_network_opts(),
        "noplaylist": True,
        "skip_download": True,
        "extractor_args": {"youtube": {"player_client": ["android", "web"]}},
    }
    try:
        with yt_dlp.YoutubeDL(probe_opts) as ydl:
            info = ydl.extract_info(url, download=False)
    except Exception as exc:
        raise _youtube_error(exc, "No se pudo leer el video") from exc
    if not info:
        raise PipelineError("yt-dlp no devolvió información del video.")
    if info.get("is_live") or info.get("live_status") == "is_live":
        raise PipelineError("Los directos no entran en este POC.")

    title = str(info.get("title") or "video")
    duration = float(info.get("duration") or 0)
    if duration <= 0:
        raise PipelineError("No se pudo leer la duración antes de descargar.")
    _reject_duration(duration, f"«{title}»")

    video = _download_with_retries(url, work_dir)
    actual = probe_duration(video)
    _reject_duration(actual, f"«{title}»")
    logger.info("youtube source %s duration=%.1f file=%s", title, actual, video.name)
    return MediaSource(
        path=video,
        title=title,
        duration_sec=actual,
        transcript_path=_find_vtt(work_dir),
    )


def _youtube_error(exc: Exception, phase: str) -> PipelineError:
    text = str(exc).strip()
    lowered = text.lower()
    if "not a bot" in lowered or "sign in to confirm" in lowered:
        return PipelineError(
            "YouTube bloqueó la descarga y pide confirmar que no eres un bot. "
            "Toca «Probar con muestra» para crear clips sin YouTube."
        )
    first = text.splitlines()[0][:500] if text else exc.__class__.__name__
    return PipelineError(f"{phase}: {first}")


_FORMAT_TRIES = (
    "bv*[ext=mp4][height<=720]+ba[ext=m4a]/b[ext=mp4][height<=720]/bv*[height<=720]+ba/b[height<=720]",
    "bv*[height<=480]+ba/b[height<=480]/bv*+ba/b",
    "bv*+ba/b",
)



def _try_optional_subs(url: str, work_dir: Path) -> None:
    """Best-effort captions; ignore 429 / missing tracks."""
    import yt_dlp

    if _find_vtt(work_dir) is not None:
        return
    options = {
        **_ytdlp_network_opts(),
        "skip_download": True,
        "writesubtitles": True,
        "writeautomaticsub": True,
        "subtitleslangs": ["es", "en"],
        "subtitlesformat": "vtt",
        "outtmpl": str(work_dir / "source.%(ext)s"),
        "extractor_args": {"youtube": {"player_client": ["android", "web"]}},
    }
    try:
        with yt_dlp.YoutubeDL(options) as ydl:
            ydl.download([url])
    except Exception as exc:
        logger.warning("subtítulos opcionales omitidos: %s", exc)


def _download_with_retries(url: str, work_dir: Path) -> Path:
    import yt_dlp

    last_error: Exception | None = None
    for attempt, fmt in enumerate(_FORMAT_TRIES, start=1):
        _cleanup_partials(work_dir)
        options = {
            **_ytdlp_network_opts(),
            "format": fmt,
            "outtmpl": str(work_dir / "source.%(ext)s"),
            "merge_output_format": "mp4",
            "noplaylist": True,
            "retries": 5,
            "fragment_retries": 5,
            "file_access_retries": 3,
            # Subs are optional: a 429 on captions must not kill the clip job.
            "writesubtitles": False,
            "writeautomaticsub": False,
            "overwrites": True,
            "extractor_args": {
                "youtube": {"player_client": ["android", "web", "default"]}
            },
        }
        logger.info("youtube download attempt %s format=%s", attempt, fmt)
        try:
            with yt_dlp.YoutubeDL(options) as ydl:
                ydl.download([url])
        except Exception as exc:
            last_error = exc
            logger.warning("intento %s de descarga falló: %s", attempt, exc)
        else:
            chosen = select_playable_media(work_dir)
            if chosen is not None:
                _try_optional_subs(url, work_dir)
                return chosen
            logger.warning("intento %s no dejó video con imagen", attempt)
        if attempt < len(_FORMAT_TRIES):
            time.sleep(1.5)

    if _has_audio_without_video(work_dir):
        raise PipelineError(
            "YouTube solo entregó audio, sin una pista de video completa. "
            "Prueba otro enlace o un MP4 local."
        )
    if last_error is not None:
        raise _youtube_error(last_error, "La descarga falló") from last_error
    raise PipelineError(
        "La descarga no dejó un video reproducible. "
        "El archivo de imagen quedó incompleto."
    )


def select_playable_media(work_dir: Path) -> Path | None:
    """Elige un archivo con imagen, uniendo el audio suelto si hace falta.

    Ignora `.part` y archivos que solo tienen audio (por ejemplo un WebM
    de Opus que yt-dlp deja cuando el video no termina).
    """

    files = [path for path in work_dir.iterdir() if path.is_file() and not _is_partial(path)]
    videos = [path for path in files if has_stream(path, "v")]
    if not videos:
        return None
    with_audio = [path for path in videos if has_stream(path, "a")]
    if with_audio:
        return max(with_audio, key=lambda path: path.stat().st_size)
    video = max(videos, key=lambda path: path.stat().st_size)
    audios = [
        path
        for path in files
        if path not in videos and has_stream(path, "a")
    ]
    if not audios:
        return video
    merged = work_dir / "source-merged.mp4"
    _merge_audio(video, max(audios, key=lambda path: path.stat().st_size), merged)
    return merged


def _merge_audio(video: Path, audio: Path, dest: Path) -> None:
    require_binary("ffmpeg")
    if dest.exists():
        dest.unlink()
    commands = (
        [
            "ffmpeg", "-y", "-i", str(video), "-i", str(audio),
            "-map", "0:v:0", "-map", "1:a:0",
            "-c:v", "copy", "-c:a", "aac", "-shortest", str(dest),
        ],
        [
            "ffmpeg", "-y", "-i", str(video), "-i", str(audio),
            "-map", "0:v:0", "-map", "1:a:0",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac",
            "-shortest", str(dest),
        ],
    )
    error = ""
    for command in commands:
        proc = subprocess.run(command, capture_output=True, text=True, timeout=180)
        if proc.returncode == 0 and dest.is_file() and has_stream(dest, "v"):
            return
        error = (proc.stderr or proc.stdout or "").strip()[-500:]
        if dest.exists():
            dest.unlink()
    raise PipelineError(f"No se pudo unir el video y el audio de YouTube. {error}")


def _has_audio_without_video(work_dir: Path) -> bool:
    files = [path for path in work_dir.iterdir() if path.is_file() and not _is_partial(path)]
    if any(has_stream(path, "v") for path in files):
        return False
    return any(has_stream(path, "a") for path in files)


def _cleanup_partials(work_dir: Path) -> None:
    for path in work_dir.iterdir():
        if path.is_file() and _is_partial(path):
            path.unlink(missing_ok=True)


def _is_partial(path: Path) -> bool:
    name = path.name.lower()
    return name.endswith(".part") or name.endswith(".ytdl") or name.endswith(".temp")


def _find_vtt(work_dir: Path) -> Path | None:
    files = list(work_dir.glob("*.vtt"))
    if not files:
        return None

    def rank(path: Path) -> tuple[int, str]:
        name = path.name.lower()
        if ".es" in name:
            return (0, name)
        if ".en" in name:
            return (1, name)
        return (2, name)

    return sorted(files, key=rank)[0]
