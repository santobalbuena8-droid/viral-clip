"""Subtítulos quemados con libass.

El estilo llega del job. Aquí se convierte a un ASS con PlayRes igual al
cuadro 9:16, para que el MP4 lleve el color, el contorno y la fuente
elegidos y no solo una vista previa.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.models import SubtitleStyle

# Familias que fontconfig resuelve en el servidor. libass las usa por nombre.
FONT_FILES = {
    "sans": "Noto Sans",
    "display": "Inter",
    "serif": "Liberation Serif",
    "mono": "Liberation Mono",
}

_CUE_LINE = re.compile(
    r"(?P<start>(?:\d{2}:)?\d{2}:\d{2}[.,]\d{1,3})\s+-->\s+"
    r"(?P<end>(?:\d{2}:)?\d{2}:\d{2}[.,]\d{1,3})"
)
_STAMP = re.compile(
    r"(?:(?P<h>\d{2}):)?(?P<m>\d{2}):(?P<s>\d{2})[.,](?P<ms>\d{1,3})"
)

_REFERENCE_HEIGHT = 1280


@dataclass(frozen=True)
class Caption:
    start_sec: float
    end_sec: float
    text: str


def spoken_chars(vtt_text: str | None, start_sec: float, end_sec: float) -> int:
    total = 0
    for cue in parse_vtt_cues(vtt_text or ""):
        if cue.end_sec > start_sec and cue.start_sec < end_sec:
            total += len(cue.text)
    return total


def font_name(family: str) -> str:
    return FONT_FILES.get(family, FONT_FILES["sans"])


def ass_color(hex_color: str) -> str:
    """#RRGGBB → &HAABBGGRR (alfa 00 = opaco)."""

    raw = hex_color.removeprefix("#")
    red, green, blue = int(raw[0:2], 16), int(raw[2:4], 16), int(raw[4:6], 16)
    return f"&H00{blue:02X}{green:02X}{red:02X}"


def captions_for_clip(
    *,
    vtt_text: str | None,
    start_sec: float,
    end_sec: float,
    fallback: str,
) -> list[Caption]:
    """Cues del tramo, en tiempo del clip (0 = el primer frame exportado)."""

    duration = max(0.5, end_sec - start_sec)
    selected: list[Caption] = []
    for cue in parse_vtt_cues(vtt_text or ""):
        overlap_start = max(start_sec, cue.start_sec)
        overlap_end = min(end_sec, cue.end_sec)
        if overlap_end - overlap_start < 0.25:
            continue
        selected.append(
            Caption(
                start_sec=round(overlap_start - start_sec, 3),
                end_sec=round(overlap_end - start_sec, 3),
                text=cue.text,
            )
        )
    if selected:
        return selected
    label = _clean_caption(fallback) or "Viral Clip"
    return [
        Caption(
            start_sec=0.15,
            end_sec=round(max(0.8, duration - 0.15), 3),
            text=label,
        )
    ]


def parse_vtt_cues(raw: str) -> list[Caption]:
    cues: list[Caption] = []
    lines = raw.splitlines()
    index = 0
    while index < len(lines):
        match = _CUE_LINE.search(lines[index].strip())
        if not match:
            index += 1
            continue
        start = _timestamp_to_seconds(match.group("start"))
        end = _timestamp_to_seconds(match.group("end"))
        index += 1
        spoken: list[str] = []
        while index < len(lines) and lines[index].strip():
            cleaned = re.sub(r"<[^>]+>", "", lines[index].strip())
            if cleaned:
                spoken.append(cleaned)
            index += 1
        text = _clean_caption(" ".join(spoken))
        if start is None or end is None or not text or end <= start:
            continue
        if cues and cues[-1].text == text and abs(cues[-1].end_sec - start) < 0.4:
            cues[-1] = Caption(cues[-1].start_sec, end, text)
            continue
        cues.append(Caption(start, end, text))
    return cues


def build_ass(
    captions: list[Caption],
    style: SubtitleStyle,
    *,
    width: int,
    height: int,
) -> str:
    scale = height / _REFERENCE_HEIGHT
    font_size = max(16, round(style.font_size * scale))
    outline = max(2, round(4 * scale))
    shadow = max(1, round(2 * scale))
    margin_v = max(64, round(150 * scale))
    margin_h = max(36, round(48 * scale))
    family = font_name(style.font_family)
    events = "\n".join(
        "Dialogue: 0,{start},{end},Caption,,0,0,0,,{text}".format(
            start=_ass_time(caption.start_sec),
            end=_ass_time(caption.end_sec),
            text=_escape_ass(caption.text),
        )
        for caption in captions
        if caption.end_sec > caption.start_sec and caption.text.strip()
    )
    return (
        "[Script Info]\n"
        "ScriptType: v4.00+\n"
        f"PlayResX: {width}\n"
        f"PlayResY: {height}\n"
        "WrapStyle: 0\n"
        "ScaledBorderAndShadow: yes\n"
        "\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
        "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, "
        "ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
        "Alignment, MarginL, MarginR, MarginV, Encoding\n"
        "Style: Caption,"
        f"{family},{font_size},{ass_color(style.text_color)},&H000000FF,"
        f"{ass_color(style.outline_color)},&H64000000,-1,0,0,0,100,100,0,0,1,"
        f"{outline},{shadow},2,{margin_h},{margin_h},{margin_v},1\n"
        "\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
        f"{events}\n"
    )


def ffmpeg_subtitle_path(path) -> str:
    """Escapa la ruta para el filtro subtitles= de FFmpeg."""

    text = path.resolve().as_posix()
    return (
        text.replace("\\", "\\\\")
        .replace(":", "\\:")
        .replace("'", "\\'")
        .replace(",", "\\,")
        .replace("[", "\\[")
        .replace("]", "\\]")
        .replace(";", "\\;")
    )


def _clean_caption(text: str) -> str:
    cleaned = re.sub(r"\s+", " ", text).strip()
    return cleaned[:180]


def _escape_ass(text: str) -> str:
    return (
        text.replace("\\", "\\\\")
        .replace("{", "\\{")
        .replace("}", "\\}")
        .replace("\n", "\\N")
    )


def _ass_time(seconds: float) -> str:
    seconds = max(0.0, seconds)
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    rest = seconds % 60
    return f"{hours}:{minutes:02d}:{rest:05.2f}"


def _timestamp_to_seconds(value: str) -> float | None:
    match = _STAMP.fullmatch(value.strip())
    if not match:
        return None
    hours = int(match.group("h") or 0)
    millis = int(match.group("ms").ljust(3, "0"))
    return hours * 3600 + int(match.group("m")) * 60 + int(match.group("s")) + millis / 1000
