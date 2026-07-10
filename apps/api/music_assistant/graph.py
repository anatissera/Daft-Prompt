"""Composition graphs.

Phase 4: one-shot fan-out via `build_graph` / `run_instruments`.
Phase 5: batched sequential composition via `_build_negotiation_graph` /
         `run_negotiation` / `iter_negotiation_events`.

The batch sequencer graph:
  START -> director -> instruments (batch subgraph) -> check_convergence
        -> batch_next_round -> instruments (intra-batch loop)
        -> advance_batch -> instruments (next batch)
        -> arbiter -> END

`composition_groups` from the director define the ordered batches. Each batch
runs its instruments in parallel, mini-negotiates up to `max_negotiation_rounds`,
then advances to the next batch. Prior-batch peer summaries are visible to all
later batches via `peer_summaries` in the shared state.
"""

from __future__ import annotations

import logging
import time
from typing import Iterator, Optional, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

from .agents.arbiter import run_arbiter
from .agents.bandleader import BandleaderReviewOutput, run_bandleader_review
from .agents.instrument import NewRequest, RequestResolution, compose_part, run_instrument_turn
from .domain.song_state import Header, NegotiationRequest, Part, RosterItem, SongState
from .infrastructure.llm import LLMError
from .music.reference_materialization import literal_parts_from_request
from .state import BandState, InstrumentsState, merge_parts, merge_requests, merge_summaries, take_latest

log = logging.getLogger(__name__)


def _empty_part(roster_item: RosterItem, reason: str) -> Part:
    return Part(
        instrument_id=roster_item.id,
        version=0,
        notes=[],
        notes_summary=f"(failed to compose: {reason})",
        self_notes="",
    )


class _InstrumentPayload(TypedDict):
    header: Header
    roster_item: RosterItem
    roster: list[RosterItem]
    peer_summaries: dict[str, str]


def _dispatch(state: BandState) -> list[Send]:
    peer_summaries = {rid: p.notes_summary for rid, p in state["parts"].items() if p.notes_summary}
    return [
        Send(
            "instrument",
            {
                "header": state["header"],
                "roster_item": r,
                "roster": state["roster"],
                "peer_summaries": peer_summaries,
            },
        )
        for r in state["roster"]
        if r.id not in state["parts"]
    ]


def build_graph(llm=None):
    def _instrument_node(payload: _InstrumentPayload) -> dict:
        try:
            part = compose_part(
                payload["header"], payload["roster_item"], payload["roster"],
                payload["peer_summaries"], llm=llm,
            )
        except (LLMError, Exception) as exc:  # noqa: BLE001 — keep compose alive on per-part failure
            log.warning("instrument %s failed: %s", payload["roster_item"].id, exc)
            part = _empty_part(payload["roster_item"], type(exc).__name__)
        return {"parts": {payload["roster_item"].id: part}}

    graph = StateGraph(BandState)
    graph.add_node("instrument", _instrument_node)
    graph.add_conditional_edges(START, _dispatch, ["instrument"])
    graph.add_edge("instrument", END)
    return graph.compile()


def run_instruments(song: SongState, llm=None) -> SongState:
    """Compose all roster parts in one shot and merge them onto `song`."""
    if not song.roster:
        return song
    literal_parts, literal_warnings = literal_parts_from_request(
        song.request, song.header, song.roster, include_warnings=True
    )
    app = build_graph(llm=llm)
    result = app.invoke({
        "request": song.request,
        "header": song.header,
        "roster": song.roster,
        "parts": {**dict(song.parts), **literal_parts},
        "composition_groups": song.composition_groups,
        "current_group_index": 0,
        "batch_instrument_ids": [],
        "max_negotiation_rounds": 0,
        "negotiation_requests": [],
        "round": 0,
        "converged": False,
        "peer_summaries": {part_id: part.notes_summary for part_id, part in literal_parts.items() if part.notes_summary},
        "errors": list(song.errors) + literal_warnings,
    })
    song.parts = result["parts"]
    song.errors = result.get("errors", [])
    return song


