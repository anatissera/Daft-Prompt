"""LangGraph state schema for the composition pipeline.

Kept separate from `SongState` (the Pydantic I/O contract): this is the graph's
internal working state. `parts` is written by multiple instrument nodes in
parallel during fan-out, so it carries a merge reducer instead of the
last-write-wins default.
"""

from __future__ import annotations

from typing import Annotated, TypedDict

from .schema import Header, Part, RosterItem


def merge_parts(left: dict[str, Part], right: dict[str, Part]) -> dict[str, Part]:
    merged = dict(left)
    merged.update(right)
    return merged


class BandState(TypedDict):
    header: Header
    roster: list[RosterItem]
    parts: Annotated[dict[str, Part], merge_parts]
