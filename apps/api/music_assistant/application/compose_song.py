"""Composition application service."""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterator
from typing import Any

from music_assistant.domain.errors import OffTopicRequest
from music_assistant.domain.song_state import SongState

log = logging.getLogger(__name__)


class ComposeConfigurationError(RuntimeError):
    """Raised when a compose is requested but no LLM provider is configured. We surface
    this explicitly instead of silently returning the canned demo song, which made it
    look like the requested style had been composed when it hadn't."""

    code = "llm_not_configured"
    user_message = (
        "LLM provider is not configured. Set LLM_PROVIDER and the matching provider "
        "API key before composing."
    )


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
        if not self.llm_configured():
            raise ComposeConfigurationError()
        return self.negotiator(style), "director"

    def stream(self, style: str) -> Iterator[tuple[dict[str, Any], SongState | None, str]]:
        if not self.llm_configured():
            raise ComposeConfigurationError()
        source = "director"
        song = None
        for event, song_snapshot in self.event_streamer(style):
            if song_snapshot is not None:
                song = song_snapshot
            yield event, song, source
        yield {}, song, source


def _director_event(song: SongState, source: str) -> dict[str, Any]:
    return {
        "type": "director",
        "source": source,
        "header": song.header.model_dump(mode="json"),
        "roster": [item.model_dump(mode="json") for item in song.roster],
    }
