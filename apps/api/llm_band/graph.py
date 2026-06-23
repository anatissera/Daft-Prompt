"""Phase 4: one-shot fan-out — one instrument node per roster entry, merged via a
LangGraph state reducer. No negotiation rounds yet (Phase 5): all instruments
compose in parallel from the header + role + peer roles, so `peer_summaries` is
empty on this first pass — the wiring exists for later phases to populate it
across rounds.
"""

from __future__ import annotations

from typing import TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

from .agents.instrument import compose_part
from .schema import Header, RosterItem, SongState
from .state import BandState


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
    result = app.invoke({"header": song.header, "roster": song.roster, "parts": dict(song.parts)})
    song.parts = result["parts"]
    return song
