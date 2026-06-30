"""Pure-function tests for harmony skills."""

from __future__ import annotations

from llm_band.domain.song_state import Note
from llm_band.music.theory import in_key
from llm_band.skills.harmony import (
    fit_to_range,
    scale_degrees,
    transpose,
    voice_lead,
)


def test_scale_degrees_c_major_g7():
    out = scale_degrees("C major", "G7")
    assert out["scale"] == [0, 2, 4, 5, 7, 9, 11]
    assert set(out["chord_tones"]) == {7, 11, 2, 5}  # G B D F
    assert set(out["tensions"]).isdisjoint(out["chord_tones"])
    assert set(out["scale"]) == set(out["chord_tones"]) | set(out["tensions"])


def test_scale_degrees_unknown_key_yields_empty_scale():
    out = scale_degrees("???", "C")
    assert out["scale"] == []


def test_scale_degrees_no_chord_returns_empty_chord_tones():
    out = scale_degrees("C major")
    assert out["chord_tones"] == []
    assert out["tensions"] == out["scale"]


def test_transpose_shifts_pitch_and_passes_rests():
    notes = [
        Note(bar=0, start_beat=0, pitch=60, dur=1),
        Note(bar=0, start_beat=1, pitch=None, dur=1),
    ]
    out = transpose(notes, 2)
    assert [n.pitch for n in out] == [62, None]


def test_transpose_leaves_pitch_unchanged_on_overflow():
    notes = [Note(bar=0, start_beat=0, pitch=126, dur=1)]
    out = transpose(notes, 5)
    assert out[0].pitch == 126


def test_fit_to_range_octave_shifts_into_window():
    # C5 (72) into [40, 60] should land on C4 (60).
    assert fit_to_range(72, 40, 60) == 60
    # C2 (36) into [40, 60] should land on C3 (48).
    assert fit_to_range(36, 40, 60) == 48
    # E5 (76) into bass range [28, 55] should land on E3 (52).
    assert fit_to_range(76, 28, 55) == 52


def test_fit_to_range_handles_inverted_endpoints():
    assert fit_to_range(72, 60, 40) == 60


def test_voice_lead_minimal_motion_distinct_voices():
    # C major triad → F major triad. Closest minimal motion:
    # 60 (C) stays as C (still in F triad), 64 (E) → 65 (F), 67 (G) → 69 (A).
    out = voice_lead("F", [60, 64, 67], 48, 84)
    assert len(out) == len(set(out)) == 3
    assert sum(abs(a - b) for a, b in zip(out, [60, 64, 67])) <= 4


def test_voice_lead_returns_empty_on_unparseable_chord():
    assert voice_lead("not-a-chord", [60, 64, 67], 48, 84) == []


def test_voice_lead_respects_range():
    out = voice_lead("C", [60, 64, 67], 50, 70)
    assert all(50 <= p <= 70 for p in out)


def test_transposed_in_key_pitches_stay_in_key():
    # Transpose a C-major C scale up a whole step: should be all in D major.
    notes = [Note(bar=0, start_beat=i, pitch=60 + p, dur=0.25)
             for i, p in enumerate([0, 2, 4, 5, 7, 9, 11])]
    out = transpose(notes, 2)
    assert all(in_key(n.pitch, "D major") for n in out)
