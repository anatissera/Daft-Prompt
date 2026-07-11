"""Process-local reference-profile store. Replace with persistent storage later."""

from __future__ import annotations

from threading import Lock
from typing import Optional

from music_assistant.domain.audio_profile import ReferenceProfile


class InMemoryReferenceStore:
    def __init__(self) -> None:
        self._lock = Lock()
        self._profiles: dict[str, ReferenceProfile] = {}

    def save(self, profile: ReferenceProfile) -> None:
        with self._lock:
            self._profiles[profile.reference_id] = profile

    def get(self, reference_id: str) -> Optional[ReferenceProfile]:
        with self._lock:
            return self._profiles.get(reference_id)
