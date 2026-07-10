"""Composition application service."""

from __future__ import annotations

import logging
import json
import time
from copy import deepcopy
from collections.abc import Callable, Iterator
from typing import Any

from music_assistant.domain.audio_profile import CompositionBrief
from music_assistant.domain.errors import OffTopicRequest
from music_assistant.domain.song_state import SongState
from music_assistant.music.reference_materialization import register_literal_note_pack

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
        instrument_reviser: Callable[[SongState, str, str], SongState] | None = None,
    ):
        self.llm_configured = llm_configured
        self.negotiator = negotiator
        self.event_streamer = event_streamer
        self.canned = canned
        self.instrument_reviser = instrument_reviser

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
        started_at = time.monotonic()
        previous_event_at = started_at
        for event, song_snapshot in self.event_streamer(prompt):
            if song_snapshot is not None:
                song = song_snapshot
            if event:
                now = time.monotonic()
                event = {
                    **event,
                    "elapsed_seconds": round(now - started_at, 3),
                    "stage_elapsed_seconds": round(now - previous_event_at, 3),
                }
                previous_event_at = now
            yield event, song, source
        yield {}, song, source

    def revise_instrument(self, song: SongState, instruction: str, instrument_id: str) -> tuple[SongState, str]:
        if not self.llm_configured():
            raise ComposeConfigurationError()
        if self.instrument_reviser is None:
            raise ComposeConfigurationError()
        return self.instrument_reviser(song, instruction, instrument_id), "director"


def prompt_from_composition_brief(brief: CompositionBrief) -> str:
    data = brief.model_dump(mode="json")
    instrument_requests = _prompt_safe_instrument_requests(data["instrument_requests"])
    return (
        "CompositionBrief\n"
        f"user_request: {data['user_request']}\n"
        f"global_constraints: {data['global_constraints']}\n"
        f"references_used: {data['references_used']}\n"
        f"transfer_policy: {data['transfer_policy']}\n"
        f"harmonic_guidance: {data['harmonic_guidance']}\n"
        f"rhythmic_guidance: {data['rhythmic_guidance']}\n"
        f"melodic_guidance: {data['melodic_guidance']}\n"
        f"form_guidance: {data['form_guidance']}\n"
        f"instrumentation: {data['instrumentation']}\n"
        f"instrument_requests: {instrument_requests}\n"
        f"instrument_requests_json: {json.dumps(instrument_requests, separators=(',', ':'))}\n"
        f"timbre_traits: {data['timbre_traits']}\n"
        f"forbidden_traits: {data['forbidden_traits']}\n"
        f"uncertainty_notes: {data['uncertainty_notes']}\n"
        "Use the structured brief as constraints. Preserve existing SongState output."
    )


def _prompt_safe_instrument_requests(instrument_requests: dict[str, Any]) -> dict[str, Any]:
    sanitized = deepcopy(instrument_requests)
    for payload in sanitized.values():
        if not isinstance(payload, dict):
            continue
        note_pack = payload.pop("note_pack", None)
        if not isinstance(note_pack, dict):
            continue
        note_pack_id = str(payload.get("note_pack_id") or note_pack.get("pack_id") or "")
        intent = payload.get("intent")
        reference_id = str(intent.get("reference_id") or "") if isinstance(intent, dict) else ""
        register_literal_note_pack(
            reference_id=reference_id,
            note_pack_id=note_pack_id,
            note_pack=note_pack,
        )
    return sanitized


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
