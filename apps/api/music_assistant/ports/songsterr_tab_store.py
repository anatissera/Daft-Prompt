"""Ephemeral Songsterr tab bundle lookup port."""

from __future__ import annotations

from typing import Any, Optional, Protocol


class SongsterrTabStore(Protocol):
    def save(self, reference_id: str, bundle: Any) -> None:
        ...

    def get(self, reference_id: str) -> Optional[Any]:
        ...
