"""Composition application service."""

from __future__ import annotations

import logging
import json
import time
from copy import deepcopy
from collections.abc import Callable, Iterator
from typing import Any

from music_assistant.domain.audio_profile import CompositionBrief
from music_assistant.application.composition_reviewer import CompositionReview, CompositionReviewer
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
        reviewer: CompositionReviewer | None = None,
    ):
        self.llm_configured = llm_configured
        self.negotiator = negotiator
        self.event_streamer = event_streamer
        self.canned = canned
        self.instrument_reviser = instrument_reviser
        self.reviewer = reviewer
        self.last_review: CompositionReview | None = None

    def compose(self, style: str | CompositionBrief) -> tuple[SongState, str]:
        if not self.llm_configured():
            raise ComposeConfigurationError()
        prompt = _style_prompt(style)
        song = self.negotiator(prompt)
        return self._review_if_needed(style, song), "director"

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
        if song is not None:
            song = self._review_if_needed(style, song)
        yield {}, song, source

    def _review_if_needed(self, style: str | CompositionBrief, song: SongState) -> SongState:
        self.last_review = None
        if self.reviewer is None or not isinstance(style, CompositionBrief):
            return song
        try:
            review = self.reviewer.review(style, song)
        except Exception as exc:  # noqa: BLE001 - review must not discard a playable result
            song.errors.append(f"composition reviewer unavailable: {type(exc).__name__}")
            return song

        chosen = song
        chosen_review = review
        if any(issue.severity == "high" for issue in review.issues):
            revision_prompt = (
                f"{_style_prompt(style)}\n"
                "Final CompositionReviewer findings require one bounded correction pass:\n"
                + "\n".join(f"- {request}" for request in review.targeted_revision_requests)
                + "\nReturn a corrected complete SongState that preserves unaffected requested material."
            )
            try:
                candidate = self.negotiator(revision_prompt)
                candidate_review = self.reviewer.review(style, candidate)
                if _review_rank(candidate_review) < _review_rank(review):
                    chosen, chosen_review = candidate, candidate_review
            except Exception as exc:  # noqa: BLE001 - keep the original playable result
                review.user_warnings.append(f"A targeted composition revision was unavailable ({type(exc).__name__}).")

        if not chosen_review.accepted:
            warnings = chosen_review.user_warnings or [issue.message for issue in chosen_review.issues]
            chosen.errors.extend(f"Composition review: {warning}" for warning in warnings)
        self.last_review = chosen_review
        return chosen

    def revise_instrument(self, song: SongState, instruction: str, instrument_id: str) -> tuple[SongState, str]:
        if not self.llm_configured():
            raise ComposeConfigurationError()
        if self.instrument_reviser is None:
            raise ComposeConfigurationError()
        candidate = self.instrument_reviser(deepcopy(song), instruction, instrument_id)
        return _merge_targeted_revision(song, candidate, instrument_id), "director"


def _merge_targeted_revision(original: SongState, candidate: SongState, instrument_id: str) -> SongState:
    """Accept only the requested part from a revision candidate.

    Header, harmony, roster, peer parts, negotiation history, and the original
    request are composition identity. They cannot be changed by a one-part edit.
    """
    if instrument_id not in original.parts:
        raise ValueError(f"unknown instrument id: {instrument_id}")
    revised_part = candidate.parts.get(instrument_id, original.parts[instrument_id]).model_copy(
        update={"instrument_id": instrument_id}
    )
    return original.model_copy(
        deep=True,
        update={"parts": {**original.parts, instrument_id: revised_part}},
    )


def _review_rank(review: CompositionReview) -> tuple[int, int]:
    high = sum(issue.severity == "high" for issue in review.issues)
    return high, len(review.issues)


def prompt_from_composition_brief(brief: CompositionBrief) -> str:
    data = brief.model_dump(mode="json")
    instrument_requests = _prompt_safe_instrument_requests(data["instrument_requests"])
    playable_parts = _prompt_safe_playable_parts(data["playable_parts_to_preserve"])
    return (
        "CompositionBrief\n"
        f"user_request: {data['user_request']}\n"
        f"global_constraints: {data['global_constraints']}\n"
        f"fidelity_mode: {data['fidelity_mode']}\n"
        f"references_used: {data['references_used']}\n"
        f"transfer_policy: {data['transfer_policy']}\n"
        f"harmonic_guidance: {data['harmonic_guidance']}\n"
        f"rhythmic_guidance: {data['rhythmic_guidance']}\n"
        f"melodic_guidance: {data['melodic_guidance']}\n"
        f"form_guidance: {data['form_guidance']}\n"
        f"instrumentation: {data['instrumentation']}\n"
        f"reference_instrumentation: {data['reference_instrumentation']}\n"
        f"reference_instrumentation_json: {json.dumps(data['reference_instrumentation'], separators=(',', ':'))}\n"
        f"style_guardrails: {data['style_guardrails']}\n"
        f"style_guardrails_json: {json.dumps(data['style_guardrails'], separators=(',', ':'))}\n"
        f"instrument_requests: {instrument_requests}\n"
        f"instrument_requests_json: {json.dumps(instrument_requests, separators=(',', ':'))}\n"
        f"playable_parts_to_preserve: {playable_parts}\n"
        f"preservation_requests: {data['preservation_requests']}\n"
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


def _prompt_safe_playable_parts(parts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    sanitized: list[dict[str, Any]] = []
    for part in parts:
        if not isinstance(part, dict):
            continue
        item = {
            "part_id": part.get("part_id"),
            "kind": part.get("kind"),
            "instrument_family": part.get("instrument_family"),
            "title": part.get("title"),
            "summary": part.get("summary"),
            "source_name": part.get("source_name"),
            "source_url": part.get("source_url"),
            "confidence_label": part.get("confidence_label"),
        }
        tab = part.get("tab")
        if isinstance(tab, dict):
            item["tab"] = {
                "instrument": tab.get("instrument"),
                "tuning": tab.get("tuning"),
                "capo": tab.get("capo"),
                "measures": _prompt_safe_tab_measures(tab.get("measures") or []),
            }
        for key in ("chord_chart", "piano_keys", "piano_roll", "rhythm_grid", "rendering_notes"):
            value = part.get(key)
            if value:
                item[key] = value[:16] if isinstance(value, list) else value
        sanitized.append(item)
    return sanitized


def _prompt_safe_tab_measures(measures: list[Any]) -> list[dict[str, Any]]:
    safe: list[dict[str, Any]] = []
    for measure in measures[:4]:
        if not isinstance(measure, dict):
            continue
        events = measure.get("events") or []
        safe.append({
            "measure_number": measure.get("measure_number"),
            "start_bar": measure.get("start_bar"),
            "events": events[:16] if isinstance(events, list) else [],
        })
    return safe


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
