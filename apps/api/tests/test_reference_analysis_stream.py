"""SSE tests for research-only reference analysis progress."""

from __future__ import annotations

import json

from fastapi.testclient import TestClient

import music_assistant.interfaces.api as api
from music_assistant.domain.reference_profile import MusicProfile, ReferenceProfile, ReferenceSource


def _parse_sse(text: str) -> list[dict]:
    events = []
    for chunk in text.strip().split("\n\n"):
        for line in chunk.splitlines():
            if line.startswith("data:"):
                events.append(json.loads(line.removeprefix("data:").strip()))
    return events


class _FakeResearcher:
    def research(self, query: str) -> ReferenceProfile:
        return ReferenceProfile(
            reference_id="ref_stream_song",
            source=ReferenceSource(
                reference_id="ref_stream_song",
                kind="metadata",
                label=query,
                uri=f"research://{query}",
                authorized=True,
            ),
            music=MusicProfile(
                duration_seconds=0.0,
                tempo_bpm=101.0,
                tempo_confidence=0.7,
                key="D minor",
                key_confidence=0.66,
                confidence=0.7,
                overall_confidence=0.7,
            ),
            summary="Research ready.",
        )


class _FailingResearcher:
    def research(self, query: str) -> ReferenceProfile:
        raise RuntimeError("source blocked")


def test_research_reference_stream_emits_progress_and_done(monkeypatch):
    monkeypatch.setattr(api, "_song_researcher", lambda: _FakeResearcher())
    client = TestClient(api.app)

    response = client.post("/references/research/stream", json={"query": "Space Cowboy"})

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    events = _parse_sse(response.text)
    assert [event["type"] for event in events] == [
        "accepted",
        "searching_sources",
        "fetching_pages",
        "extracting_claims",
        "fusing_evidence",
        "done",
    ]
    assert events[-1]["profile"]["music"]["key"] == "D minor"


def test_research_reference_stream_emits_error_event(monkeypatch):
    monkeypatch.setattr(api, "_song_researcher", lambda: _FailingResearcher())
    client = TestClient(api.app)

    response = client.post("/references/research/stream", json={"query": "Blocked Song"})

    assert response.status_code == 200
    events = _parse_sse(response.text)
    assert events[-1]["type"] == "error"
    assert "source blocked" in events[-1]["message"]
