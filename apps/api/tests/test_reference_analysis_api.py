"""HTTP API tests for research-only reference analysis."""

from __future__ import annotations

from fastapi.testclient import TestClient

import music_assistant.interfaces.api as api
from music_assistant.domain.reference_profile import MusicProfile, ReferenceProfile, ReferenceSource


class _FakeResearcher:
    def research(self, query: str) -> ReferenceProfile:
        return ReferenceProfile(
            reference_id="ref_test_song",
            source=ReferenceSource(
                reference_id="ref_test_song",
                kind="metadata",
                label=query,
                uri=f"research://{query}",
                authorized=True,
            ),
            music=MusicProfile(
                duration_seconds=0.0,
                tempo_bpm=120.0,
                tempo_confidence=0.8,
                key="A minor",
                key_confidence=0.7,
                confidence=0.75,
                overall_confidence=0.75,
            ),
            summary="Research found a likely A minor track around 120 BPM.",
        )


class _FailingResearcher:
    def research(self, query: str) -> ReferenceProfile:
        raise RuntimeError("blocked source")


def test_research_reference_returns_reference_profile(monkeypatch):
    monkeypatch.setattr(api, "_song_researcher", lambda: _FakeResearcher())
    client = TestClient(api.app)

    response = client.post("/references/research", json={"query": "Every Breath You Take"})

    assert response.status_code == 200
    body = response.json()
    assert body["reference_id"] == "ref_test_song"
    assert body["source"]["kind"] == "metadata"
    assert body["music"]["key"] == "A minor"
    assert body["music"]["tempo_bpm"] == 120.0
    assert "research" in body["summary"].lower()


def test_research_reference_rejects_empty_query():
    client = TestClient(api.app)

    response = client.post("/references/research", json={"query": ""})

    assert response.status_code == 422


def test_research_reference_reports_research_failure(monkeypatch):
    monkeypatch.setattr(api, "_song_researcher", lambda: _FailingResearcher())
    client = TestClient(api.app)

    response = client.post("/references/research", json={"query": "Blocked Song"})

    assert response.status_code == 422
    assert "research" in response.json()["detail"].lower()
