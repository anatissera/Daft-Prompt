from __future__ import annotations

from fastapi.testclient import TestClient

import music_assistant.interfaces.api as api
from music_assistant.domain.audio_profile import EvidenceClaim
from music_assistant.infrastructure.web_research.researcher import ConnectorSongResearcher
from music_assistant.ports.song_source_connector import (
    ConnectorFailure,
    ConnectorResult,
    ResolvedSongQuery,
)
from music_assistant.ports.web_search import SearchResult


class ClaimsConnector:
    source_name = "claims"

    def __init__(self, claims: list[EvidenceClaim]):
        self.claims = claims
        self.calls: list[ResolvedSongQuery] = []

    def collect(self, query: ResolvedSongQuery) -> ConnectorResult:
        self.calls.append(query)
        return ConnectorResult(
            source_name=self.source_name,
            query=query,
            fetch_status="fetched",
            claims=self.claims,
        )


class BlockedConnector:
    source_name = "blocked"

    def collect(self, query: ResolvedSongQuery) -> ConnectorResult:
        return ConnectorResult(
            source_name=self.source_name,
            query=query,
            fetch_status="blocked",
            failures=[
                ConnectorFailure(
                    source_name=self.source_name,
                    url="https://blocked.test",
                    status="blocked",
                    reason="HTTP 403",
                )
            ],
        )


class UrlSensitiveConnector:
    source_name = "CifraClub"

    def __init__(self, claims: list[EvidenceClaim]) -> None:
        self.claims = claims
        self.calls: list[ResolvedSongQuery] = []

    def collect(self, query: ResolvedSongQuery) -> ConnectorResult:
        self.calls.append(query)
        if query.source_url == "https://www.cifraclub.com.br/jamiroquai/space-cowboy/":
            return ConnectorResult(
                source_name=self.source_name,
                query=query,
                fetch_status="fetched",
                claims=self.claims,
            )
        return ConnectorResult(
            source_name=self.source_name,
            query=query,
            fetch_status="empty",
            failures=[
                ConnectorFailure(
                    source_name=self.source_name,
                    url=query.source_url,
                    status="empty",
                    reason="No structured claims found in fetched page.",
                )
            ],
        )


class FakeSearch:
    def search(self, query: str, *, limit: int = 10) -> list[SearchResult]:
        return [
            SearchResult(
                url="https://www.cifraclub.com.br/jamiroquai/space-cowboy/",
                title="Space Cowboy - Jamiroquai",
                site="CifraClub",
            )
        ][:limit]


def claim(claim_id: str, claim_type: str, value: str, *, source: str = "claims", confidence: float = 0.7) -> EvidenceClaim:
    return EvidenceClaim(
        claim_id=claim_id,
        claim_type=claim_type,  # type: ignore[arg-type]
        value=value,
        normalized_value=value,
        source_name=source,
        source_url=f"https://{source}.test/song",
        extraction_method="site_parser",
        confidence=confidence,
        snippet=f"{claim_type}: {value}",
    )


def test_connector_song_researcher_returns_reference_profile_with_rich_knowledge():
    researcher = ConnectorSongResearcher(
        connectors=[
            ClaimsConnector(
                [
                    claim("tempo", "tempo", "111 BPM", confidence=0.8),
                    claim("key", "key", "A minor", confidence=0.7),
                ]
            )
        ]
    )

    profile = researcher.research("Jamiroquai - Space Cowboy")

    assert profile.source.kind == "metadata"
    assert profile.knowledge is not None
    assert profile.knowledge.identity.title == "Jamiroquai - Space Cowboy"
    assert profile.audio is not None
    assert profile.audio.tempo_bpm == 111
    assert profile.audio.key == "A minor"
    assert profile.research_evidence[0].claim_type == "tempo"


def test_connector_song_researcher_parses_title_by_artist_queries():
    connector = ClaimsConnector([claim("tempo", "tempo", "111 BPM", confidence=0.8)])
    researcher = ConnectorSongResearcher(connectors=[connector])

    profile = researcher.research("Space Cowboy by Jamiroquai")

    assert profile.knowledge is not None
    assert profile.knowledge.identity.title == "Space Cowboy"
    assert profile.knowledge.identity.artist == "Jamiroquai"
    assert connector.calls[0].title == "Space Cowboy"
    assert connector.calls[0].artist == "Jamiroquai"


def test_connector_song_researcher_tries_source_search_candidates_after_empty_direct_result():
    connector = UrlSensitiveConnector([claim("tempo", "tempo", "111 BPM", source="CifraClub", confidence=0.8)])
    researcher = ConnectorSongResearcher(connectors=[connector], search=FakeSearch())

    profile = researcher.research("Space Cowboy by Jamiroquai")

    assert profile.audio is not None
    assert profile.audio.tempo_bpm == 111
    assert [call.source_url for call in connector.calls] == [
        None,
        "https://www.cifraclub.com.br/jamiroquai/space-cowboy/",
    ]


def test_connector_song_researcher_handles_no_claims_as_missing_data():
    profile = ConnectorSongResearcher(connectors=[ClaimsConnector([])]).research("Sparse Song")

    assert profile.knowledge is not None
    assert profile.audio is not None
    assert profile.audio.tempo_bpm is None
    assert any(item.field == "tempo" for item in profile.knowledge.missing_data)
    assert "No source-backed claims" in profile.summary


def test_connector_song_researcher_records_blocked_sources():
    profile = ConnectorSongResearcher(connectors=[BlockedConnector()]).research("Blocked Song")

    assert profile.knowledge is not None
    assert any(note.code == "source_blocked" for note in profile.audio.analysis_notes)
    assert "blocked" in profile.summary.lower()


def test_connector_song_researcher_preserves_conflicts_in_reference_profile():
    researcher = ConnectorSongResearcher(
        connectors=[
            ClaimsConnector([claim("key_one", "key", "A major", source="one", confidence=0.8)]),
            ClaimsConnector([claim("key_two", "key", "C major", source="two", confidence=0.78)]),
        ]
    )

    profile = researcher.research("Conflict Song")

    assert profile.knowledge is not None
    assert profile.knowledge.conflicts[0].claim_type == "key"
    assert profile.audio is not None
    assert profile.audio.key_confidence < 0.7
    assert any(note.code == "conflicting_key_claims" for note in profile.audio.analysis_notes)


def test_research_endpoint_persists_connector_profile(monkeypatch):
    researcher = ConnectorSongResearcher(
        connectors=[ClaimsConnector([claim("tempo", "tempo", "111 BPM", confidence=0.8)])]
    )
    monkeypatch.setattr(api, "_song_researcher", lambda: researcher)
    client = TestClient(api.app)

    response = client.post("/references/research", json={"query": "Space Cowboy"})

    assert response.status_code == 200
    body = response.json()
    assert body["knowledge"]["profile_id"].startswith("song_")
    assert body["audio"]["tempo_bpm"] == 111
    assert api.REFERENCE_STORE.get(body["reference_id"]) is not None
