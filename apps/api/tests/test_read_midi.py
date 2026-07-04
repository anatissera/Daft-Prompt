"""Round-trip and extractor tests for the MIDI reader.

Round-trip is the correctness gate: SongState -> render_midi -> read_midi should
yield equivalent bar/beat/pitch content up to quantisation. Extractor tests use
hand-crafted `pretty_midi` objects so no MIDI files are shipped in the repo.
"""

from __future__ import annotations

from pathlib import Path

import pretty_midi
import pytest

from music_assistant.domain.song_state import (
    ChordSpan,
    Header,
    Note,
    Part,
    RosterItem,
    SongState,
)
from music_assistant.music.read_midi import (
    ReadNote,
    ReadSong,
    ReadTrack,
    extract_density_by_role,
    extract_drum_pattern,
    extract_key,
    extract_progression,
    pretty_midi_to_song,
    program_role,
    read_midi,
)
from music_assistant.music.render_midi import render_midi


def _song(*, key="C major", num_bars=4, tempo=120) -> SongState:
    return SongState(
        request="",
        header=Header(
            genre="test",
            key=key,
            tempo_bpm=tempo,
            time_signature=(4, 4),
            num_bars=num_bars,
            chord_progression=[ChordSpan(bar=b, chord="C") for b in range(num_bars)],
        ),
        roster=[
            RosterItem(id="bass", instrument="bass", midi_program=33, midi_range=(28, 55), is_drum=False),
            RosterItem(id="drums", instrument="drums", midi_program=0, midi_range=(35, 81), is_drum=True),
        ],
        parts={
            "bass": Part(
                instrument_id="bass",
                notes=[Note(bar=b, start_beat=0.0, pitch=48, dur=1.0, velocity=90) for b in range(num_bars)],
            ),
            "drums": Part(
                instrument_id="drums",
                notes=[
                    Note(bar=b, start_beat=beat, pitch=pitch, dur=0.25, velocity=100)
                    for b in range(num_bars)
                    for beat, pitch in [(0.0, 36), (1.0, 38), (2.0, 36), (3.0, 38)]
                ],
            ),
        },
    )


# ---------------------------------------------------------------------------
# Round-trip: render, read, equivalence
# ---------------------------------------------------------------------------


def test_round_trip_preserves_bars_beats_and_pitches(tmp_path: Path):
    song = _song(num_bars=4)
    mid = tmp_path / "rt.mid"
    render_midi(song, str(mid))

    read = read_midi(str(mid))
    assert read.tempo_bpm == pytest.approx(120.0, abs=0.5)
    assert read.time_signature == (4, 4)
    assert read.num_bars == 4

    bass = _pick_track(read, is_drum=False)
    assert len(bass.notes) == 4
    for i, n in enumerate(bass.notes):
        assert n.bar == i
        assert n.start_beat == pytest.approx(0.0, abs=0.05)
        assert n.pitch == 48

    drums = _pick_track(read, is_drum=True)
    kicks = [n for n in drums.notes if n.pitch == 36]
    snares = [n for n in drums.notes if n.pitch == 38]
    assert len(kicks) == 8 and len(snares) == 8


def _pick_track(read: ReadSong, *, is_drum: bool) -> ReadTrack:
    for t in read.tracks:
        if t.is_drum == is_drum:
            return t
    raise AssertionError(f"no track with is_drum={is_drum}")


# ---------------------------------------------------------------------------
# program_role bucketing
# ---------------------------------------------------------------------------


def test_program_role_buckets_gm_families():
    assert program_role(0, False) == "piano"
    assert program_role(24, False) == "guitar"
    assert program_role(33, False) == "bass"
    assert program_role(40, False) == "strings"
    assert program_role(48, False) == "ensemble"
    assert program_role(80, False) == "synth_lead"
    assert program_role(0, True) == "drums"


# ---------------------------------------------------------------------------
# extract_key
# ---------------------------------------------------------------------------


def test_extract_key_recovers_c_major_from_diatonic():
    # C major scale ascending in one bar
    read = ReadSong(
        tempo_bpm=120,
        time_signature=(4, 4),
        num_bars=2,
        tracks=[
            ReadTrack(
                program=0,
                is_drum=False,
                name="piano",
                notes=[
                    ReadNote(bar=0, start_beat=i * 0.5, pitch=60 + p, dur=0.5, velocity=90)
                    for i, p in enumerate([0, 2, 4, 5, 7, 9, 11])
                ],
            )
        ],
    )
    key = extract_key(read)
    assert "C" in key and "major" in key


def test_extract_key_returns_default_when_empty():
    read = ReadSong(tempo_bpm=120, time_signature=(4, 4), num_bars=1, tracks=[])
    assert extract_key(read) == "C major"


# ---------------------------------------------------------------------------
# extract_progression
# ---------------------------------------------------------------------------


def test_extract_progression_detects_major_triad():
    # bar 0: C E G sustained
    read = ReadSong(
        tempo_bpm=120,
        time_signature=(4, 4),
        num_bars=1,
        tracks=[
            ReadTrack(
                program=0,
                is_drum=False,
                name="piano",
                notes=[
                    ReadNote(bar=0, start_beat=0.0, pitch=60, dur=4.0, velocity=90),
                    ReadNote(bar=0, start_beat=0.0, pitch=64, dur=4.0, velocity=90),
                    ReadNote(bar=0, start_beat=0.0, pitch=67, dur=4.0, velocity=90),
                ],
            )
        ],
    )
    prog = extract_progression(read)
    assert len(prog) == 1
    assert prog[0].startswith("C")


