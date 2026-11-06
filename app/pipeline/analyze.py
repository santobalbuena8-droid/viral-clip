"""Elige los intervalos que vale la pena convertir en clip.

Con GEMINI_API_KEY y sin MOCK_ANALYZE, manda la transcripción a Gemini Flash.
Si no hay clave, si MOCK_ANALYZE está activo, o si el modelo no devuelve
intervalos válidos, se usan 1–3 ventanas en la parte media del video.
"""

from __future__ import annotations

import json
import logging
import re
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeout
from dataclasses import dataclass

from app.config import analyze_config, gemini_api_key, gemini_model
from app.pipeline.errors import PipelineError

logger = logging.getLogger(__name__)

_VTT_STAMP = re.compile(
    r"(?P<h>\d{2}:)?(?P<m>\d{2}):(?P<s>\d{2})[.,](?P<ms>\d{1,3})"
)
_CUE_LINE = re.compile(
    r"(?P<start>(?:\d{2}:)?\d{2}:\d{2}[.,]\d{1,3})\s+-->\s+"
)

_BEATS: tuple[tuple[str, str], ...] = (
    (
        "El gancho",
        "Arranca ya metido en el video, cuando el ritmo está arriba.",
    ),
    (
        "El giro",
        "Toma el centro del video, donde suele estar el cambio.",
    ),
    (
        "El remate",
        "Cierra el cuerpo del video, antes de que se diluya.",
    ),
)


@dataclass(frozen=True)
class ClipSpec:
    title: str
    reason: str
    start_sec: float
    end_sec: float


def estimate_virality(
    *,
    title: str,
    reason: str,
    start_sec: float,
    end_sec: float,
    duration_sec: float,
    spoken_chars: int = 0,
) -> int:
    """Estimación 0–100 a partir del gancho, la duración y el texto.

    No mide audiencia real. El número viaja en el JSON del clip y no entra
    en el ASS que quema FFmpeg.
    """

    length = max(0.0, end_sec - start_sec)
    if 8 <= length <= 16:
        duration_score = 24
    elif 6 <= length <= 22:
        duration_score = 16
    elif 4 <= length <= 30:
        duration_score = 8
    else:
        duration_score = 0

    blob = f"{title} {reason}".lower()
    hook = 0
    if any(word in blob for word in ("gancho", "enganch", "hook")):
        hook += 14
    if any(word in blob for word in ("giro", "cambio", "inesper")):
        hook += 10
    if any(word in blob for word in ("remate", "cierre")):
        hook += 8
    if any(word in blob for word in ("ritmo", "momento")):
        hook += 4
    hook = min(hook, 18)

    specificity = 0
    if len(reason.strip()) >= 40:
        specificity += 8
    if len(reason.strip()) >= 90:
        specificity += 4

    position = 0
    if duration_sec > 0:
        start_ratio = start_sec / duration_sec
        end_ratio = end_sec / duration_sec
        if 0.08 <= start_ratio and end_ratio <= 0.92:
            position += 8
        if start_ratio < 0.2 and "gancho" in blob:
            position += 6

    speech = 0
    if spoken_chars >= 24:
        speech += 8
    if spoken_chars >= 90:
        speech += 4

    raw = 38 + duration_score + hook + specificity + position + speech
    return max(8, min(96, raw))


@dataclass(frozen=True)
class AnalyzeResult:
    clips: list[ClipSpec]
    mode: str
    note: str | None


