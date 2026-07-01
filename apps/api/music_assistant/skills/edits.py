"""Diff-based revision helpers.

An instrument's revision-round output ships as `list[NoteEdit]` instead of the
full note list — typically a handful of edits vs ~100 notes re-emitted per
turn. `apply_edits` is the pure function that materializes the new `Part`.

Unmatched edits (replace/remove with no target note) and out-of-bounds adds are
dropped rather than raising — reported as `EditFailure` records so the agent's
repair loop knows exactly what was ignored without crashing the run.
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

    Order matters: `remove` then `add` at the same slot lands the add on empty
    space; the reverse drops the add as a collision. `num_bars` clamps
    add/replace edits whose bar is past the song length so a runaway agent
    can't extend the song behind the director's back.

    Returned `Part` keeps the original `instrument_id`, bumps `version`, and
    inherits summary fields (callers overwrite `notes_summary` at the call
    site with the agent's new summary).
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
            if _match_index(notes, edit.bar, edit.start_beat) is not None:
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
