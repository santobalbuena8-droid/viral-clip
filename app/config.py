"""Ajustes del POC. Se leen del entorno en cada consulta para poder
forzar MOCK_ANALYZE sin reiniciar el intérprete en pruebas.
"""

from __future__ import annotations

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
