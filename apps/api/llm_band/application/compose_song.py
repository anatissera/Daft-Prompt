"""Composition application service."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from typing import Any

from llm_band.domain.song_state import SongState


class ComposeSong:
    def __init__(
        self,
        *,
        llm_configured: Callable[[], bool],
        director: Callable[[str], SongState],
        negotiator: Callable[[SongState], SongState],
        event_streamer: Callable[[SongState], Iterator[dict[str, Any]]],
        canned: Callable[[str], SongState],
    ):
        self.llm_configured = llm_configured
        self.director = director
        self.negotiator = negotiator
        self.event_streamer = event_streamer
        self.canned = canned

    def compose(self, style: str) -> tuple[SongState, str]:
        if self.llm_configured():
            song = self.director(style)
            return self.negotiator(song), "director"
        return self.canned(style), "canned"

    def stream(self, style: str) -> Iterator[tuple[dict[str, Any], SongState | None, str]]:
        if self.llm_configured():
            song = self.director(style)
            source = "director"
            yield _director_event(song, source), None, source
            yield from ((event, None, source) for event in self.event_streamer(song))
            yield {}, song, source
            return

        song = self.canned(style)
        source = "canned"
        yield _director_event(song, source), None, source
        yield {
            "type": "convergence",
            "round": song.round,
            "converged": True,
            "resolved_requests": [],
        }, None, source
        yield {}, song, source


def _director_event(song: SongState, source: str) -> dict[str, Any]:
    return {
        "type": "director",
        "source": source,
        "header": song.header.model_dump(mode="json"),
        "roster": [item.model_dump(mode="json") for item in song.roster],
    }
