"""In-memory Songsterr tab bundle store."""

from __future__ import annotations

from threading import RLock
from typing import Optional

from music_assistant.infrastructure.web_research.songsterr_tabs import SongsterrTabBundle


class InMemorySongsterrTabStore:
    def __init__(self) -> None:
        self._lock = RLock()
        self._bundles: dict[str, SongsterrTabBundle] = {}

    def save(self, reference_id: str, bundle: SongsterrTabBundle) -> None:
        with self._lock:
            self._bundles[reference_id] = bundle

    def get(self, reference_id: str) -> Optional[SongsterrTabBundle]:
        with self._lock:
            return self._bundles.get(reference_id)
