"""Ports for selecting representative artist/band songs."""

from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel, Field


class ArtistSongCandidate(BaseModel):
    title: str
    artist: str
    reason: str = ""
    popularity_rank: int | None = Field(default=None, ge=1)
    tab_likely: bool = False
    source_name: str = ""
    source_url: str = ""
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)


class ArtistCatalog(Protocol):
    def representative_songs(self, artist_name: str, *, limit: int = 6) -> list[ArtistSongCandidate]:
        ...
