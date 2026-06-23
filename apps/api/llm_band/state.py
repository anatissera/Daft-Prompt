"""LangGraph state schema for the composition pipeline.

Kept separate from `SongState` (the Pydantic I/O contract): this is the graph's
internal working state. `parts` and `negotiation_requests` are written by
multiple nodes in parallel during fan-out, so both carry merge reducers instead
of the last-write-wins default.
"""

from __future__ import annotations

from typing import Annotated, TypedDict

from .schema import Header, NegotiationRequest, Part, RosterItem


def merge_parts(left: dict[str, Part], right: dict[str, Part]) -> dict[str, Part]:
    merged = dict(left)
    merged.update(right)
    return merged


def merge_requests(
    left: list[NegotiationRequest], right: list[NegotiationRequest]
) -> list[NegotiationRequest]:
    """Merge by id: a later entry with the same id (e.g. a status update from
    'pending' to 'resolved'/'declined') replaces the earlier one; new ids append."""
    by_id = {r.id: r for r in left}
    for r in right:
        by_id[r.id] = r
    return list(by_id.values())


def take_latest(_left: int, right: int) -> int:
    """All Sends within one negotiation round write the same round number — a
    plain int field would reject the second write as a conflicting update even
    though the values agree, so it still needs an explicit (trivial) reducer."""
    return right


class BandState(TypedDict):
    header: Header
    roster: list[RosterItem]
    parts: Annotated[dict[str, Part], merge_parts]
    negotiation_requests: Annotated[list[NegotiationRequest], merge_requests]
    round: Annotated[int, take_latest]
    converged: bool
