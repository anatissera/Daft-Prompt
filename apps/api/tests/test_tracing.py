from __future__ import annotations

import json
from pathlib import Path

from music_assistant.agents.director import DirectorOutput, run_director
from music_assistant.infrastructure.tracing import open_run


class FakeLLM:
    def __init__(self, out: DirectorOutput) -> None:
        self._out = out

    def with_structured_output(self, _schema):
        return self

    def invoke(self, _messages):
        return self._out


def _minimal_output() -> DirectorOutput:
    return DirectorOutput(
        genre="rock metal",
        key="E minor",
        tempo_bpm=140.0,
        num_bars=4,
        sections=[{"name": "A", "start_bar": 0, "end_bar": 4, "energy": "high"}],
        chord_progression=[{"bar": i, "chord": "Em"} for i in range(4)],
        instruments=[
            {"id": "gtr", "instrument": "electric_guitar", "patch": "distortion_guitar",
             "role": "riffs", "playing_style": "power chords, palm mutes"},
            {"id": "bass", "instrument": "electric_bass", "patch": "electric_bass",
             "role": "root", "playing_style": "root eighths"},
            {"id": "drums", "instrument": "drum_kit", "patch": None,
             "role": "kit", "playing_style": "four-on-the-floor", "is_drum": True},
        ],
        composition_groups=[
            {"name": "rhythm", "instrument_ids": ["drums", "bass"], "max_negotiation_rounds": 1},
            {"name": "melody", "instrument_ids": ["gtr"], "max_negotiation_rounds": 0},
        ],
    )


def test_run_director_writes_trace(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("MUSIC_ASSISTANT_TRACE_DIR", str(tmp_path))
    trace = open_run("rock metal in E")
    song = run_director("rock metal in E", llm=FakeLLM(_minimal_output()), trace=trace)
    assert song.header.tempo_bpm == 140.0

    director_file = trace.directory / "director.json"
    assert director_file.exists(), "director trace file was not written"
    payload = json.loads(director_file.read_text())

    assert payload["node"] == "director"
    assert payload["style"] == "rock metal in E"
    assert payload["run_id"] == trace.run_id
    assert isinstance(payload["prompt_messages"], list) and payload["prompt_messages"], (
        "prompt_messages should contain at least the system message"
    )
    assert payload["prompt_messages"][0]["role"] == "system"
    # The director's own decision must be present for the "why did it pick X" audit.
    assert payload["output"]["tempo_bpm"] == 140.0
    # `instrument` free-text was dropped from ArrangementInstrument — `patch`
    # from the closed vocabulary is the single source of truth for the sound.
    assert any(i["patch"] == "distortion_guitar" for i in payload["output"]["instruments"])


def test_run_director_without_trace_still_works():
    # trace is optional — this is the path exercised by existing tests.
    song = run_director("disco", llm=FakeLLM(_minimal_output()))
    assert song.header.key == "E minor"
