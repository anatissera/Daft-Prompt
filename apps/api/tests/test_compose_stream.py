"""Phase 6: POST /compose/stream emits SSE events (director, agent_pass,
convergence, done) over the same director/canned + negotiation pipeline as
/compose. LLM/negotiation mocked — no API key needed."""

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
    roster = [RosterItem(id="bass", instrument="electric_bass", midi_range=(28, 55), role="groove")]
    return SongState(request=style, header=header, roster=roster)


def _fake_negotiation_events(style, **kw):
    song = _make_fake_song(style)
    song.parts = {"bass": Part(instrument_id="bass", notes_summary="patched")}
    song.converged = True
    yield (
        {
            "type": "director",
            "source": "director",
            "header": song.header.model_dump(mode="json"),
            "roster": [r.model_dump(mode="json") for r in song.roster],
        },
        song,
    )
    yield (
        {"type": "agent_pass", "round": 0, "instrument_id": "bass",
         "notes_summary": "patched", "new_requests": [], "resolved_requests": []},
        None,
    )
    yield (
        {"type": "convergence", "round": 0, "converged": True, "resolved_requests": []},
        None,
    )


def _fake_failing_negotiation_events(style, **kw):
    song = _make_fake_song(style)
    yield (
        {
            "type": "director",
            "source": "director",
            "header": song.header.model_dump(mode="json"),
            "roster": [r.model_dump(mode="json") for r in song.roster],
        },
        song,
    )
    yield (
        {"type": "agent_pass", "round": 0, "instrument_id": "bass",
         "notes_summary": "fallback: model did not return structured output",
         "new_requests": [], "resolved_requests": []},
        None,
    )
    raise RuntimeError("instrument failed after fallback event")


def _fake_quota_negotiation_events(style, **kw):
    song = _make_fake_song(style)
    yield (
        {
            "type": "director",
            "source": "director",
            "header": song.header.model_dump(mode="json"),
            "roster": [r.model_dump(mode="json") for r in song.roster],
        },
        song,
    )
    raise LLMQuotaExceeded(provider="gemini", model="gemini-2.5-flash", detail="quota exceeded")


def _fake_partial_then_quota_events(style, **kw):
    song = _make_fake_song(style)
    song.parts = {"bass": Part(instrument_id="bass", notes_summary="partial bass")}
    yield (
        {
            "type": "director",
            "source": "director",
            "header": song.header.model_dump(mode="json"),
            "roster": [r.model_dump(mode="json") for r in song.roster],
        },
        song,
    )
    yield (
        {"type": "agent_pass", "round": 0, "instrument_id": "bass",
         "notes_summary": "partial bass", "new_requests": [], "resolved_requests": []},
        None,
    )
    raise LLMQuotaExceeded(provider="gemini", model="gemini-2.5-flash", detail="quota exceeded")


def test_compose_stream_director_path_emits_agent_pass_and_done(monkeypatch):
    monkeypatch.setattr(api, "get_settings", lambda: _Cfg())
    monkeypatch.setattr(api, "iter_negotiation_events", _fake_negotiation_events)
    monkeypatch.setattr(api, "render_artifacts", lambda song, job_dir: None)
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


def test_compose_stream_survives_negotiation_exception_after_fallback_event(monkeypatch):
    monkeypatch.setattr(api, "get_settings", lambda: _Cfg())
    monkeypatch.setattr(api, "iter_negotiation_events", _fake_failing_negotiation_events)
    monkeypatch.setattr(api, "render_artifacts", lambda song, job_dir: None)
    client = TestClient(api.app)
    resp = client.post("/compose/stream", json={"style": "disco"})

    assert resp.status_code == 200
    events = _parse_sse(resp.text)
    types = [e["type"] for e in events]
    assert types == ["director", "agent_pass", "convergence", "done"]
    assert events[1]["instrument_id"] == "bass"
    assert "fallback" in events[1]["notes_summary"]
    assert events[-1]["song"]["parts"]["bass"]["notes_summary"].startswith("fallback")


def test_compose_stream_emits_error_event_on_quota_exhaustion(monkeypatch):
    monkeypatch.setattr(api, "get_settings", lambda: _Cfg())
    monkeypatch.setattr(api, "iter_negotiation_events", _fake_quota_negotiation_events)
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
    monkeypatch.setattr(api, "iter_negotiation_events", _fake_partial_then_quota_events)
    monkeypatch.setattr(api, "render_artifacts", lambda song, job_dir: None)
    client = TestClient(api.app)
    resp = client.post("/compose/stream", json={"style": "disco"})

    assert resp.status_code == 200
    events = _parse_sse(resp.text)
    types = [e["type"] for e in events]
    assert types == ["director", "agent_pass", "error", "done"]
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
