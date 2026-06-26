"""Audio-analysis port for future listening workflows."""

from __future__ import annotations

from typing import Protocol

from llm_band.domain.audio_profile import ReferenceProfile, ReferenceSource


class AudioAnalyzer(Protocol):
    def analyze(self, source: ReferenceSource) -> ReferenceProfile:
        ...
