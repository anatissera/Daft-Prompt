"""Composition application service.

This module owns the choice between the real LLM director path and the canned
fallback. API code should not need to know how the song is produced.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from typing import Any

from .canned import canned_song
from .config import Settings, get_settings
from .graph import iter_negotiation_events, run_negotiation
from .schema import SongState
from .agents.director import run_director


class CompositionService:
    def __init__(
        self,
        *,
        settings_factory: Callable[[], Settings] = get_settings,
        director: Callable[[str], SongState] = run_director,
        negotiator: Callable[[SongState], SongState] = run_negotiation,
        event_streamer: Callable[[SongState], Iterator[dict[str, Any]]] = iter_negotiation_events,
        canned: Callable[[str], SongState] = canned_song,
    ):
        self.settings_factory = settings_factory
        self.director = director
        self.negotiator = negotiator
        self.event_streamer = event_streamer
        self.canned = canned

    def compose(self, style: str) -> tuple[SongState, str]:
        if self.settings_factory().llm_configured:
            song = self.director(style)
            return self.negotiator(song), "director"
        return self.canned(style), "canned"

    def stream(self, style: str) -> Iterator[tuple[dict[str, Any], SongState | None, str]]:
        if self.settings_factory().llm_configured:
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
