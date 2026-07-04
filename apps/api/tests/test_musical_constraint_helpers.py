from __future__ import annotations

from music_assistant.domain.song_state import ChordSpan, Header, Note, RosterItem
from music_assistant.music.constraints import (
    bass_pattern_from_chords,
    chord_voicing,
    melody_constraint_summary,
    synth_timbre_constraints,
)
from music_assistant.agents.instrument import _instrument_intro


def test_bass_pattern_uses_roots_register_and_kick_relationship():
    header = Header(
        genre="funk",
        key="A minor",
        tempo_bpm=112,
        num_bars=2,
        chord_progression=[ChordSpan(bar=0, chord="Am"), ChordSpan(bar=1, chord="F")],
    )

    notes = bass_pattern_from_chords(header, register=(28, 55), density="medium")

    assert [note.bar for note in notes] == [0, 0, 1, 1]
    assert all(28 <= note.pitch <= 55 for note in notes if note.pitch is not None)
    assert all(note.start_beat in {0.0, 2.0} for note in notes)


def test_chord_voicing_respects_register_and_density():
    sparse = chord_voicing("Am7", register=(48, 72), density="sparse")
    dense = chord_voicing("Am7", register=(48, 72), density="dense")

    assert len(sparse) == 3
    assert len(dense) >= len(sparse)
    assert all(48 <= pitch <= 72 for pitch in dense)


def test_melody_constraints_describe_scale_range_repetition_and_resolution():
    summary = melody_constraint_summary(key="A minor", register=(60, 76), motif="rising three-note hook")

    assert "A minor" in summary
    assert "60-76" in summary
    assert "rising three-note hook" in summary
    assert "resolve" in summary.lower()


def test_synth_timbre_constraints_are_structured_even_with_gm_playback():
    traits = synth_timbre_constraints("warm pad", density="low")

    assert traits["role"] == "warm pad"
    assert traits["waveform_family"]
    assert traits["playback_note"].startswith("General MIDI")


def test_instrument_intro_includes_role_specific_constraints():
    bass = RosterItem(id="bass", instrument="Electric Bass", midi_range=(28, 55), role="bass groove")
    synth = RosterItem(id="pad", instrument="Synth Pad", midi_range=(48, 84), role="warm pad texture")

    bass_intro = _instrument_intro(bass)
    synth_intro = _instrument_intro(synth)

    assert "Constraint hints" in bass_intro
    assert "root motion" in bass_intro.lower()
    assert "timbre" in synth_intro.lower()
