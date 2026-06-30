"""Chord-symbol parsing and active-chord lookup used by harmony validation."""

from __future__ import annotations

from music_assistant.domain.song_state import ChordSpan
from music_assistant.music.theory import (
    active_chord_at,
    chord_pitch_classes,
    chord_tone_names,
    in_key,
)


def test_chord_pitch_classes_common_symbols():
    assert chord_pitch_classes("Em7") == frozenset({4, 7, 11, 2})
    assert chord_pitch_classes("Cmaj7") == frozenset({0, 4, 7, 11})
    assert chord_pitch_classes("C") == frozenset({0, 4, 7})


def test_chord_pitch_classes_handles_flats():
    # LLMs write 'Bb'; music21 wants 'B-'. Normalization must bridge that.
    assert chord_pitch_classes("Bb") == frozenset({10, 2, 5})
    assert chord_pitch_classes("Abmaj7") == frozenset({8, 0, 3, 7})


def test_chord_pitch_classes_unknown_is_empty():
    # empty / N.C. / garbage → empty set so callers treat it as "don't flag".
    assert chord_pitch_classes("") == frozenset()
    assert chord_pitch_classes("N.C.") == frozenset()
    assert chord_pitch_classes("not-a-chord") == frozenset()


def test_chord_tone_names_for_prompt_guidance():
    assert chord_tone_names("Em7") == ("E", "G", "B", "D")
    assert chord_tone_names("Bb") == ("Bb", "D", "F")
    assert chord_tone_names("") == ()
    assert chord_tone_names("N.C.") == ()


def test_active_chord_at_picks_most_recent_span():
    prog = [ChordSpan(bar=0, chord="Em7"), ChordSpan(bar=4, chord="Am7"),
            ChordSpan(bar=8, chord="G7")]
    assert active_chord_at(0, prog) == "Em7"
    assert active_chord_at(3, prog) == "Em7"
    assert active_chord_at(4, prog) == "Am7"
    assert active_chord_at(10, prog) == "G7"


def test_active_chord_at_returns_none_when_uncovered():
    assert active_chord_at(0, []) is None
    assert active_chord_at(0, [ChordSpan(bar=2, chord="C")]) is None


def test_secondary_dominant_tone_is_in_chord_but_out_of_key():
    # G# (pc 8) is the 3rd of E7 but not in E minor — the case chord-awareness fixes.
    assert 8 in chord_pitch_classes("E7")
    assert not in_key(56, "E minor")  # 56 % 12 == 8