# ---- Phase 5: batch sequencer -----------------------------------------------


class _TurnPayload(TypedDict):
    header: Header
    roster_item: RosterItem
    roster: list[RosterItem]
    peer_summaries: dict[str, str]
    batch_peer_ids: list[str]
    pending: list[NegotiationRequest]
    existing_part: Optional[Part]
    round: int


def _new_requests_to_pending(
    from_id: str, round_num: int, new_requests: list[NewRequest]
) -> list[NegotiationRequest]:
    return [
        NegotiationRequest(
            id=f"req_{round_num}_{from_id}_{i}",
            from_=from_id,
            to=nr.to,
            round=round_num,
            bars=nr.bars,
            request=nr.request,
            rationale=nr.rationale,
            status="pending",
        )
        for i, nr in enumerate(new_requests)
    ]


def _resolutions_to_updates(
    pending_for_self: list[NegotiationRequest], resolutions: list[RequestResolution]
) -> list[NegotiationRequest]:
    by_id = {r.id: r for r in pending_for_self}
    updates = []
    for res in resolutions:
        orig = by_id.get(res.request_id)
        if orig is None:
            continue
        status = "resolved" if res.accepted else "declined"
        updates.append(orig.model_copy(update={"status": status, "resolution": res.resolution}))
    return updates


def _build_instruments_subgraph(llm=None):
    """Subgraph: one round of instrument turns for the current batch.

    On round 0 all batch members compose. On subsequent rounds only instruments
    that have pending requests addressed to them get a turn.
    Requests raised to instruments outside the batch are silently dropped —
    they belong to the arbiter.
    """

    def _dispatch_instruments(state: InstrumentsState) -> list[Send]:
        batch_ids = set(state["batch_instrument_ids"])
        roster_by_id = {r.id: r for r in state["roster"]}
        peer_summaries = state.get("peer_summaries", {})

        if state["round"] == 0:
            targets = [(r, []) for r in state["roster"] if r.id in batch_ids and r.id not in state["parts"]]
        else:
            pending = [r for r in state["negotiation_requests"] if r.status == "pending" and r.to in batch_ids]
            pending_by_to: dict[str, list[NegotiationRequest]] = {}
            for r in pending:
                pending_by_to.setdefault(r.to, []).append(r)
            targets = [
                (roster_by_id[to_id], reqs)
                for to_id, reqs in pending_by_to.items()
                if to_id in roster_by_id
            ]

        return [
            Send(
                "instrument_turn",
                {
                    "header": state["header"],
                    "roster_item": r,
                    "roster": state["roster"],
                    "peer_summaries": {k: v for k, v in peer_summaries.items() if k != r.id},
                    "batch_peer_ids": [bid for bid in state["batch_instrument_ids"] if bid != r.id],
                    "pending": reqs,
                    "existing_part": state["parts"].get(r.id) if state["round"] > 0 else None,
                    "round": state["round"],
                },
            )
            for r, reqs in targets
        ]

    def _instrument_turn_node(payload: _TurnPayload) -> dict:
        try:
            part, resolutions, new_requests = run_instrument_turn(
                payload["header"], payload["roster_item"], payload["roster"],
                payload["peer_summaries"], payload["batch_peer_ids"],
                payload["pending"], payload["existing_part"], llm=llm,
            )
            updates = _resolutions_to_updates(payload["pending"], resolutions)
            all_new = _new_requests_to_pending(payload["roster_item"].id, payload["round"], new_requests)
            # All new requests are kept here. Dispatch scoping (only intra-batch requests
            # are dispatched within a batch) happens in _dispatch_instruments; cross-batch
            # requests survive and are resolved by the arbiter at the end.
            updates += all_new  # keep all (arbiter handles orphans)
        except (LLMError, Exception) as exc:  # noqa: BLE001 — keep negotiation alive on per-turn failure
            log.warning(
                "instrument %s turn failed (round %d): %s",
                payload["roster_item"].id, payload["round"], exc,
            )
            part = payload["existing_part"] or _empty_part(payload["roster_item"], type(exc).__name__)
            updates = [
                r.model_copy(update={"status": "declined", "resolution": f"auto-declined: {type(exc).__name__}"})
                for r in payload["pending"]
            ]
        new_summary = (
            {payload["roster_item"].id: part.notes_summary} if part.notes_summary else {}
        )
        return {
            "parts": {payload["roster_item"].id: part},
            "negotiation_requests": updates,
            "peer_summaries": new_summary,
            "round": payload["round"],
        }

    subgraph = StateGraph(InstrumentsState)
    subgraph.add_node("instrument_turn", _instrument_turn_node)
    subgraph.add_conditional_edges(START, _dispatch_instruments, ["instrument_turn"])
    subgraph.add_edge("instrument_turn", END)
    return subgraph.compile()


