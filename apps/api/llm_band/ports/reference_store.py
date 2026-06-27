"""Reference-profile lookup port for follow-up Q&A."""

from __future__ import annotations

from typing import Optional, Protocol

from llm_band.domain.audio_profile import ReferenceProfile


class ReferenceStore(Protocol):
    def save(self, profile: ReferenceProfile) -> None:
        ...

    def get(self, reference_id: str) -> Optional[ReferenceProfile]:
        ...
