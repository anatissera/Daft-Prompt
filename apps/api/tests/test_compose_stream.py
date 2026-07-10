"""POST /compose/stream emits SSE events over the band-agent pipeline
(progress, director, done — plus error/convergence on failures). The
band-agent event streamer is mocked — no API key needed."""

from __future__ import annotations

import json

from fastapi.testclient import TestClient

import music_assistant.interfaces.api as api
from music_assistant.domain.song_state import Header, Part, RosterItem, SongState
from music_assistant.infrastructure.llm import LLMQuotaExceeded


def _parse_sse(text: str) -> list[dict]:
    events = []
    for chunk in text.strip().split("\n\n"):
        for line in chunk.splitlines():
            if line.startswith("data:"):
                events.append(json.loads(line.removeprefix("data:").strip()))
    return events


class _Cfg:
    llm_configured = True


class _NoLLMCfg:
    llm_configured = False


def _make_fake_song(style: str) -> SongState:
    header = Header(genre="disco", key="C major", tempo_bpm=120, num_bars=8)
    roster = [RosterItem(id="bass", instrument="electric_bass", role="groove")]
    return SongState(request=style, header=header, roster=roster)


def _director_event(song: SongState) -> dict:
    return {
        "type": "director",
        "source": "director",
        "header": song.header.model_dump(mode="json"),
        "roster": [r.model_dump(mode="json") for r in song.roster],
    }


def _fake_band_stream(style):
    """Happy path: progress → director (carries song) → empty sentinel."""
    song = _make_fake_song(style)
    song.parts = {"bass": Part(instrument_id="bass", notes_summary="patched")}
    song.converged = True
    yield {"type": "progress", "stage": "skeleton", "message": "disco @ 120"}, None
    yield _director_event(song), song
    yield {}, song


def _fake_band_stream_crash_after_director(style):
    song = _make_fake_song(style)
    song.parts = {"bass": Part(instrument_id="bass", notes_summary="partial bass")}
    yield _director_event(song), song
    raise RuntimeError("fills crashed after director")


def _fake_band_stream_quota_after_director(style):
    song = _make_fake_song(style)
    yield _director_event(song), song
    raise LLMQuotaExceeded(provider="gemini", model="gemini-2.5-flash", detail="quota exceeded")


def _fake_band_stream_partial_then_quota(style):
    song = _make_fake_song(style)
    song.parts = {"bass": Part(instrument_id="bass", notes_summary="partial bass")}
    yield _director_event(song), song
    yield {"type": "progress", "stage": "fills", "message": "filled 1 / 2"}, None
    raise LLMQuotaExceeded(provider="gemini", model="gemini-2.5-flash", detail="quota exceeded")


def test_compose_stream_band_path_emits_progress_director_done(monkeypatch):
    monkeypatch.setattr(api, "get_settings", lambda: _Cfg())
    monkeypatch.setattr(api, "_band_agent_event_streamer", _fake_band_stream)
    monkeypatch.setattr(api, "render_artifacts", lambda song, job_dir: None)
    client = TestClient(api.app)
    resp = client.post("/compose/stream", json={"style": "disco"})

    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/event-stream")
    events = _parse_sse(resp.text)
    types = [e["type"] for e in events]
    assert types == ["progress", "director", "done"]

    assert events[1]["roster"][0]["id"] == "bass"
    done = events[-1]
    assert done["source"] == "director"
    assert done["song"]["parts"]["bass"]["notes_summary"] == "patched"
    assert done["artifacts"]["midi"].endswith("song.mid")


def test_compose_stream_survives_crash_after_director_with_partial_song(monkeypatch):
    monkeypatch.setattr(api, "get_settings", lambda: _Cfg())
    monkeypatch.setattr(api, "_band_agent_event_streamer", _fake_band_stream_crash_after_director)
    monkeypatch.setattr(api, "render_artifacts", lambda song, job_dir: None)
    client = TestClient(api.app)
    resp = client.post("/compose/stream", json={"style": "disco"})

    assert resp.status_code == 200
    events = _parse_sse(resp.text)
    types = [e["type"] for e in events]
    assert types == ["director", "convergence", "done"]
    done = events[-1]
    assert done["song"]["converged"] is False
    assert done["song"]["parts"]["bass"]["notes_summary"] == "partial bass"
    assert any("partial" in e for e in done["song"]["errors"])


def test_compose_stream_emits_error_event_on_quota_exhaustion(monkeypatch):
    monkeypatch.setattr(api, "get_settings", lambda: _Cfg())
    monkeypatch.setattr(api, "_band_agent_event_streamer", _fake_band_stream_quota_after_director)
    monkeypatch.setattr(api, "render_artifacts", lambda song, job_dir: None)
    client = TestClient(api.app)
    resp = client.post("/compose/stream", json={"style": "disco"})

    assert resp.status_code == 200
    events = _parse_sse(resp.text)
    types = [e["type"] for e in events]
    assert types == ["director", "error", "done"]
    assert events[1]["code"] == "quota_exceeded"
    assert events[1]["provider"] == "gemini"
    assert events[1]["model"] == "gemini-2.5-flash"
    assert events[-1]["song"]["converged"] is False
    assert "quota" in events[-1]["song"]["errors"][0].lower()


def test_compose_stream_preserves_partial_parts_after_quota_error(monkeypatch):
    monkeypatch.setattr(api, "get_settings", lambda: _Cfg())
    monkeypatch.setattr(api, "_band_agent_event_streamer", _fake_band_stream_partial_then_quota)
    monkeypatch.setattr(api, "render_artifacts", lambda song, job_dir: None)
    client = TestClient(api.app)
    resp = client.post("/compose/stream", json={"style": "disco"})

    assert resp.status_code == 200
    events = _parse_sse(resp.text)
    types = [e["type"] for e in events]
    assert types == ["director", "progress", "error", "done"]
    assert events[-1]["song"]["parts"]["bass"]["notes_summary"] == "partial bass"
    assert events[-1]["song"]["converged"] is False


def test_compose_stream_emits_error_without_llm_configuration(monkeypatch):
    monkeypatch.setattr(api, "get_settings", lambda: _NoLLMCfg())
    monkeypatch.setattr(api, "render_artifacts", lambda song, job_dir: None)
    client = TestClient(api.app)
    resp = client.post("/compose/stream", json={"style": "slow blues"})

    assert resp.status_code == 200
    events = _parse_sse(resp.text)
    types = [e["type"] for e in events]
    assert types == ["error"]
    assert events[0]["code"] == "llm_not_configured"
    assert events[0]["partial"] is False
    assert "provider" in events[0]["message"].lower()