def _build_negotiation_graph(llm=None, max_rounds: Optional[int] = None):
    instruments = _build_instruments_subgraph(llm=llm)

    def _director_node(state: BandState) -> dict:
        from .agents.director import run_director
        song = run_director(state["request"], llm=llm)
        literal_parts, literal_warnings = literal_parts_from_request(
            state["request"], song.header, song.roster, include_warnings=True
        )
        first_group = song.composition_groups[0] if song.composition_groups else None
        return {
            "header": song.header,
            "roster": song.roster,
            "parts": literal_parts,
            "peer_summaries": {
                part_id: part.notes_summary
                for part_id, part in literal_parts.items()
                if part.notes_summary
            },
            "composition_groups": song.composition_groups,
            "errors": list(song.errors) + literal_warnings,
            "current_group_index": 0,
            "round": 0,
            "batch_instrument_ids": first_group.instrument_ids if first_group else [r.id for r in song.roster],
            "max_negotiation_rounds": (
                max_rounds
                if max_rounds is not None
                else (first_group.max_negotiation_rounds if first_group else 1)
            ),
        }

    def _batch_next_round(state: BandState) -> dict:
        return {"round": state["round"] + 1}

    def _advance_batch(state: BandState) -> dict:
        next_idx = state["current_group_index"] + 1
        next_group = state["composition_groups"][next_idx]
        return {
            "current_group_index": next_idx,
            "round": 0,
            "batch_instrument_ids": next_group.instrument_ids,
            "max_negotiation_rounds": (
                max_rounds if max_rounds is not None else next_group.max_negotiation_rounds
            ),
        }

    def _check_convergence(state: BandState):
        batch_ids = set(state["batch_instrument_ids"])
        current_max = state["max_negotiation_rounds"]
        pending = [
            r for r in state["negotiation_requests"]
            if r.status == "pending" and r.to in batch_ids
        ]
        # `max_negotiation_rounds` counts rounds AFTER the initial composition (round 0).
        # round 0 = compose; rounds 1..max = negotiate. Check: current round < max.
        if pending and state["round"] < current_max:
            return "batch_next_round"
        if state["current_group_index"] + 1 < len(state["composition_groups"]):
            return "advance_batch"
        return "arbiter"

    def _arbiter_node(state: BandState) -> dict:
        pending = [r for r in state["negotiation_requests"] if r.status == "pending"]
        if not pending:
            return {"negotiation_requests": [], "converged": True}
        try:
            resolved = run_arbiter(pending, llm=llm)
        except (LLMError, Exception) as exc:  # noqa: BLE001 — finalize compose even if arbiter LLM fails
            log.warning("arbiter failed, auto-declining %d pending request(s): %s", len(pending), exc)
            resolved = [
                r.model_copy(update={"status": "declined", "resolution": f"auto-declined: {type(exc).__name__}"})
                for r in pending
            ]
        return {"negotiation_requests": resolved, "converged": True}

    graph = StateGraph(BandState)
    graph.add_node("director", _director_node)
    graph.add_node("instruments", instruments)
    graph.add_node("batch_next_round", _batch_next_round)
    graph.add_node("advance_batch", _advance_batch)
    graph.add_node("arbiter", _arbiter_node)
    graph.add_edge(START, "director")
    graph.add_edge("director", "instruments")
    graph.add_conditional_edges(
        "instruments", _check_convergence,
        ["batch_next_round", "advance_batch", "arbiter"],
    )
    graph.add_edge("batch_next_round", "instruments")
    graph.add_edge("advance_batch", "instruments")
    graph.add_edge("arbiter", END)
    return graph.compile()


