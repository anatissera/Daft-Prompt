"""Phase 6: POST /compose/stream emits SSE events (director, agent_pass,
convergence, done) over the same director/canned + negotiation pipeline as
/compose. LLM/negotiation mocked — no API key needed."""

from __future__ import annotations

import json

from fastapi.testclient import TestClient

import llm_band.api as api
from llm_band.agents.director import (
    ArrangementInstrument,
    ArrangementSection,
    DirectorOutput,
    arrangement_to_song,
)
from llm_band.schema import Part


def _parse_sse(text: str) -> list[dict]:
    events = []
    for chunk in text.strip().split("\n\n"):
        for line in chunk.splitlines():
            if line.startswith("data:"):
                events.append(json.loads(line.removeprefix("data:").strip()))
    return events


class _Cfg:
    llm_configured = True


def _fake_song(style: str):
    out = DirectorOutput(
        genre="disco", key="C major", tempo_bpm=120,
        time_sig_numerator=4, time_sig_denominator=4, num_bars=8,
        sections=[ArrangementSection(name="loop", start_bar=0, end_bar=8)],
        instruments=[
            ArrangementInstrument(id="bass", instrument="electric_bass",
                                  midi_program=33, midi_low=28, midi_high=55, role="groove"),
        ],
    )
    return arrangement_to_song(style, out)


def _fake_negotiation_events(song):
    song.parts = {"bass": Part(instrument_id="bass", notes_summary="patched")}
    song.converged = True
    yield {"type": "agent_pass", "round": 0, "instrument_id": "bass",
           "notes_summary": "patched", "new_requests": [], "resolved_requests": []}
    yield {"type": "convergence", "round": 0, "converged": True, "resolved_requests": []}


def test_compose_stream_director_path_emits_agent_pass_and_done(monkeypatch):
    monkeypatch.setattr(api, "get_settings", lambda: _Cfg())
    monkeypatch.setattr(api, "run_director", _fake_song)
    monkeypatch.setattr(api, "iter_negotiation_events", _fake_negotiation_events)
    client = TestClient(api.app)
    resp = client.post("/compose/stream", json={"style": "disco"})

    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/event-stream")
    events = _parse_sse(resp.text)
    types = [e["type"] for e in events]
    assert types == ["director", "agent_pass", "convergence", "done"]

    assert events[0]["roster"][0]["id"] == "bass"
    assert events[1]["instrument_id"] == "bass"
    done = events[-1]
    assert done["source"] == "director"
    assert done["song"]["parts"]["bass"]["notes_summary"] == "patched"
    assert done["artifacts"]["midi"].endswith("song.mid")


def test_compose_stream_canned_path_emits_director_and_done():
    client = TestClient(api.app)
    resp = client.post("/compose/stream", json={"style": "slow blues"})

    assert resp.status_code == 200
    events = _parse_sse(resp.text)
    types = [e["type"] for e in events]
    assert types == ["director", "convergence", "done"]
    assert events[-1]["source"] == "canned"