def analyze(
    *,
    duration_sec: float,
    transcript: str | None,
    max_clips: int,
    title: str | None,
) -> AnalyzeResult:
    config = analyze_config()
    if config.error:
        raise PipelineError(config.error)
    text = (transcript or "").strip()
    if config.mock:
        note = (
            "MOCK_ANALYZE activo: ventanas en la parte media del video."
            if config.gemini_configured
            else "Sin GEMINI_API_KEY: ventanas en la parte media del video."
        )
        if text:
            note += " La transcripción se guardó y no se envió al modelo."
        return AnalyzeResult(
            clips=mock_clip_specs(duration_sec, max_clips),
            mode="mock",
            note=note,
        )
    if not text:
        return AnalyzeResult(
            clips=mock_clip_specs(duration_sec, max_clips),
            mode="mock_fallback",
            note="No hay subtítulos ni transcripción; se usaron ventanas medias.",
        )
    try:
        specs = gemini_clip_specs(
            duration_sec=duration_sec,
            transcript=text,
            max_clips=max_clips,
            title=title,
        )
    except Exception as exc:
        logger.warning("Gemini no pudo elegir clips: %s", exc)
        return AnalyzeResult(
            clips=mock_clip_specs(duration_sec, max_clips),
            mode="mock_fallback",
            note=f"Gemini no respondió ({exc}). Se usaron ventanas medias.",
        )
    if not specs:
        return AnalyzeResult(
            clips=mock_clip_specs(duration_sec, max_clips),
            mode="mock_fallback",
            note="Gemini no devolvió intervalos válidos. Se usaron ventanas medias.",
        )
    return AnalyzeResult(clips=specs, mode="gemini", note=None)


def mock_clip_specs(duration_sec: float, max_clips: int) -> list[ClipSpec]:
    """1–3 ventanas centradas en el cuerpo del video, sin pisarse."""

    if duration_sec < 8:
        raise PipelineError(
            f"El video dura {duration_sec:.1f}s. Hace falta al menos 8 segundos."
        )
    count = max(1, min(int(max_clips), 3))
    if duration_sec < 24:
        count = 1
    elif duration_sec < 42:
        count = min(count, 2)

    edge = 1.0 if duration_sec < 20 else min(8.0, duration_sec * 0.12)
    region_start = edge
    region_end = duration_sec - edge
    if region_end - region_start < 5:
        region_start = min(0.5, duration_sec / 4)
        region_end = duration_sec - region_start

    span = region_end - region_start
    slot = span / count
    length = min(12.0, max(6.0, slot * 0.7))
    if length > slot - 0.4:
        length = max(4.0, slot - 0.4)

    specs: list[ClipSpec] = []
    for index in range(count):
        slot_start = region_start + index * slot
        start = slot_start + (slot - length) / 2
        end = start + length
        start = max(0.0, min(start, duration_sec - 4))
        end = min(duration_sec, max(end, start + 4))
        beat_title, beat_reason = _BEATS[min(index, len(_BEATS) - 1)]
        specs.append(
            ClipSpec(
                title=beat_title,
                reason=beat_reason,
                start_sec=round(start, 3),
                end_sec=round(end, 3),
            )
        )
    return specs


def transcript_from_vtt(raw: str) -> str:
    """Pasa un VTT a líneas `[segundos] texto`, sin duplicar subtítulos automáticos."""

    cues: list[tuple[float, str]] = []
    lines = raw.splitlines()
    index = 0
    while index < len(lines):
        match = _CUE_LINE.match(lines[index].strip())
        if not match:
            index += 1
            continue
        start = _timestamp_to_seconds(match.group("start"))
        index += 1
        spoken: list[str] = []
        while index < len(lines) and lines[index].strip():
            cleaned = re.sub(r"<[^>]+>", "", lines[index].strip())
            if cleaned:
                spoken.append(cleaned)
            index += 1
        text = re.sub(r"\s+", " ", " ".join(spoken)).strip()
        if text and (not cues or cues[-1][1] != text):
            cues.append((start if start is not None else 0.0, text))
    rendered = "\n".join(f"[{start:.1f}] {text}" for start, text in cues)
    if len(rendered) > 12000:
        return rendered[:12000] + "\n…"
    return rendered