def _initial_band_state(request: str) -> dict:
    return {
        "request": request,
        "header": None,
        "roster": [],
        "composition_groups": [],
        "current_group_index": 0,
        "batch_instrument_ids": [],
        "max_negotiation_rounds": 1,
        "parts": {},
        "negotiation_requests": [],
        "round": 0,
        "converged": False,
        "peer_summaries": {},
        "errors": [],
    }


def run_negotiation(style: str, llm=None, max_rounds: Optional[int] = None) -> SongState:
    """Compose + negotiate via the batch sequencer."""
    rounds_for_limit = max_rounds if max_rounds is not None else 3
    app = _build_negotiation_graph(llm=llm, max_rounds=max_rounds)
    result = app.invoke(
        _initial_band_state(style),
        config={"recursion_limit": 4 * rounds_for_limit * 8 + 20},
    )
    song = SongState(
        request=style,
        header=result["header"],
        roster=result["roster"],
        parts=result.get("parts", {}),
        composition_groups=result.get("composition_groups", []),
        negotiation_requests=result.get("negotiation_requests", []),
        round=result.get("round", 0),
        converged=result.get("converged", True),
        errors=result.get("errors", []),
    )
    return _run_bandleader_rehearsal(song, llm=llm)


def _run_bandleader_rehearsal(song: SongState, llm=None) -> SongState:
    guitar_ids = [
        item.id
        for item in song.roster
        if item.id in song.parts and "guitar" in f"{item.id} {item.instrument} {item.role}".lower()
    ]
    if not guitar_ids:
        return song
    if llm is None:
        try:
            from music_assistant.infrastructure.gemini.llm import make_llm

            llm = make_llm("arbiter")
        except Exception as exc:  # noqa: BLE001 - review is advisory only
            log.info("bandleader review unavailable: %s", exc)
            return song
    try:
        review: BandleaderReviewOutput = run_bandleader_review(song, llm)
    except Exception as exc:  # noqa: BLE001 - review is advisory only
        log.info("bandleader review skipped: %s", exc)
        return song
    for request in review.revision_requests[:1]:
        if request.instrument_id not in guitar_ids:
            continue
        instruction = request.instruction.strip()
        if not instruction:
            continue
        try:
            revised = revise_instrument_part(song, instruction, request.instrument_id, llm=llm)
        except Exception as exc:  # noqa: BLE001 - keep first take if rehearsal fails
            log.warning("bandleader revision for %s failed: %s", request.instrument_id, exc)
            return song
        return revised.model_copy(
            update={
                "errors": [
                    *revised.errors,
                    f"bandleader requested {request.instrument_id}: {request.reason or instruction}",
                ]
            }
        )
    return song


def revise_instrument_part(
    song: SongState,
    instruction: str,
    instrument_id: str,
    llm=None,
) -> SongState:
    """Revise one existing generated part with the instrument revision agent."""
    roster_by_id = {item.id: item for item in song.roster}
    roster_item = roster_by_id[instrument_id]
    existing_part = song.parts[instrument_id]
    peer_summaries = {
        part_id: part.notes_summary
        for part_id, part in song.parts.items()
        if part_id != instrument_id and part.notes_summary
    }
    part, resolutions, new_requests = run_instrument_turn(
        song.header,
        roster_item,
        song.roster,
        peer_summaries,
        [item.id for item in song.roster if item.id != instrument_id],
        [],
        existing_part,
        llm=llm,
        revision_instruction=instruction,
    )
    updated_requests = [
        *song.negotiation_requests,
        *_new_requests_to_pending(instrument_id, song.round + 1, new_requests),
    ]
    updated_errors = list(song.errors)
    for resolution in resolutions:
        updated_errors.append(f"{instrument_id} revision resolved {resolution.request_id}: {resolution.resolution}")
    return song.model_copy(
        update={
            "request": instruction,
            "parts": {**song.parts, instrument_id: part},
            "negotiation_requests": updated_requests,
            "errors": updated_errors,
        }
    )


