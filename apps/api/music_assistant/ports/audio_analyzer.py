"""Audio-analysis port for future listening workflows."""

from __future__ import annotations

from typing import Protocol

from music_assistant.domain.audio_profile import ReferenceProfile, ReferenceSource


class AudioAnalyzer(Protocol):
    def analyze(self, source: ReferenceSource) -> ReferenceProfile:
        ...