def gemini_clip_specs(
    *,
    duration_sec: float,
    transcript: str,
    max_clips: int,
    title: str | None,
) -> list[ClipSpec]:
    try:
        from google import genai
        from google.genai import types
    except ImportError as exc:
        raise PipelineError(
            "Falta el paquete google-genai. Instálalo o activa MOCK_ANALYZE=1."
        ) from exc

    prompt = _prompt(
        title=title,
        duration_sec=duration_sec,
        transcript=transcript,
        max_clips=max_clips,
    )
    logger.info("gemini request model=%s chars=%s", gemini_model(), len(prompt))

    def _call() -> str:
        client = genai.Client(api_key=gemini_api_key())
        response = client.models.generate_content(
            model=gemini_model(),
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.4,
                response_mime_type="application/json",
            ),
        )
        text = getattr(response, "text", None)
        if not text:
            raise PipelineError("Gemini devolvió una respuesta vacía.")
        return text

    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(_call)
        try:
            raw = future.result(timeout=60)
        except FuturesTimeout as exc:
            raise PipelineError("Gemini tardó más de 60s.") from exc
    payload = _parse_json(raw)
    clips = payload.get("clips") if isinstance(payload, dict) else None
    if not isinstance(clips, list):
        raise PipelineError("La respuesta de Gemini no trae una lista de clips.")
    return _sanitize(clips, duration_sec, max_clips)


def _prompt(*, title: str | None, duration_sec: float, transcript: str, max_clips: int) -> str:
    heading = f"Título: {title}\n" if title else ""
    return (
        "Eres editor de Viral Clip. Eliges fragmentos cortos con gancho para "
        "Shorts, Reels y TikTok.\n"
        f"{heading}"
        f"Duración del video: {duration_sec:.1f} segundos.\n"
        f"Elige como máximo {max_clips} clips.\n"
        "Reglas:\n"
        "- Cada clip dura entre 8 y 20 segundos.\n"
        f"- start_sec y end_sec caen dentro de 0 y {duration_sec:.1f}.\n"
        "- No se solapan.\n"
        "- Empieza y termina en una idea completa cuando la transcripción lo permita.\n"
        "- Evita intros vacías y despedidas.\n"
        "- title es corto y está en el idioma de la transcripción.\n"
        "- reason explica en una frase por qué puede enganchar.\n"
        "Responde solo JSON con esta forma:\n"
        '{"clips":[{"title":"...","reason":"...","start_sec":0,"end_sec":0}]}\n\n'
        f"Transcripción:\n{transcript}\n"
    )


def _parse_json(raw: str) -> object:
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise PipelineError("Gemini no devolvió JSON válido.") from exc


def _sanitize(raw_clips: list[object], duration_sec: float, max_clips: int) -> list[ClipSpec]:
    specs: list[ClipSpec] = []
    for item in raw_clips:
        if not isinstance(item, dict):
            continue
        try:
            start = float(item["start_sec"])
            end = float(item["end_sec"])
        except (KeyError, TypeError, ValueError):
            continue
        start = max(0.0, start)
        end = min(duration_sec, end)
        if end - start < 3:
            continue
        if end - start > 45:
            end = start + 45
        if end > duration_sec:
            start = max(0.0, duration_sec - min(45.0, duration_sec))
            end = duration_sec
        if end - start < 3:
            continue
        title = str(item.get("title") or "Clip").strip()[:80] or "Clip"
        reason = str(item.get("reason") or "Elegido por el modelo.").strip()[:240]
        specs.append(
            ClipSpec(
                title=title,
                reason=reason or "Elegido por el modelo.",
                start_sec=round(start, 3),
                end_sec=round(end, 3),
            )
        )
    specs.sort(key=lambda spec: spec.start_sec)
    return specs[:max_clips]


def _timestamp_to_seconds(value: str) -> float | None:
    match = _VTT_STAMP.fullmatch(value.strip())
    if not match:
        return None
    hours = int(match.group("h")[:-1]) if match.group("h") else 0
    minutes = int(match.group("m"))
    seconds = int(match.group("s"))
    millis = int(match.group("ms").ljust(3, "0"))
    return hours * 3600 + minutes * 60 + seconds + millis / 1000
