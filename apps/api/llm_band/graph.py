"""Phase 4: one-shot fan-out — one instrument node per roster entry, merged via a
LangGraph state reducer. No negotiation rounds (see `run_negotiation` below for
Phase 5's round loop): all instruments compose in parallel from the header +
role + peer roles, so `peer_summaries` is empty on this first pass.
"""

from __future__ import annotations

from typing import Iterator, Optional, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

import logging

from .agents.arbiter import run_arbiter
from .agents.instrument import NewRequest, RequestResolution, compose_part, run_instrument_turn
from .config import get_settings
from .domain.song_state import Header, NegotiationRequest, Part, RosterItem, SongState
from .infrastructure.llm import LLMError
from .state import BandState, merge_parts, merge_requests, take_latest

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
    app = build_graph(llm=llm)
    result = app.invoke({"header": song.header, "roster": song.roster, "parts": dict(song.parts)})
    song.parts = result["parts"]
    return song


# ---- Phase 5: negotiation rounds -------------------------------------------
#
#   START -> [instrument_turn]* (round 0, fan-out to every instrument)
#   instrument_turn -> round_complete
#   round_complete -> {arbiter}                      if no requests are pending
#                   -> {[instrument_turn]*}           next round, fan-out to addressees
#                   -> {arbiter}                      if the round cap is hit
#   arbiter -> END
#
# Round 0 has no pending requests (nothing exists yet to negotiate about) but
# can still raise new ones; from round 1 on, only instruments with a pending
# request addressed to them get a turn — others' parts stay frozen, which is
# what makes "zero new requests" a reachable fixed point instead of every
# instrument re-rolling forever.


class _TurnPayload(TypedDict):
    header: Header
    roster_item: RosterItem
    roster: list[RosterItem]
    peer_summaries: dict[str, str]
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


def _dispatch_round0(state: BandState) -> list[Send]:
    return [
        Send(
            "instrument_turn",
            {
                "header": state["header"], "roster_item": r, "roster": state["roster"],
                "peer_summaries": {}, "pending": [], "existing_part": None, "round": 0,
            },
        )
        for r in state["roster"]
    ]


def _build_negotiation_graph(llm=None, max_rounds: int = 3):
    def _instrument_turn_node(payload: _TurnPayload) -> dict:
        try:
            part, resolutions, new_requests = run_instrument_turn(
                payload["header"], payload["roster_item"], payload["roster"],
                payload["peer_summaries"], payload["pending"], payload["existing_part"], llm=llm,
            )
            updates = _resolutions_to_updates(payload["pending"], resolutions)
            updates += _new_requests_to_pending(payload["roster_item"].id, payload["round"], new_requests)
        except (LLMError, Exception) as exc:  # noqa: BLE001 — keep negotiation alive on per-turn failure
            log.warning(
                "instrument %s turn failed (round %d): %s",
                payload["roster_item"].id, payload["round"], exc,
            )
            # Auto-decline pending requests for this instrument; salvage whatever part we had.
            part = payload["existing_part"] or _empty_part(payload["roster_item"], type(exc).__name__)
            updates = [
                r.model_copy(update={"status": "declined", "resolution": f"auto-declined: {type(exc).__name__}"})
                for r in payload["pending"]
            ]
        return {
            "parts": {payload["roster_item"].id: part},
            "negotiation_requests": updates,
            "round": payload["round"],
        }

    def _round_complete(_state: BandState) -> dict:
        return {}

    def _check_convergence(state: BandState):
        pending = [r for r in state["negotiation_requests"] if r.status == "pending"]
        if not pending:
            return "arbiter"  # fixed point: nothing left to negotiate about
        next_round = state["round"] + 1
        if next_round >= max_rounds:
            return "arbiter"  # round cap hit — force-converge whatever's left

        roster_by_id = {r.id: r for r in state["roster"]}
        peer_summaries = {rid: p.notes_summary for rid, p in state["parts"].items() if p.notes_summary}
        pending_by_to: dict[str, list[NegotiationRequest]] = {}
        for r in pending:
            pending_by_to.setdefault(r.to, []).append(r)

        return [
            Send(
                "instrument_turn",
                {
                    "header": state["header"], "roster_item": roster_by_id[to_id],
                    "roster": state["roster"],
                    "peer_summaries": {k: v for k, v in peer_summaries.items() if k != to_id},
                    "pending": reqs, "existing_part": state["parts"].get(to_id), "round": next_round,
                },
            )
            for to_id, reqs in pending_by_to.items()
            if to_id in roster_by_id
        ]

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
    graph.add_node("instrument_turn", _instrument_turn_node)
    graph.add_node("round_complete", _round_complete)
    graph.add_node("arbiter", _arbiter_node)
    graph.add_conditional_edges(START, _dispatch_round0, ["instrument_turn"])
    graph.add_edge("instrument_turn", "round_complete")
    graph.add_conditional_edges("round_complete", _check_convergence, ["instrument_turn", "arbiter"])
    graph.add_edge("arbiter", END)
    return graph.compile()


