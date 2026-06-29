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
        negotiator: Callable[[str], SongState],
        event_streamer: Callable[[str], Iterator[tuple[dict[str, Any], Any]]],
        canned: Callable[[str], SongState],
    ):
        self.llm_configured = llm_configured
        self.negotiator = negotiator
        self.event_streamer = event_streamer
        self.canned = canned

    def compose(self, style: str) -> tuple[SongState, str]:
        if self.llm_configured():
            return self.negotiator(style), "director"
        return self.canned(style), "canned"

    def stream(self, style: str) -> Iterator[tuple[dict[str, Any], SongState | None, str]]:
        if self.llm_configured():
            source = "director"
            song = None
            for event, song_snapshot in self.event_streamer(style):
                if song_snapshot is not None:
                    song = song_snapshot
                yield event, song, source
            yield {}, song, source
            return

        song = self.canned(style)
        source = "canned"
        yield _director_event(song, source), song, source
        yield {
            "type": "convergence",
            "round": song.round,
            "converged": True,
            "resolved_requests": [],
        }, song, source
        yield {}, song, source


def _director_event(song: SongState, source: str) -> dict[str, Any]:
    return {
        "type": "director",
        "source": source,
        "header": song.header.model_dump(mode="json"),
        "roster": [item.model_dump(mode="json") for item in song.roster],
    }
