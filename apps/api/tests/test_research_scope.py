import time

from music_assistant.application.answer_music_question import AnswerMusicQuestion
from music_assistant.domain.audio_profile import ReferenceProfile, ReferenceSource
from music_assistant.infrastructure.web_research.researcher import (
    ConnectorSongResearcher,
    DefaultSongResearcher,
    classify_research_scope,
)
from music_assistant.ports.web_search import SearchResult


class _Search:
    def search(self, _query: str, *, limit: int = 10):
        return [
            SearchResult(url=f"https://fixture.test/{index}", title=f"Page {index}", site="Fixture")
            for index in range(4)
        ][:limit]


class _SlowFetcher:
    def fetch(self, _url: str) -> str:
        time.sleep(0.03)
        return """
        <html><body>
        The production uses distorted guitars, electric bass, and live drums for a raw sound.
        Its groove emphasizes a heavy backbeat and loose rhythmic feel.
        </body></html>
        """


class _BroadStub:
    def __init__(self):
        self.calls = []

    def research(self, query: str) -> ReferenceProfile:
        self.calls.append(query)
        return ReferenceProfile(
            reference_id="ref_broad",
            source=ReferenceSource(reference_id="ref_broad", kind="metadata", label=query, uri="research://broad", authorized=True),
        )


def test_research_scope_distinguishes_song_from_broader_context():
    assert classify_research_scope("Smells Like Teen Spirit by Nirvana") == "song"
    assert classify_research_scope("the production style of Nirvana") == "artist"
    assert classify_research_scope("the album Nevermind") == "album"
    assert classify_research_scope("1990s grunge era") == "era"
    assert classify_research_scope("grunge genre") == "genre"


def test_connector_pipeline_delegates_broad_queries_but_keeps_song_queries_specialized():
    broad = _BroadStub()
    researcher = ConnectorSongResearcher(connectors=[], broad_researcher=broad)

    profile = researcher.research("the production style of Nirvana")

    assert profile.reference_id == "ref_broad"
    assert broad.calls == ["the production style of Nirvana"]


def test_broad_research_extracts_reusable_production_evidence_in_parallel():
    researcher = DefaultSongResearcher(search=_Search(), fetcher=_SlowFetcher())
    started = time.perf_counter()

    profile = researcher.research("1990s grunge production era")
    elapsed = time.perf_counter() - started

    assert elapsed < 0.09  # four 30 ms fetches would take ~120 ms sequentially
    assert profile.knowledge is not None
    claim_types = {claim.claim_type for claim in profile.knowledge.evidence_claims}
    assert {"timbre", "groove"}.issubset(claim_types)
    assert profile.research_evidence
    followup = AnswerMusicQuestion().execute("What evidence did you find?", profile)
    assert followup.evidence
    assert "strongest findings" in followup.answer