def test_extract_progression_detects_minor_seventh():
    # bar 0: A C E G
    read = ReadSong(
        tempo_bpm=120,
        time_signature=(4, 4),
        num_bars=1,
        tracks=[
            ReadTrack(
                program=0,
                is_drum=False,
                name="piano",
                notes=[
                    ReadNote(bar=0, start_beat=0.0, pitch=57, dur=4.0, velocity=90),
                    ReadNote(bar=0, start_beat=0.0, pitch=60, dur=4.0, velocity=90),
                    ReadNote(bar=0, start_beat=0.0, pitch=64, dur=4.0, velocity=90),
                    ReadNote(bar=0, start_beat=0.0, pitch=67, dur=4.0, velocity=90),
                ],
            )
        ],
    )
    prog = extract_progression(read)
    assert prog[0].startswith("A")
    assert "m" in prog[0]


def test_extract_progression_inherits_previous_chord_for_empty_bar():
    read = ReadSong(
        tempo_bpm=120,
        time_signature=(4, 4),
        num_bars=2,
        tracks=[
            ReadTrack(
                program=0,
                is_drum=False,
                name="piano",
                notes=[
                    ReadNote(bar=0, start_beat=0.0, pitch=60, dur=4.0, velocity=90),
                    ReadNote(bar=0, start_beat=0.0, pitch=64, dur=4.0, velocity=90),
                    ReadNote(bar=0, start_beat=0.0, pitch=67, dur=4.0, velocity=90),
                ],
            )
        ],
    )
    prog = extract_progression(read)
    assert len(prog) == 2
    assert prog[1] == prog[0]  # empty bar 1 inherits bar 0


# ---------------------------------------------------------------------------
# extract_drum_pattern
# ---------------------------------------------------------------------------


def test_extract_drum_pattern_produces_grid():
    # Four-on-the-floor kick + backbeat snare on bar 0
    read = ReadSong(
        tempo_bpm=120,
        time_signature=(4, 4),
        num_bars=1,
        tracks=[
            ReadTrack(
                program=0,
                is_drum=True,
                name="drums",
                notes=[
                    ReadNote(bar=0, start_beat=0.0, pitch=36, dur=0.25, velocity=100),
                    ReadNote(bar=0, start_beat=1.0, pitch=38, dur=0.25, velocity=100),
                    ReadNote(bar=0, start_beat=2.0, pitch=36, dur=0.25, velocity=100),
                    ReadNote(bar=0, start_beat=3.0, pitch=38, dur=0.25, velocity=100),
                ],
            )
        ],
    )
    pattern = extract_drum_pattern(read, subdivision=16)
    assert "kick" in pattern and "snare" in pattern
    # 16 steps per bar in 4/4, one bar => 16 chars.
    assert len(pattern["kick"]) == 16
    assert pattern["kick"][0] == "x" and pattern["kick"][8] == "x"
    assert pattern["snare"][4] == "x" and pattern["snare"][12] == "x"


def test_extract_drum_pattern_empty_when_no_drum_track():
    read = ReadSong(
        tempo_bpm=120,
        time_signature=(4, 4),
        num_bars=1,
        tracks=[
            ReadTrack(program=0, is_drum=False, name="piano", notes=[]),
        ],
    )
    assert extract_drum_pattern(read) == {}


# ---------------------------------------------------------------------------
# extract_density_by_role
# ---------------------------------------------------------------------------


def test_extract_density_by_role_counts_notes_per_bar():
    read = ReadSong(
        tempo_bpm=120,
        time_signature=(4, 4),
        num_bars=2,
        tracks=[
            ReadTrack(
                program=33,
                is_drum=False,
                name="bass",
                notes=[
                    ReadNote(bar=0, start_beat=0.0, pitch=40, dur=1.0, velocity=90),
                    ReadNote(bar=0, start_beat=2.0, pitch=40, dur=1.0, velocity=90),
                    ReadNote(bar=1, start_beat=0.0, pitch=40, dur=1.0, velocity=90),
                ],
            ),
            ReadTrack(
                program=0,
                is_drum=True,
                name="drums",
                notes=[
                    ReadNote(bar=0, start_beat=b, pitch=36, dur=0.25, velocity=100)
                    for b in (0.0, 1.0, 2.0, 3.0)
                ],
            ),
        ],
    )
    density = extract_density_by_role(read)
    assert density["bass"] == pytest.approx(1.5)  # 3 notes / 2 bars
    assert density["drums"] == pytest.approx(2.0)  # 4 notes / 2 bars


# ---------------------------------------------------------------------------
# read_midi via pretty_midi round-trip on synthetic object
# ---------------------------------------------------------------------------


def test_pretty_midi_to_song_reads_tempo_and_ts():
    pm = pretty_midi.PrettyMIDI(initial_tempo=90.0)
    pm.time_signature_changes.append(pretty_midi.TimeSignature(3, 4, 0.0))
    inst = pretty_midi.Instrument(program=0, is_drum=False, name="p")
    # one C4 note at t=0, dur=1 quarter note
    sec_per_beat = 60.0 / 90.0
    inst.notes.append(pretty_midi.Note(velocity=90, pitch=60, start=0.0, end=sec_per_beat))
    pm.instruments.append(inst)

    read = pretty_midi_to_song(pm)
    assert read.tempo_bpm == pytest.approx(90.0)
    assert read.time_signature == (3, 4)
    assert read.tracks and read.tracks[0].notes
    n = read.tracks[0].notes[0]
    assert n.pitch == 60
    assert n.bar == 0
    assert n.start_beat == pytest.approx(0.0, abs=0.05)
