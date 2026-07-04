"""Composition application service."""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterator
from typing import Any

from music_assistant.domain.audio_profile import CompositionBrief
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

    def compose(self, style: str | CompositionBrief) -> tuple[SongState, str]:
        if not self.llm_configured():
            raise ComposeConfigurationError()
        prompt = _style_prompt(style)
        return self.negotiator(prompt), "director"

    def stream(self, style: str | CompositionBrief) -> Iterator[tuple[dict[str, Any], SongState | None, str]]:
        if not self.llm_configured():
            raise ComposeConfigurationError()
        source = "director"
        song = None
        prompt = _style_prompt(style)
        for event, song_snapshot in self.event_streamer(prompt):
            if song_snapshot is not None:
                song = song_snapshot
            yield event, song, source
        yield {}, song, source


def prompt_from_composition_brief(brief: CompositionBrief) -> str:
    data = brief.model_dump(mode="json")
    return (
        "CompositionBrief\n"
        f"user_request: {data['user_request']}\n"
        f"global_constraints: {data['global_constraints']}\n"
        f"references_used: {data['references_used']}\n"
        f"transfer_policy: {data['transfer_policy']}\n"
        f"harmonic_guidance: {data['harmonic_guidance']}\n"
        f"rhythmic_guidance: {data['rhythmic_guidance']}\n"
        f"form_guidance: {data['form_guidance']}\n"
        f"instrumentation: {data['instrumentation']}\n"
        f"instrument_requests: {data['instrument_requests']}\n"
        f"timbre_traits: {data['timbre_traits']}\n"
        f"forbidden_traits: {data['forbidden_traits']}\n"
        f"uncertainty_notes: {data['uncertainty_notes']}\n"
        "Use the structured brief as constraints. Preserve existing SongState output."
    )


def _style_prompt(style: str | CompositionBrief) -> str:
    if isinstance(style, CompositionBrief):
        return prompt_from_composition_brief(style)
    return style


def _director_event(song: SongState, source: str) -> dict[str, Any]:
    return {
        "type": "director",
        "source": source,
        "header": song.header.model_dump(mode="json"),
        "roster": [item.model_dump(mode="json") for item in song.roster],
    }
