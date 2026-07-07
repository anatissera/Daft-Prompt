"""LangGraph state schema for the composition pipeline."""

from __future__ import annotations

from typing import Annotated, Optional, TypedDict

from .domain.song_state import CompositionGroup, Header, NegotiationRequest, Part, RosterItem


def merge_parts(left: dict[str, Part], right: dict[str, Part]) -> dict[str, Part]:
    merged = dict(left)
    merged.update(right)
    return merged


def merge_summaries(left: dict[str, str], right: dict[str, str]) -> dict[str, str]:
    merged = dict(left)
    merged.update(right)
    return merged


def merge_errors(left: list[str], right: list[str]) -> list[str]:
    merged = list(left)
    for item in right:
        if item not in merged:
            merged.append(item)
    return merged


def merge_requests(
    left: list[NegotiationRequest], right: list[NegotiationRequest]
) -> list[NegotiationRequest]:
    """Merge by id: a later entry with the same id replaces the earlier one."""
    by_id = {r.id: r for r in left}
    for r in right:
        by_id[r.id] = r
    return list(by_id.values())


def take_latest(_left: int, right: int) -> int:
    return right


class BandState(TypedDict):
    request: str
    header: Optional[Header]
    roster: list[RosterItem]
    composition_groups: list[CompositionGroup]
    current_group_index: int
    batch_instrument_ids: list[str]
    max_negotiation_rounds: int
    parts: Annotated[dict[str, Part], merge_parts]
    negotiation_requests: Annotated[list[NegotiationRequest], merge_requests]
    round: Annotated[int, take_latest]
    converged: bool
    peer_summaries: Annotated[dict[str, str], merge_summaries]
    errors: Annotated[list[str], merge_errors]


class InstrumentsState(TypedDict):
    """Shares keys with BandState so LangGraph passes state between parent and subgraph automatically."""
    header: Optional[Header]
    roster: list[RosterItem]
    batch_instrument_ids: list[str]
    max_negotiation_rounds: int
    parts: Annotated[dict[str, Part], merge_parts]
    negotiation_requests: Annotated[list[NegotiationRequest], merge_requests]
    round: Annotated[int, take_latest]
    peer_summaries: Annotated[dict[str, str], merge_summaries]
    errors: Annotated[list[str], merge_errors]
