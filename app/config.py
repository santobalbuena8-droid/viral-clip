"""Ajustes del POC. Se leen del entorno en cada consulta para poder
forzar MOCK_ANALYZE sin reiniciar el intérprete en pruebas.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def _flag(name: str) -> str:
    return os.environ.get(name, "").strip().lower()


def gemini_api_key() -> str:
    return os.environ.get("GEMINI_API_KEY", "").strip()


def gemini_model() -> str:
    return os.environ.get("GEMINI_MODEL", "gemini-2.5-flash").strip() or "gemini-2.5-flash"


def use_mock_analyze() -> bool:
    """Mock si no hay clave, o si MOCK_ANALYZE pide mock de forma explícita.

    MOCK_ANALYZE=0 sin clave no activa el mock: el análisis falla con un
    mensaje claro para no disfrazar un descuido de configuración.
    """

    flag = _flag("MOCK_ANALYZE")
    if flag in {"1", "true", "yes"}:
        return True
    if flag in {"0", "false", "no"}:
        return False
    return not gemini_api_key()


def data_dir() -> Path:
    raw = os.environ.get("DATA_DIR", "").strip()
    path = Path(raw) if raw else REPO_ROOT / "data"
    if not path.is_absolute():
        path = REPO_ROOT / path
    return path


# Ruta que Render usa para un Secret File llamado cookies.txt.
_DEFAULT_COOKIES = Path("/etc/secrets/cookies.txt")
_missing_cookie_paths: set[str] = set()


def cookies_file() -> Path | None:
    """Archivo Netscape de cookies para yt-dlp, o None.

    Si COOKIES_FILE está definida y ese archivo existe, se usa esa ruta.
    Si no hay variable, se usa /etc/secrets/cookies.txt cuando el Secret
    File de Render está montado. En cualquier otro caso, None.

    No lee ni registra el contenido del archivo: como mucho, la ruta.
    """

    explicit = os.environ.get("COOKIES_FILE", "").strip()
    if explicit:
        path = Path(explicit).expanduser()
        if path.is_file():
            return path
        key = str(path)
        if key not in _missing_cookie_paths:
            _missing_cookie_paths.add(key)
            logging.getLogger(__name__).warning(
                "COOKIES_FILE no apunta a un archivo existente: %s", path
            )
        return None
    if _DEFAULT_COOKIES.is_file():
        return _DEFAULT_COOKIES
    return None


def youtube_player_clients() -> list[str] | None:
    """Clientes de player de YouTube, o None para el default de yt-dlp.

    YOUTUBE_PLAYER_CLIENTS es una lista separada por comas
    (por ejemplo ``web,tv_embedded``). Vacía o ausente: no se fuerza
    player_client.
    """

    raw = os.environ.get("YOUTUBE_PLAYER_CLIENTS", "").strip()
    if not raw:
        return None
    clients = [part.strip() for part in raw.split(",") if part.strip()]
    return clients or None


def max_duration_sec() -> float | None:
    """Segundos máximos, o None si MAX_DURATION_SEC es 0 (sin límite)."""

    raw = os.environ.get("MAX_DURATION_SEC", "600").strip()
    try:
        value = float(raw)
    except ValueError:
        return 600.0
    if value <= 0:
        return None
    return value


def _even(value: int) -> int:
    return value if value % 2 == 0 else value - 1


def output_size() -> tuple[int, int]:
    """Tamaño de salida. 720x1280 por defecto; 1080x1920 también vale."""

    try:
        width = int(os.environ.get("OUTPUT_WIDTH", "720"))
        height = int(os.environ.get("OUTPUT_HEIGHT", "1280"))
    except ValueError:
        return 720, 1280
    width = _even(max(width, 2))
    height = _even(max(height, 2))
    return width, height


@dataclass(frozen=True)
class AnalyzeConfig:
    mock: bool
    gemini_configured: bool
    error: str | None = None


def analyze_config() -> AnalyzeConfig:
    configured = bool(gemini_api_key())
    flag = _flag("MOCK_ANALYZE")
    if flag in {"0", "false", "no"} and not configured:
        return AnalyzeConfig(
            mock=False,
            gemini_configured=False,
            error="MOCK_ANALYZE=0 pero no hay GEMINI_API_KEY.",
        )
    return AnalyzeConfig(mock=use_mock_analyze(), gemini_configured=configured)
