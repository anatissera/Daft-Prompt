"""Pure-function tests for melody skill."""

from __future__ import annotations

from music_assistant.domain.song_state import ChordSpan
from music_assistant.music.theory import in_key
from music_assistant.skills.melody import melodic_contour


def _prog(*pairs: tuple[int, str]) -> list[ChordSpan]:
    return [ChordSpan(bar=b, chord=c) for b, c in pairs]


def test_contour_returns_density_notes_per_bar():
    notes = melodic_contour(
        _prog((0, "C"), (1, "G")), key="C major",
        midi_low=60, midi_high=84, density=2,
    )
    assert len(notes) == 4
    assert {n.bar for n in notes} == {0, 1}


def test_contour_stays_in_range():
    notes = melodic_contour(
        _prog((0, "C")), key="C major",
        midi_low=60, midi_high=72, density=4,
    )
    assert all(60 <= n.pitch <= 72 for n in notes)


def test_contour_stays_in_key():
    notes = melodic_contour(
        _prog((0, "C"), (1, "F"), (2, "G"), (3, "C")),
        key="C major", midi_low=60, midi_high=84, density=4,
    )
    assert all(in_key(n.pitch, "C major") for n in notes)


def test_contour_first_note_of_bar_is_chord_tone():
    notes = melodic_contour(
        _prog((0, "C"), (1, "G")), key="C major",
        midi_low=60, midi_high=84, density=2,
    )
    bar0_first = next(n for n in notes if n.bar == 0 and n.start_beat == 0)
    bar1_first = next(n for n in notes if n.bar == 1 and n.start_beat == 0)
    assert bar0_first.pitch % 12 in {0, 4, 7}  # C E G
    assert bar1_first.pitch % 12 in {7, 11, 2}  # G B D


def test_contour_empty_progression_yields_no_notes():
    assert melodic_contour([], "C major", 60, 84) == []


def test_contour_unparseable_chord_skips_bar():
    notes = melodic_contour(
        _prog((0, "C"), (1, "???")), key="C major",
        midi_low=60, midi_high=84, density=2,
    )
    assert {n.bar for n in notes} == {0}
