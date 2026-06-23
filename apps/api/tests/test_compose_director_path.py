"""Phase 3: /compose chooses the director path when an LLM is configured,
otherwise falls back to the canned demo. Both paths mocked — no API key."""

from __future__ import annotations

from fastapi.testclient import TestClient

import llm_band.api as api
from llm_band.agents.director import (
    ArrangementInstrument,
    ArrangementSection,
    DirectorOutput,
    arrangement_to_song,
)


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
            ArrangementInstrument(id="lead", instrument="lead", midi_program=0,
                                  midi_low=60, midi_high=84, role="melody"),
            ArrangementInstrument(id="drums", instrument="kit", midi_program=0,
                                  midi_low=35, midi_high=81, role="beat", is_drum=True),
        ],
    )
    return arrangement_to_song(style, out)


def test_compose_uses_director_when_configured(monkeypatch):
    monkeypatch.setattr(api, "get_settings", lambda: _Cfg())
    monkeypatch.setattr(api, "run_director", _fake_song)
    monkeypatch.setattr(api, "run_negotiation", lambda song: song)
    client = TestClient(api.app)
    resp = client.post("/compose", json={"style": "disco"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["source"] == "director"
    assert [r["id"] for r in body["song"]["roster"]] == ["bass", "lead", "drums"]


def test_compose_falls_back_to_canned_without_llm():
    # default settings: no provider -> canned path
    client = TestClient(api.app)
    resp = client.post("/compose", json={"style": "slow blues"})
    assert resp.status_code == 200
    assert resp.json()["source"] == "canned"
