"""Errores de dominio del pipeline. La API los convierte en estado failed."""


class PipelineError(Exception):
    """Fallo esperado: entrada inválida, límite de duración, ffmpeg o red."""


class VideoTooLongError(PipelineError):
    """El POC rechaza videos por encima de MAX_DURATION_SEC."""
