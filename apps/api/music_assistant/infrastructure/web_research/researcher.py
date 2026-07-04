"""Default orchestration for research-only song analysis."""

from __future__ import annotations

from music_assistant.domain.audio_profile import (
    AnalysisNote,
    AudioProfile,
    ReferenceProfile,
    ReferenceSource,
    ResearchEvidence,
    SongKnowledgeProfile,
)
from music_assistant.infrastructure.web_research.connectors import CifraClubConnector, HookTheoryConnector
from music_assistant.infrastructure.web_research.fetch import UrlLibPageFetcher
from music_assistant.infrastructure.web_research.fusion import EvidenceFuser
from music_assistant.infrastructure.web_research.parsers import GenericSongPageParser
from music_assistant.infrastructure.web_research.search import SeededWebSearch
from music_assistant.ports.page_fetcher import PageFetcher
from music_assistant.ports.song_researcher import SongResearcher
from music_assistant.ports.song_source_connector import ConnectorResult, ResolvedSongQuery, SongSourceConnector
from music_assistant.ports.web_search import WebSearch


class DefaultSongResearcher(SongResearcher):
    def __init__(
        self,
        *,
        search: WebSearch | None = None,
        fetcher: PageFetcher | None = None,
        parser: GenericSongPageParser | None = None,
        fuser: EvidenceFuser | None = None,
    ) -> None:
        self.search = search or SeededWebSearch()
        self.fetcher = fetcher or UrlLibPageFetcher()
        self.parser = parser or GenericSongPageParser()
        self.fuser = fuser or EvidenceFuser()

    def research(self, query: str) -> ReferenceProfile:
        pages = []
        for result in self.search.search(query, limit=12):
            try:
                html_text = self.fetcher.fetch(result.url)
            except RuntimeError:
                continue
            page = self.parser.parse(result, html_text)
            if page.claims:
                pages.append(page)
        return self.fuser.fuse(query, pages)


class ConnectorSongResearcher(SongResearcher):
    def __init__(
        self,
        *,
        connectors: list[SongSourceConnector] | None = None,
        fuser: EvidenceFuser | None = None,
    ) -> None:
        self.connectors = connectors or [HookTheoryConnector(), CifraClubConnector()]
        self.fuser = fuser or EvidenceFuser()

    def research(self, query: str) -> ReferenceProfile:
        resolved = ResolvedSongQuery(title=query)
        results = [connector.collect(resolved) for connector in self.connectors]
        knowledge = self.fuser.fuse_connector_results(resolved, results)
        return _reference_from_knowledge(query, knowledge, results)


def _reference_from_knowledge(
    query: str,
    knowledge: SongKnowledgeProfile,
    results: list[ConnectorResult],
) -> ReferenceProfile:
    reference_id = knowledge.profile_id.replace("song_", "ref_", 1)
    tempo, tempo_confidence = _tempo_from_claims(knowledge)
    key, key_confidence, notes = _key_from_knowledge(knowledge)
    notes.extend(_notes_from_failures(results))
    confidence = max(tempo_confidence, key_confidence)
    evidence = [
        ResearchEvidence(
            url=claim.source_url,
            site=claim.source_name,
            claim_type=claim.claim_type,
            value=claim.value,
            confidence=claim.confidence,
            snippet=claim.snippet,
        )
        for claim in knowledge.evidence_claims
    ]
    audio = AudioProfile(
        duration_seconds=0.0,
        tempo_bpm=tempo,
        tempo_confidence=tempo_confidence,
        key=key,
        key_confidence=key_confidence,
        confidence=confidence,
        overall_confidence=confidence,
        analysis_notes=notes,
    )
    return ReferenceProfile(
        reference_id=reference_id,
        source=ReferenceSource(
            reference_id=reference_id,
            kind="metadata",
            label=query,
            uri=f"research://{query}",
            authorized=True,
        ),
        audio=audio,
        summary=_summary_from_knowledge(knowledge, results),
        research_evidence=evidence,
        knowledge=knowledge,
    )


def _tempo_from_claims(knowledge: SongKnowledgeProfile) -> tuple[float | None, float]:
    tempo_claims = [claim for claim in knowledge.evidence_claims if claim.claim_type == "tempo"]
    values: list[float] = []
    confidences: list[float] = []
    for claim in tempo_claims:
        import re

        match = re.search(r"(\d+(?:\.\d+)?)", claim.normalized_value or claim.value)
        if match:
            values.append(float(match.group(1)))
            confidences.append(claim.confidence)
    if not values:
        return None, 0.0
    return round(sum(values) / len(values), 1), round(sum(confidences) / len(confidences), 2)


def _key_from_knowledge(knowledge: SongKnowledgeProfile) -> tuple[str | None, float, list[AnalysisNote]]:
    key_claims = [claim for claim in knowledge.evidence_claims if claim.claim_type == "key"]
    if not key_claims:
        return None, 0.0, []
    notes: list[AnalysisNote] = []
    key_conflicts = [conflict for conflict in knowledge.conflicts if conflict.claim_type == "key"]
    if key_conflicts:
        notes.append(
            AnalysisNote(
                code="conflicting_key_claims",
                message="Different sources disagree on the likely key.",
                severity="warning",
            )
        )
        return key_claims[0].value, min(0.65, key_claims[0].confidence * 0.7), notes
    best = max(key_claims, key=lambda claim: claim.confidence)
    return best.value, best.confidence, notes


def _notes_from_failures(results: list[ConnectorResult]) -> list[AnalysisNote]:
    notes: list[AnalysisNote] = []
    for result in results:
        for failure in result.failures:
            notes.append(
                AnalysisNote(
                    code=f"source_{failure.status}",
                    message=f"{failure.source_name}: {failure.reason}",
                    severity="warning",
                )
            )
    return notes


def _summary_from_knowledge(knowledge: SongKnowledgeProfile, results: list[ConnectorResult]) -> str:
    if not knowledge.evidence_claims:
        if any(result.failures for result in results):
            return "No source-backed claims found; some sources were blocked or unavailable."
        return "No source-backed claims found for this song yet."
    source_count = len({claim.source_name for claim in knowledge.evidence_claims})
    parts = [f"Research found {len(knowledge.evidence_claims)} source-backed claims from {source_count} sources."]
    if knowledge.conflicts:
        parts.append(f"Preserved {len(knowledge.conflicts)} evidence conflict(s).")
    if any(result.failures for result in results):
        parts.append("Some sources were blocked or unavailable.")
    return " ".join(parts)
