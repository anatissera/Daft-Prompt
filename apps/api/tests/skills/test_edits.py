"""Pure-function tests for apply_edits."""

from __future__ import annotations

from llm_band.domain.song_state import Note, Part
from llm_band.skills.edits import NoteEdit, apply_edits


def _part(*notes: Note) -> Part:
    return Part(instrument_id="x", notes=list(notes), notes_summary="initial")


def _note(bar: int, beat: float, pitch: int = 60) -> Note:
    return Note(bar=bar, start_beat=beat, pitch=pitch, dur=1.0)


def test_add_inserts_note_and_sorts():
    part = _part(_note(2, 0.0))
    edits = [NoteEdit(op="add", bar=0, start_beat=0.0, note=_note(0, 0.0, pitch=48))]
    out, fails = apply_edits(part, edits)
    assert fails == []
    assert [(n.bar, n.start_beat, n.pitch) for n in out.notes] == [(0, 0.0, 48), (2, 0.0, 60)]
    assert out.version == part.version + 1


def test_replace_overwrites_matched_note():
    part = _part(_note(0, 1.0, pitch=60))
    edits = [NoteEdit(op="replace", bar=0, start_beat=1.0, note=_note(0, 1.0, pitch=64))]
    out, fails = apply_edits(part, edits)
    assert fails == []
    assert out.notes[0].pitch == 64


def test_remove_drops_matched_note():
    part = _part(_note(0, 0.0), _note(0, 1.0))
    edits = [NoteEdit(op="remove", bar=0, start_beat=0.0)]
    out, fails = apply_edits(part, edits)
    assert fails == []
    assert [(n.bar, n.start_beat) for n in out.notes] == [(0, 1.0)]


def test_remove_with_no_match_is_reported_not_raised():
    part = _part(_note(0, 0.0))
    edits = [NoteEdit(op="remove", bar=3, start_beat=2.0)]
    out, fails = apply_edits(part, edits)
    assert out.notes == part.notes
    assert len(fails) == 1 and "no note" in fails[0].reason


def test_replace_with_no_match_is_reported_not_raised():
    part = _part(_note(0, 0.0))
    edits = [NoteEdit(op="replace", bar=1, start_beat=0.0, note=_note(1, 0.0, pitch=72))]
    out, fails = apply_edits(part, edits)
    assert out.notes == part.notes
    assert len(fails) == 1


def test_add_into_occupied_slot_is_reported():
    part = _part(_note(0, 0.0))
    edits = [NoteEdit(op="add", bar=0, start_beat=0.0, note=_note(0, 0.0, pitch=72))]
    out, fails = apply_edits(part, edits)
    assert out.notes == part.notes
    assert len(fails) == 1 and "already occupies" in fails[0].reason


def test_remove_then_add_at_same_slot_succeeds():
    part = _part(_note(0, 0.0, pitch=60))
    edits = [
        NoteEdit(op="remove", bar=0, start_beat=0.0),
        NoteEdit(op="add", bar=0, start_beat=0.0, note=_note(0, 0.0, pitch=64)),
    ]
    out, fails = apply_edits(part, edits)
    assert fails == []
    assert [n.pitch for n in out.notes] == [64]


def test_add_then_remove_at_same_slot_yields_empty():
    part = _part()
    edits = [
        NoteEdit(op="add", bar=0, start_beat=0.0, note=_note(0, 0.0, pitch=60)),
        NoteEdit(op="remove", bar=0, start_beat=0.0),
    ]
    out, fails = apply_edits(part, edits)
    assert fails == []
    assert out.notes == []


def test_match_tolerates_floating_point_drift():
    part = _part(_note(0, 1.0))
    edits = [NoteEdit(op="remove", bar=0, start_beat=1.0 + 1e-5)]
    out, fails = apply_edits(part, edits)
    assert fails == [] and out.notes == []


def test_match_rejects_distant_start_beat():
    part = _part(_note(0, 1.0))
    edits = [NoteEdit(op="remove", bar=0, start_beat=1.5)]
    _, fails = apply_edits(part, edits)
    assert len(fails) == 1


def test_add_or_replace_without_note_payload_is_reported():
    part = _part(_note(0, 0.0))
    edits = [
        NoteEdit(op="add", bar=1, start_beat=0.0, note=None),
        NoteEdit(op="replace", bar=0, start_beat=0.0, note=None),
    ]
    out, fails = apply_edits(part, edits)
    assert out.notes == part.notes
    assert len(fails) == 2
    assert all("requires note payload" in f.reason for f in fails)


def test_bar_past_num_bars_is_dropped_when_num_bars_provided():
    part = _part(_note(0, 0.0))
    edits = [NoteEdit(op="add", bar=8, start_beat=0.0, note=_note(8, 0.0, pitch=60))]
    out, fails = apply_edits(part, edits, num_bars=4)
    assert out.notes == part.notes
    assert len(fails) == 1 and "past song length" in fails[0].reason


def test_apply_edits_is_pure():
    original = _part(_note(0, 0.0, pitch=60))
    edits = [NoteEdit(op="replace", bar=0, start_beat=0.0, note=_note(0, 0.0, pitch=72))]
    out, _ = apply_edits(original, edits)
    # source part untouched
    assert original.notes[0].pitch == 60
    assert original.version == 1
    assert out is not original


def test_edit_payload_pitch_wins_even_if_bar_or_start_beat_differ():
    # Agents sometimes set the note payload's bar/start_beat to the source's
    # values rather than the target's; apply_edits should still anchor to the
    # edit's (bar, start_beat).
    part = _part(_note(0, 0.0))
    edits = [NoteEdit(
        op="replace", bar=0, start_beat=0.0,
        note=Note(bar=3, start_beat=2.5, pitch=72, dur=1.0),
    )]
    out, fails = apply_edits(part, edits)
    assert fails == []
    assert (out.notes[0].bar, out.notes[0].start_beat, out.notes[0].pitch) == (0, 0.0, 72)