def iter_negotiation_events(
    style: str, llm=None, max_rounds: Optional[int] = None
) -> Iterator[tuple[dict, Optional[SongState]]]:
    """Same run as `run_negotiation` but streaming events."""
    rounds_for_limit = max_rounds if max_rounds is not None else 3
    app = _build_negotiation_graph(llm=llm, max_rounds=max_rounds)
    state: dict = _initial_band_state(style)
    song: Optional[SongState] = None
    started_at = time.monotonic()
    previous_event_at = started_at

    def with_timing(event: dict) -> dict:
        nonlocal previous_event_at
        now = time.monotonic()
        timed = {
            **event,
            "elapsed_seconds": round(now - started_at, 3),
            "stage_elapsed_seconds": round(now - previous_event_at, 3),
        }
        previous_event_at = now
        return timed

    stream = app.stream(
        state,
        config={"recursion_limit": 4 * rounds_for_limit * 8 + 20},
        stream_mode="updates",
        subgraphs=True,
    )
    for ns, chunk in stream:
        for node, update in chunk.items():
            if not update:
                continue

            if "parts" in update:
                state["parts"] = merge_parts(state["parts"], update["parts"])
            if "negotiation_requests" in update:
                state["negotiation_requests"] = merge_requests(
                    state["negotiation_requests"], update["negotiation_requests"]
                )
            if "peer_summaries" in update:
                state["peer_summaries"] = merge_summaries(
                    state.get("peer_summaries", {}), update["peer_summaries"]
                )
            if "errors" in update:
                state["errors"] = list(dict.fromkeys([*state.get("errors", []), *update["errors"]]))
            if "round" in update:
                state["round"] = take_latest(state["round"], update["round"])
            if "converged" in update:
                state["converged"] = update["converged"]
            if "header" in update:
                state["header"] = update["header"]
            if "roster" in update:
                state["roster"] = update["roster"]
            if "composition_groups" in update:
                state["composition_groups"] = update["composition_groups"]

            if node == "director" and not ns:
                song = SongState(
                    request=style,
                    header=update["header"],
                    roster=update["roster"],
                    parts=state["parts"],
                    errors=state["errors"],
                )
                yield with_timing({
                    "type": "director",
                    "source": "director",
                    "header": update["header"].model_dump(mode="json"),
                    "roster": [r.model_dump(mode="json") for r in update["roster"]],
                }), song

            elif node == "instrument_turn" and ns and song is not None:
                song.parts = state["parts"]
                song.negotiation_requests = state["negotiation_requests"]
                song.round = state["round"]
                instrument_id = next(iter(update["parts"]))
                reqs = update.get("negotiation_requests", [])
                yield with_timing({
                    "type": "agent_pass",
                    "round": update["round"],
                    "instrument_id": instrument_id,
                    "notes_summary": state["parts"][instrument_id].notes_summary,
                    "new_requests": [
                        r.model_dump(by_alias=True) for r in reqs if r.status == "pending"
                    ],
                    "resolved_requests": [
                        r.model_dump(by_alias=True) for r in reqs if r.status != "pending"
                    ],
                }), None

            elif node == "arbiter" and not ns and song is not None:
                song.converged = True
                song.negotiation_requests = state["negotiation_requests"]
                yield with_timing({
                    "type": "convergence",
                    "round": state["round"],
                    "converged": True,
                    "resolved_requests": [
                        r.model_dump(by_alias=True)
                        for r in update.get("negotiation_requests", [])
                    ],
                }), None

    if song is not None:
        song.parts = state["parts"]
        song.negotiation_requests = state["negotiation_requests"]
        song.round = state["round"]
        song.converged = state["converged"]
        song.errors = state["errors"]
