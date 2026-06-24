"""Stem-separation port for future listening workflows."""

from __future__ import annotations

from typing import Protocol

from llm_band.domain.audio_profile import ReferenceSource, StemProfile


class StemSeparator(Protocol):
    def separate(self, source: ReferenceSource) -> list[StemProfile]:
        ...
