from __future__ import annotations

import json
from pathlib import Path

import pytest

from music_assistant.corpus import retrieve
from music_assistant.corpus.retrieve import (
    LakhExample,
    GroovePattern,
    normalize_genre,
    retrieve_groove,
    retrieve_style_examples,
)


def test_normalize_genre_maps_common_terms():
    assert "reggaeton" in normalize_genre("reggaeton perreo")
    assert "bossa" in normalize_genre("bossa nova triste")
    assert "rock" in normalize_genre("90s grunge")
    assert normalize_genre("") == []


def test_normalize_genre_unknown_falls_back_to_first_token():
    tags = normalize_genre("weird xyz music")
    assert tags == ["weird"]


def test_retrieve_style_examples_returns_empty_when_index_missing():
    # No `_rows` and (in CI) no index on disk => empty list, no crash.
    retrieve.clear_caches()
    got = retrieve_style_examples("reggaeton", "medium", n=3, _rows=[])
    assert got == []


def test_retrieve_style_examples_filters_by_genre():
    rows = [
        {
            "track_id": "TR1",
            "genre": "reggaeton",
            "key": "A minor",
            "tempo": 92.0,
            "progression": ["Am", "F", "C", "G"],
            "density_by_role": {"bass": 4.0, "drums": 8.0},
            "roles": ["bass", "drums", "synth_lead"],
        },
        {
            "track_id": "TR2",
            "genre": "rock",
            "key": "E major",
            "tempo": 130.0,
            "progression": ["E", "A", "B", "E"],
            "density_by_role": {"bass": 5.0, "drums": 9.0},
            "roles": ["bass", "drums", "guitar"],
        },
    ]
    examples = retrieve_style_examples("reggaeton perreo", "medium", n=3, _rows=rows)
    assert len(examples) == 1
    assert examples[0].genre == "reggaeton"
    assert examples[0].progression == ["Am", "F", "C", "G"]


def test_retrieve_style_examples_ranks_by_energy_target():
    # Two rock rows with different densities; energy=low should prefer the sparser one.
    rows = [
        {"track_id": "T1", "genre": "rock", "key": "E major", "tempo": 130,
         "progression": ["E"], "density_by_role": {"bass": 2, "drums": 3}, "roles": []},
        {"track_id": "T2", "genre": "rock", "key": "E major", "tempo": 130,
         "progression": ["A"], "density_by_role": {"bass": 8, "drums": 12}, "roles": []},
    ]
    low = retrieve_style_examples("rock", "low", n=1, _rows=rows)
    high = retrieve_style_examples("rock", "high", n=1, _rows=rows)
    assert low[0].track_id == "T1"
    assert high[0].track_id == "T2"


def test_retrieve_groove_matches_style_and_prefers_beat_by_default():
    rows = [
        {"style": "funk", "bpm": 100, "type": "beat", "num_bars": 2,
         "pattern_by_channel": {"kick": "x...x...", "snare": "....x..."}},
        {"style": "funk", "bpm": 100, "type": "fill", "num_bars": 1,
         "pattern_by_channel": {"kick": "xxxxxxxx"}},
        {"style": "rock", "bpm": 130, "type": "beat", "num_bars": 2,
         "pattern_by_channel": {"kick": "x.x.x.x.", "snare": "..x...x."}},
    ]
    groove = retrieve_groove("funk", bpm=100, energy="medium", _rows=rows)
    assert groove is not None
    assert groove.style == "funk"
    assert groove.type == "beat"


def test_retrieve_groove_returns_fill_for_high_energy():
    rows = [
        {"style": "rock", "bpm": 120, "type": "beat", "num_bars": 2,
         "pattern_by_channel": {"kick": "x...x..."}},
        {"style": "rock", "bpm": 122, "type": "fill", "num_bars": 1,
         "pattern_by_channel": {"snare": "xxxxxxxx"}},
    ]
    groove = retrieve_groove("rock", bpm=120, energy="high", _rows=rows)
    assert groove is not None
    assert groove.type == "fill"


def test_retrieve_groove_returns_none_when_no_match():
    rows = [
        {"style": "rock", "bpm": 130, "type": "beat", "num_bars": 2,
         "pattern_by_channel": {"kick": "x...x..."}},
    ]
    assert retrieve_groove("reggaeton", bpm=90, energy="medium", _rows=rows) is None


def test_retrieve_reads_jsonl_index(tmp_path: Path, monkeypatch):
    idx = tmp_path / "index"
    idx.mkdir()
    (idx / "groove_patterns.jsonl").write_text(
        json.dumps({
            "style": "funk", "bpm": 100, "type": "beat", "num_bars": 2,
            "pattern_by_channel": {"kick": "x...x...", "snare": "....x..."},
        }) + "\n"
    )
    monkeypatch.setattr(retrieve, "INDEX_ROOT", idx)
    retrieve.clear_caches()
    groove = retrieve_groove("funk", bpm=100, energy="medium")
    assert groove is not None
    assert groove.pattern_by_channel["kick"] == "x...x..."
