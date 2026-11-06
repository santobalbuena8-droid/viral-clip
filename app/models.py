"""Modelos de job y clip que comparten la API, el worker y el cliente."""

from __future__ import annotations

import re
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

_HEX_COLOR = re.compile(r"^#[0-9A-Fa-f]{6}$")
SubtitleFont = Literal["sans", "display", "serif", "mono"]


class JobStatus(str, Enum):
    queued = "queued"
    downloading = "downloading"
    analyzing = "analyzing"
    rendering = "rendering"
    completed = "completed"
    failed = "failed"


class ClipStatus(str, Enum):
    pending = "pending"
    rendering = "rendering"
    ready = "ready"
    failed = "failed"


class SubtitleStyle(BaseModel):
    """Estilo que libass quema en el MP4. Los píxeles de fuente son para un alto de 1280."""

    model_config = ConfigDict(extra="ignore")

    text_color: str = "#FFFFFF"
    outline_color: str = "#000000"
    font_size: int = Field(default=54, ge=28, le=96)
    font_family: SubtitleFont = "sans"

    @field_validator("text_color", "outline_color")
    @classmethod
    def _hex_color(cls, value: str) -> str:
        raw = value.strip()
        if not _HEX_COLOR.fullmatch(raw):
            raise ValueError("El color tiene que ser #RRGGBB.")
        return raw.upper()


class Clip(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    title: str
    reason: str
    start_sec: float
    end_sec: float
    status: ClipStatus = ClipStatus.pending
    output_path: str | None = None
    playback_path: str | None = None
    error: str | None = None
    virality: int | None = Field(
        default=None,
        ge=0,
        le=100,
        description="Estimación de viralidad, de 0 a 100. Solo se muestra en la interfaz.",
    )


class Job(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    url: str
    max_clips: int
    status: JobStatus
    created_at: datetime
    updated_at: datetime
    title: str | None = None
    duration_sec: float | None = None
    source_path: str | None = None
    analyze_mode: str | None = None
    analyze_note: str | None = None
    error: str | None = None
    subtitle_style: SubtitleStyle = Field(default_factory=SubtitleStyle)
    clips: list[Clip] = Field(default_factory=list)


class CreateJobRequest(BaseModel):
    """Cuerpo de POST /jobs.

    `url` acepta un enlace de YouTube, `file://` o una ruta que exista en
    la máquina del backend. `local_path` es el equivalente de --local.
    """

    url: str | None = Field(
        default=None,
        description="URL de YouTube, file:// o ruta local.",
        examples=["https://www.youtube.com/watch?v=jNQXAC9IVRw"],
    )
    local_path: str | None = Field(
        default=None,
        description="Ruta local en el servidor. Tiene prioridad sobre url.",
    )
    max_clips: int = Field(default=3, ge=1, le=5)
    subtitle_style: SubtitleStyle = Field(
        default_factory=SubtitleStyle,
        description="Color, contorno, tamaño y fuente de los subtítulos quemados.",
    )

    @model_validator(mode="after")
    def _has_source(self) -> CreateJobRequest:
        if not (self.url and self.url.strip()) and not (
            self.local_path and self.local_path.strip()
        ):
            raise ValueError("Indica url o local_path.")
        return self

    def resolved_source(self) -> str:
        if self.local_path and self.local_path.strip():
            raw = self.local_path.strip()
            if raw.startswith(("file://", "http://", "https://")):
                return raw
            return str(Path(raw).expanduser())
        assert self.url is not None
        return self.url.strip()
