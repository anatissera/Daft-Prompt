"""Phase 3: /compose chooses the director path when an LLM is configured,
otherwise falls back to the canned demo. Both paths mocked — no API key."""

from __future__ import annotations

from fastapi.testclient import TestClient

import music_assistant.interfaces.api as api
from music_assistant.domain.song_state import Header, RosterItem, SongState


class _Cfg:
    llm_configured = True


class _NoLLMCfg:
    llm_configured = False


def _fake_song(style: str) -> SongState:
    header = Header(genre="disco", key="C major", tempo_bpm=120, num_bars=8)
    roster = [
        RosterItem(id="bass", instrument="electric_bass", midi_range=(28, 55), role="groove"),
        RosterItem(id="lead", instrument="lead", midi_range=(60, 84), role="melody"),
        RosterItem(id="drums", instrument="kit", role="beat", is_drum=True),
    ]
    return SongState(request=style, header=header, roster=roster)


def test_compose_uses_director_when_configured(monkeypatch):
    monkeypatch.setattr(api, "get_settings", lambda: _Cfg())
    monkeypatch.setattr(api, "run_negotiation", lambda style, **kw: _fake_song(style))
    monkeypatch.setattr(api, "render_artifacts", lambda song, job_dir: None)
    client = TestClient(api.app)
    resp = client.post("/compose", json={"style": "disco"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["source"] == "director"
    assert [r["id"] for r in body["song"]["roster"]] == ["bass", "lead", "drums"]


def test_compose_falls_back_to_canned_without_llm(monkeypatch):
    monkeypatch.setattr(api, "get_settings", lambda: _NoLLMCfg())
    monkeypatch.setattr(api, "render_artifacts", lambda song, job_dir: None)
    client = TestClient(api.app)
    resp = client.post("/compose", json={"style": "slow blues"})
    assert resp.status_code == 200
    assert resp.json()["source"] == "canned"
