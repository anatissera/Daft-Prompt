from __future__ import annotations

import pytest

from music_assistant.domain.song_state import Header, Note, Part
from music_assistant.music.theory_tools import (
    detect_overlaps,
    note_density,
    part_density_by_id,
)


def _header(num_bars: int = 4, ts=(4, 4)) -> Header:
    return Header(
        genre="t",
        key="C major",
        tempo_bpm=120,
        time_signature=ts,
        num_bars=num_bars,
    )


def test_note_density_counts_sounding_notes_per_bar():
    h = _header(num_bars=4)
    notes = [
        Note(bar=0, start_beat=0, pitch=60, dur=1),
        Note(bar=0, start_beat=1, pitch=None, dur=1),  # rest, ignored
        Note(bar=1, start_beat=0, pitch=60, dur=1),
        Note(bar=1, start_beat=1, pitch=60, dur=1),
        Note(bar=2, start_beat=0, pitch=60, dur=1),
    ]
    assert note_density(notes, h) == pytest.approx(4 / 4)


def test_part_density_by_id_maps_each_part():
    h = _header(num_bars=2)
    parts = {
        "bass": Part(
            instrument_id="bass",
            notes=[Note(bar=0, start_beat=0, pitch=40, dur=1)],
        ),
        "lead": Part(
            instrument_id="lead",
            notes=[
                Note(bar=0, start_beat=0, pitch=60, dur=1),
                Note(bar=1, start_beat=0, pitch=62, dur=1),
            ],
        ),
    }
    d = part_density_by_id(parts, h)
    assert d["bass"] == pytest.approx(0.5)
    assert d["lead"] == pytest.approx(1.0)


def test_detect_overlaps_flags_simultaneous_sounding_notes():
    h = _header(num_bars=1)
    part = Part(
        instrument_id="bass",
        notes=[
            Note(bar=0, start_beat=0.0, pitch=40, dur=2.0),
            Note(bar=0, start_beat=1.0, pitch=43, dur=1.0),  # overlaps with the first
        ],
    )
    overlaps = detect_overlaps(part, h)
    assert overlaps
    bar, msg = overlaps[0]
    assert bar == 0
    assert "overlap" in msg


def test_detect_overlaps_accepts_adjacent_notes():
    h = _header(num_bars=1)
    part = Part(
        instrument_id="bass",
        notes=[
            Note(bar=0, start_beat=0.0, pitch=40, dur=1.0),
            Note(bar=0, start_beat=1.0, pitch=43, dur=1.0),  # starts exactly when prev ends
        ],
    )
    assert detect_overlaps(part, h) == []


def test_detect_overlaps_ignores_rests_and_zero_duration():
    h = _header(num_bars=1)
    part = Part(
        instrument_id="bass",
        notes=[
            Note(bar=0, start_beat=0.0, pitch=None, dur=2.0),  # rest, ignored
            Note(bar=0, start_beat=1.0, pitch=43, dur=0.0),  # zero-dur, ignored
        ],
    )
    assert detect_overlaps(part, h) == []
