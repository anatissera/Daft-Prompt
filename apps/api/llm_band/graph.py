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

from typing import Iterator, Optional, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

from .agents.arbiter import run_arbiter
from .agents.instrument import NewRequest, RequestResolution, compose_part, run_instrument_turn
from .config import get_settings
from .domain.song_state import CompositionGroup, Header, NegotiationRequest, Part, RosterItem, SongState
from .state import BandState, InstrumentsState, merge_parts, merge_requests, merge_summaries, take_latest


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
        part = compose_part(
            payload["header"], payload["roster_item"], payload["roster"],
            payload["peer_summaries"], llm=llm,
        )
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
    result = app.invoke({
        "request": song.request,
        "header": song.header,
        "roster": song.roster,
        "parts": dict(song.parts),
        "composition_groups": song.composition_groups,
        "current_group_index": 0,
        "batch_instrument_ids": [],
        "max_negotiation_rounds": 0,
        "negotiation_requests": [],
        "round": 0,
        "converged": False,
        "peer_summaries": {},
    })
    song.parts = result["parts"]
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
            targets = [(r, []) for r in state["roster"] if r.id in batch_ids]
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
        part, resolutions, new_requests = run_instrument_turn(
            payload["header"], payload["roster_item"], payload["roster"],
            payload["peer_summaries"], payload["batch_peer_ids"],
            payload["pending"], payload["existing_part"], llm=llm,
        )
        batch_ids = set(payload["batch_peer_ids"]) | {payload["roster_item"].id}
        updates = _resolutions_to_updates(payload["pending"], resolutions)
        all_new = _new_requests_to_pending(payload["roster_item"].id, payload["round"], new_requests)
        # Scope: only intra-batch requests are dispatched; cross-batch ones survive
        # to be resolved by the arbiter at the end.
        updates += all_new  # keep all (arbiter handles orphans)
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
        first_group = song.composition_groups[0] if song.composition_groups else None
        return {
            "header": song.header,
            "roster": song.roster,
            "composition_groups": song.composition_groups,
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
        resolved = run_arbiter(pending, llm=llm) if pending else []
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
    }


def run_negotiation(style: str, llm=None, max_rounds: Optional[int] = None) -> SongState:
    """Compose + negotiate via the batch sequencer."""
    settings_rounds = max_rounds if max_rounds is not None else get_settings().max_rounds
    app = _build_negotiation_graph(llm=llm, max_rounds=max_rounds)
    result = app.invoke(
        _initial_band_state(style),
        config={"recursion_limit": 4 * settings_rounds * 8 + 20},
    )
    return SongState(
        request=style,
        header=result["header"],
        roster=result["roster"],
        parts=result.get("parts", {}),
        composition_groups=result.get("composition_groups", []),
        negotiation_requests=result.get("negotiation_requests", []),
        round=result.get("round", 0),
        converged=result.get("converged", True),
    )


def iter_negotiation_events(
    style: str, llm=None, max_rounds: Optional[int] = None
) -> Iterator[tuple[dict, Optional[SongState]]]:
    """Same run as `run_negotiation` but streaming events."""
    settings_rounds = max_rounds if max_rounds is not None else get_settings().max_rounds
    app = _build_negotiation_graph(llm=llm, max_rounds=max_rounds)
    state: dict = _initial_band_state(style)
    song: Optional[SongState] = None

    stream = app.stream(
        state,
        config={"recursion_limit": 4 * settings_rounds * 8 + 20},
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