def run_negotiation(song: SongState, llm=None, max_rounds: Optional[int] = None) -> SongState:
    """Compose + negotiate: instruments compose (round 0), then revise across
    bounded rounds as they raise and resolve `negotiation_requests`, until a
    round produces nothing pending (early exit) or the round cap is hit (the
    arbiter then force-resolves whatever's left). `recursion_limit` is a hard
    backstop independent of the round-cap logic above.
    """
    if not song.roster:
        return song
    rounds = max_rounds if max_rounds is not None else get_settings().max_rounds
    app = _build_negotiation_graph(llm=llm, max_rounds=rounds)
    result = app.invoke(
        {
            "header": song.header, "roster": song.roster, "parts": dict(song.parts),
            "negotiation_requests": list(song.negotiation_requests), "round": 0, "converged": False,
        },
        config={"recursion_limit": 4 * rounds + 10},
    )
    song.parts = result["parts"]
    song.negotiation_requests = result["negotiation_requests"]
    song.round = result["round"]
    song.converged = result["converged"]
    return song


def iter_negotiation_events(song: SongState, llm=None, max_rounds: Optional[int] = None) -> Iterator[dict]:
    """Same negotiation run as `run_negotiation`, but yields one event dict per
    node execution (each parallel `instrument_turn` Send produces its own chunk
    under `stream_mode="updates"`, confirmed via a standalone smoke test) instead
    of blocking until the graph finishes. Keeps `song` synchronized after each
    update so callers can return partial results if the stream is interrupted.
    """
    if not song.roster:
        return
    rounds = max_rounds if max_rounds is not None else get_settings().max_rounds
    app = _build_negotiation_graph(llm=llm, max_rounds=rounds)
    state = {
        "header": song.header, "roster": song.roster, "parts": dict(song.parts),
        "negotiation_requests": list(song.negotiation_requests), "round": 0, "converged": False,
    }
    for chunk in app.stream(state, config={"recursion_limit": 4 * rounds + 10}, stream_mode="updates"):
        for node, update in chunk.items():
            if not update:
                continue
            if "parts" in update:
                state["parts"] = merge_parts(state["parts"], update["parts"])
            if "negotiation_requests" in update:
                state["negotiation_requests"] = merge_requests(state["negotiation_requests"], update["negotiation_requests"])
            if "round" in update:
                state["round"] = take_latest(state["round"], update["round"])
            if "converged" in update:
                state["converged"] = update["converged"]

            song.parts = state["parts"]
            song.negotiation_requests = state["negotiation_requests"]
            song.round = state["round"]
            song.converged = state["converged"]

            if node == "instrument_turn":
                instrument_id = next(iter(update["parts"]))
                reqs = update.get("negotiation_requests", [])
                yield {
                    "type": "agent_pass",
                    "round": update["round"],
                    "instrument_id": instrument_id,
                    "notes_summary": state["parts"][instrument_id].notes_summary,
                    "new_requests": [r.model_dump(by_alias=True) for r in reqs if r.status == "pending"],
                    "resolved_requests": [r.model_dump(by_alias=True) for r in reqs if r.status != "pending"],
                }
            elif node == "arbiter":
                yield {
                    "type": "convergence",
                    "round": state["round"],
                    "converged": True,
                    "resolved_requests": [r.model_dump(by_alias=True) for r in update.get("negotiation_requests", [])],
                }

    song.parts = state["parts"]
    song.negotiation_requests = state["negotiation_requests"]
    song.round = state["round"]
    song.converged = state["converged"]
