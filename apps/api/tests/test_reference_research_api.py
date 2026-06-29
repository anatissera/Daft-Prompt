from __future__ import annotations

from fastapi.testclient import TestClient

import music_assistant.interfaces.api as api
from music_assistant.domain.reference_profile import MusicProfile, ReferenceProfile, ReferenceSource


class FakeResearcher:
    def research(self, query: str) -> ReferenceProfile:
        return ReferenceProfile(
            reference_id="ref_space_cowboy",
            source=ReferenceSource(
                reference_id="ref_space_cowboy",
                kind="metadata",
                label=query,
                uri=f"research://{query}",
                authorized=True,
            ),
            music=MusicProfile(
                duration_seconds=0.0,
                tempo_bpm=111,
                tempo_confidence=0.7,
                key="E minor",
                key_confidence=0.65,
                confidence=0.7,
                overall_confidence=0.7,
            ),
            summary="Likely E minor around 111 BPM.",
        )


def test_reference_research_endpoint_returns_profile(monkeypatch):
    monkeypatch.setattr(api, "_song_researcher", lambda: FakeResearcher())
    client = TestClient(api.app)

    response = client.post("/references/research", json={"query": "Jamiroquai Space Cowboy"})

    assert response.status_code == 200
    body = response.json()
    assert body["reference_id"] == "ref_space_cowboy"
    assert body["source"]["kind"] == "metadata"
    assert body["music"]["tempo_bpm"] == 111


def test_reference_research_stream_returns_done_event(monkeypatch):
    monkeypatch.setattr(api, "_song_researcher", lambda: FakeResearcher())
    client = TestClient(api.app)

    response = client.post("/references/research/stream", json={"query": "Jamiroquai Space Cowboy"})

    assert response.status_code == 200
    assert "data:" in response.text
    assert '"type": "done"' in response.text
    assert "ref_space_cowboy" in response.text
