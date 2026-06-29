"""Stem-separation port for future listening workflows."""

from __future__ import annotations

from typing import Literal, Protocol

from pydantic import BaseModel, Field

from music_assistant.domain.reference_profile import ReferenceSource


class SeparatedStem(BaseModel):
    name: Literal["drums", "bass", "vocals", "other", "mix"]
    role: Literal["percussion", "bass", "vocal", "harmony", "mix", "other"]
    path: str
    artifact_uri: str | None = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)


class StemSeparator(Protocol):
    def separate(self, source: ReferenceSource) -> list[SeparatedStem]:
        ...
