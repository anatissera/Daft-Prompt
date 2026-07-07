from __future__ import annotations

from fastapi.testclient import TestClient

import music_assistant.interfaces.api as api
from music_assistant.domain.audio_profile import AudioProfile, ReferenceProfile, ReferenceSource, SongIdentity, SongKnowledgeProfile
from music_assistant.infrastructure.web_research.songsterr_tabs import (
    InstrumentTabTrack,
    SongsterrTabBundle,
    TabEvent,
    TabMeasure,
)


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
            audio=AudioProfile(
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
    assert body["audio"]["tempo_bpm"] == 111


def test_reference_research_stream_returns_done_event(monkeypatch):
    monkeypatch.setattr(api, "_song_researcher", lambda: FakeResearcher())
    client = TestClient(api.app)

    response = client.post("/references/research/stream", json={"query": "Jamiroquai Space Cowboy"})

    assert response.status_code == 200
    assert "data:" in response.text
    assert '"type": "done"' in response.text
    assert "ref_space_cowboy" in response.text


def test_reference_instrument_profiles_endpoint_returns_compact_memory(monkeypatch):
    reference_id = "ref_profile_endpoint"
    api.REFERENCE_STORE.save(
        ReferenceProfile(
            reference_id=reference_id,
            source=ReferenceSource(
                reference_id=reference_id,
                kind="metadata",
                label="Fixture Song",
                uri="research://fixture",
                authorized=True,
            ),
            knowledge=SongKnowledgeProfile(
                profile_id="song_profile_endpoint",
                identity=SongIdentity(title="Fixture Song"),
            ),
        )
    )
    api.SONGSTERR_TAB_STORE.save(
        reference_id,
        SongsterrTabBundle(
            source_url="https://songsterr.test/fixture",
            song_id=1,
            revision_id=2,
            image="img",
            title="Fixture Song",
            tracks=[
                InstrumentTabTrack(
                    part_id=4,
                    name="Fender Bass",
                    instrument="Electric Bass",
                    instrument_family="bass",
                    tuning=["E1", "A1", "D2", "G2"],
                    is_bass=True,
                    measures=[
                        TabMeasure(
                            index=0,
                            marker="Verse",
                            events=[TabEvent(measure_index=0, beat_index=0, duration="1/4", string=1, fret=5)],
                        )
                    ],
                    note_count=1,
                    beat_count=1,
                )
            ],
        ),
    )
    client = TestClient(api.app)

    response = client.get(f"/references/{reference_id}/instrument-profiles")

    assert response.status_code == 200
    body = response.json()
    assert body["reference_id"] == reference_id
    assert body["profiles"][0]["instrument_family"] == "bass"
    assert body["profiles"][0]["note_packs"][0]["note_pack_id"] == "bass_verse_0_0"
    assert body["profiles"][0]["note_packs"][0]["note_count"] == 1
    assert '"notes":' not in response.text
