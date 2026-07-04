"""Diff-based revision helpers used by negotiation rounds (Phase 2 step 7).

An instrument's revision-round output ships as `list[NoteEdit]` instead of the
full note list — typically a handful of edits vs ~100 notes re-emitted per
turn. `apply_edits` is the pure function that materializes the new `Part`.

Unmatched edits (replace/remove with no note at the target bar/start_beat) and
out-of-bounds adds are dropped rather than raising. Drops are surfaced as
`EditFailure` records so the agent's repair loop can be told exactly what was
ignored without crashing the run — same never-crash contract as `compose_part`.
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

from ..domain.song_state import Note, Part

_MATCH_EPS = 1e-3


class NoteEdit(BaseModel):
    op: Literal["add", "replace", "remove"]
    bar: int = Field(ge=0)
    start_beat: float = Field(ge=0)
    note: Optional[Note] = Field(
        default=None,
        description="required for add/replace; the new note to insert/overwrite",
    )


class EditFailure(BaseModel):
    edit: NoteEdit
    reason: str


def _match_index(notes: list[Note], bar: int, start_beat: float) -> Optional[int]:
    """Index of the note at `(bar, start_beat)`, picking the closest start_beat
    within `_MATCH_EPS` when several notes share the bar. Returns None if no note
    is close enough — callers treat that as 'edit dropped'."""
    best: tuple[float, int] | None = None
    for i, n in enumerate(notes):
        if n.bar != bar:
            continue
        delta = abs(n.start_beat - start_beat)
        if delta > _MATCH_EPS:
            continue
        if best is None or delta < best[0]:
            best = (delta, i)
    return best[1] if best else None


def _ordered(notes: list[Note]) -> list[Note]:
    return sorted(notes, key=lambda n: (n.bar, n.start_beat))


def apply_edits(
    part: Part, edits: list[NoteEdit], num_bars: Optional[int] = None,
) -> tuple[Part, list[EditFailure]]:
    """Apply `edits` to `part` in order, returning the new `Part` and any drops.

    Order matters: a `remove` then `add` at the same target is allowed (the
    add lands on an empty slot); the reverse silently drops the add since it
    would collide. `num_bars` (if provided) lets us drop add/replace edits whose
    target bar is past the song length — keeps a runaway agent from extending
    the song behind the director's back.

    The returned `Part` keeps the original `instrument_id`, bumps `version`, and
    inherits the summary/notes fields from `part` (callers overwrite
    `notes_summary` with the agent's new summary at the call site).
    """
    notes = [n.model_copy() for n in part.notes]
    failures: list[EditFailure] = []

    for edit in edits:
        if num_bars is not None and edit.bar >= num_bars:
            failures.append(EditFailure(edit=edit, reason="bar past song length"))
            continue

        if edit.op == "add":
            if edit.note is None:
                failures.append(EditFailure(edit=edit, reason="add requires note payload"))
                continue
            collision = _match_index(notes, edit.bar, edit.start_beat)
            if collision is not None:
                failures.append(EditFailure(edit=edit, reason="another note already occupies that slot"))
                continue
            new_note = edit.note.model_copy(update={"bar": edit.bar, "start_beat": edit.start_beat})
            notes.append(new_note)

        elif edit.op == "replace":
            if edit.note is None:
                failures.append(EditFailure(edit=edit, reason="replace requires note payload"))
                continue
            idx = _match_index(notes, edit.bar, edit.start_beat)
            if idx is None:
                failures.append(EditFailure(edit=edit, reason="no note at target bar/start_beat"))
                continue
            notes[idx] = edit.note.model_copy(update={"bar": edit.bar, "start_beat": edit.start_beat})

        else:  # remove
            idx = _match_index(notes, edit.bar, edit.start_beat)
            if idx is None:
                failures.append(EditFailure(edit=edit, reason="no note at target bar/start_beat"))
                continue
            notes.pop(idx)

    new_part = part.model_copy(update={
        "notes": _ordered(notes),
        "version": part.version + 1,
    })
    return new_part, failures


__all__ = ["NoteEdit", "EditFailure", "apply_edits"]
