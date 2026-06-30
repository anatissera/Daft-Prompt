"""Composition graphs.

Phase 4: one-shot fan-out via `build_graph` / `run_instruments`.
Phase 5: full negotiation via `_build_negotiation_graph` / `run_negotiation` /
         `iter_negotiation_events`.

The negotiation graph structure:
  START → director → instruments (subgraph) → check_convergence
        → next_round → instruments (loop)
        → arbiter → END

The instruments subgraph groups all parallel instrument_turn nodes so they
appear as a single collapsed unit in LangSmith traces.
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
from .state import BandState, InstrumentsState, merge_parts, merge_requests, take_latest

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
#   START -> director
#   director -> instruments (subgraph, round 0 — all instruments compose)
#   instruments -> check_convergence
#   check_convergence -> next_round  if requests pending and round cap not reached
#                     -> arbiter     otherwise
#   next_round -> instruments (subsequent round — only addressed instruments)
#   arbiter -> END


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


def _build_instruments_subgraph(llm=None):
    """Subgraph that runs one round of instrument turns in parallel.

    On round 0 all roster instruments compose from scratch.
    On subsequent rounds only instruments addressed by pending requests get a turn.
    """

    def _dispatch_instruments(state: InstrumentsState) -> list[Send]:
        if state["round"] == 0:
            return [
                Send(
                    "instrument_turn",
                    {
                        "header": state["header"], "roster_item": r,
                        "roster": state["roster"], "peer_summaries": {},
                        "pending": [], "existing_part": None, "round": 0,
                    },
                )
                for r in state["roster"]
            ]
        pending = [r for r in state["negotiation_requests"] if r.status == "pending"]
        roster_by_id = {r.id: r for r in state["roster"]}
        peer_summaries = {
            rid: p.notes_summary for rid, p in state["parts"].items() if p.notes_summary
        }
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
                    "pending": reqs, "existing_part": state["parts"].get(to_id),
                    "round": state["round"],
                },
            )
            for to_id, reqs in pending_by_to.items()
            if to_id in roster_by_id
        ]

    def _instrument_turn_node(payload: _TurnPayload) -> dict:
        try:
            part, resolutions, new_requests = run_instrument_turn(
                payload["header"], payload["roster_item"], payload["roster"],
                payload["peer_summaries"], payload["pending"], payload["existing_part"], llm=llm,
            )
            updates = _resolutions_to_updates(payload["pending"], resolutions)
            updates += _new_requests_to_pending(
                payload["roster_item"].id, payload["round"], new_requests
            )
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
        return {
            "parts": {payload["roster_item"].id: part},
            "negotiation_requests": updates,
            "round": payload["round"],
        }

    subgraph = StateGraph(InstrumentsState)
    subgraph.add_node("instrument_turn", _instrument_turn_node)
    subgraph.add_conditional_edges(START, _dispatch_instruments, ["instrument_turn"])
    subgraph.add_edge("instrument_turn", END)
    return subgraph.compile()


def _build_negotiation_graph(llm=None, max_rounds: int = 3):
    instruments = _build_instruments_subgraph(llm=llm)

    def _director_node(state: BandState) -> dict:
        from .agents.director import run_director
        song = run_director(state["request"], llm=llm)
        return {"header": song.header, "roster": song.roster}

    def _next_round(state: BandState) -> dict:
        return {"round": state["round"] + 1}

    def _check_convergence(state: BandState):
        pending = [r for r in state["negotiation_requests"] if r.status == "pending"]
        if not pending or state["round"] + 1 >= max_rounds:
            return "arbiter"
        return "next_round"

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
    graph.add_node("next_round", _next_round)
    graph.add_node("arbiter", _arbiter_node)
    graph.add_edge(START, "director")
    graph.add_edge("director", "instruments")
    graph.add_conditional_edges("instruments", _check_convergence, ["next_round", "arbiter"])
    graph.add_edge("next_round", "instruments")
    graph.add_edge("arbiter", END)
    return graph.compile()


def run_negotiation(style: str, llm=None, max_rounds: Optional[int] = None) -> SongState:
    """Compose + negotiate: director sets the arrangement, then instruments compose
    (round 0) and revise across bounded rounds, until convergence or the round cap
    hits and the arbiter force-resolves whatever is left.
    """
    rounds = max_rounds if max_rounds is not None else get_settings().max_rounds
    app = _build_negotiation_graph(llm=llm, max_rounds=rounds)
    result = app.invoke(
        {
            "request": style, "header": None, "roster": [],
            "parts": {}, "negotiation_requests": [], "round": 0, "converged": False,
        },
        config={"recursion_limit": 4 * rounds + 10},
    )
    return SongState(
        request=style,
        header=result["header"],
        roster=result["roster"],
        parts=result.get("parts", {}),
        negotiation_requests=result.get("negotiation_requests", []),
        round=result.get("round", 0),
        converged=result.get("converged", True),
    )


def iter_negotiation_events(
    style: str, llm=None, max_rounds: Optional[int] = None
) -> Iterator[tuple[dict, Optional[SongState]]]:
    """Same run as `run_negotiation` but streaming: yields `(event, song_snapshot)`
    pairs. The first pair carries a `SongState` built from the director's output;
    subsequent pairs carry `None` (the same object is mutated in place).

    Uses `subgraphs=True` so instrument_turn events inside the instruments
    subgraph are surfaced alongside parent-graph events.
    """
    rounds = max_rounds if max_rounds is not None else get_settings().max_rounds
    app = _build_negotiation_graph(llm=llm, max_rounds=rounds)
    state: dict = {
        "request": style, "header": None, "roster": [],
        "parts": {}, "negotiation_requests": [], "round": 0, "converged": False,
    }
    song: Optional[SongState] = None

    stream = app.stream(
        state,
        config={"recursion_limit": 4 * rounds + 10},
        stream_mode="updates",
        subgraphs=True,
    )
    for ns, chunk in stream:
        for node, update in chunk.items():
            if not update:
                continue

            # Sync shared state fields
            if "parts" in update:
                state["parts"] = merge_parts(state["parts"], update["parts"])
            if "negotiation_requests" in update:
                state["negotiation_requests"] = merge_requests(
                    state["negotiation_requests"], update["negotiation_requests"]
                )
            if "round" in update:
                state["round"] = take_latest(state["round"], update["round"])
            if "converged" in update:
                state["converged"] = update["converged"]
            if "header" in update:
                state["header"] = update["header"]
            if "roster" in update:
                state["roster"] = update["roster"]

            if node == "director" and not ns:
                song = SongState(
                    request=style,
                    header=update["header"],
                    roster=update["roster"],
                    parts={},
                )
                yield {
                    "type": "director",
                    "source": "director",
                    "header": update["header"].model_dump(mode="json"),
                    "roster": [r.model_dump(mode="json") for r in update["roster"]],
                }, song

            elif node == "instrument_turn" and ns and song is not None:
                song.parts = state["parts"]
                song.negotiation_requests = state["negotiation_requests"]
                song.round = state["round"]
                instrument_id = next(iter(update["parts"]))
                reqs = update.get("negotiation_requests", [])
                yield {
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
                }, None

            elif node == "arbiter" and not ns and song is not None:
                song.converged = True
                song.negotiation_requests = state["negotiation_requests"]
                yield {
                    "type": "convergence",
                    "round": state["round"],
                    "converged": True,
                    "resolved_requests": [
                        r.model_dump(by_alias=True)
                        for r in update.get("negotiation_requests", [])
                    ],
                }, None

    if song is not None:
        song.parts = state["parts"]
        song.negotiation_requests = state["negotiation_requests"]
        song.round = state["round"]
        song.converged = state["converged"]
