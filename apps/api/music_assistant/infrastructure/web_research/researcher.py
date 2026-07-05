"""Default orchestration for research-only song analysis."""

from __future__ import annotations

import re

from music_assistant.domain.audio_profile import (
    AnalysisNote,
    AudioProfile,
    EvidenceClaim,
    ReferenceProfile,
    ReferenceSource,
    ResearchEvidence,
    SongKnowledgeProfile,
)
from music_assistant.infrastructure.web_research.connectors import (
    CifraClubConnector,
    HookTheoryConnector,
    LaCuerdaConnector,
    SongsterrConnector,
)
from music_assistant.infrastructure.web_research.fetch import UrlLibPageFetcher
from music_assistant.infrastructure.web_research.fusion import EvidenceFuser
from music_assistant.infrastructure.web_research.parsers import GenericSongPageParser
from music_assistant.infrastructure.web_research.search import SeededWebSearch
from music_assistant.infrastructure.web_research.songsterr_tabs import (
    InMemorySongsterrTabStore,
    SongsterrTabBundle,
    SongsterrTabLoader,
)
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
        search: WebSearch | None = None,
        fuser: EvidenceFuser | None = None,
        songsterr_tab_loader: SongsterrTabLoader | None = None,
        songsterr_tab_store: InMemorySongsterrTabStore | None = None,
    ) -> None:
        self.connectors = connectors or [
            HookTheoryConnector(),
            CifraClubConnector(),
            LaCuerdaConnector(),
            SongsterrConnector(),
        ]
        self.search = search or SeededWebSearch()
        self.fuser = fuser or EvidenceFuser()
        self.songsterr_tab_loader = songsterr_tab_loader or (SongsterrTabLoader() if songsterr_tab_store is not None else None)
        self.songsterr_tab_store = songsterr_tab_store

    def research(self, query: str) -> ReferenceProfile:
        resolved = _resolve_song_query(query)
        search_results = self.search.search(_search_query(resolved), limit=12)
        results = [
            _collect_with_candidates(connector, resolved, search_results)
            for connector in self.connectors
        ]
        bundle = _load_songsterr_tab_bundle(results, resolved, self.songsterr_tab_loader)
        if bundle is not None:
            results.append(_connector_result_from_songsterr_bundle(resolved, bundle))
        knowledge = self.fuser.fuse_connector_results(resolved, results)
        profile = _reference_from_knowledge(query, knowledge, results)
        if bundle is not None and self.songsterr_tab_store is not None:
            self.songsterr_tab_store.save(profile.reference_id, bundle)
        return profile


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


def _load_songsterr_tab_bundle(
    results: list[ConnectorResult],
    resolved: ResolvedSongQuery,
    loader,
) -> SongsterrTabBundle | None:
    if loader is None:
        return None
    songsterr_results = [result for result in results if result.source_name == "Songsterr" and result.claims]
    if not songsterr_results:
        return None
    load = getattr(loader, "load", None)
    if load is not None:
        bundle = load(resolved)
        if bundle is not None:
            return bundle
    for result in songsterr_results:
        source_url = result.query.source_url
        if source_url and "/a/wsa/" in source_url:
            bundle = loader.load_from_tab_url(source_url, resolved)
            if bundle is not None:
                return bundle
    return None


def _connector_result_from_songsterr_bundle(
    resolved: ResolvedSongQuery,
    bundle: SongsterrTabBundle,
) -> ConnectorResult:
    claims: list[EvidenceClaim] = []
    source_url = bundle.source_url
    if bundle.tempo_bpm is not None:
        claims.append(
            _songsterr_bundle_claim(
                "songsterr_tempo",
                "tempo",
                f"{bundle.tempo_bpm:g} BPM",
                source_url,
                0.72,
                f"Songsterr tab tempo: {bundle.tempo_bpm:g} BPM",
            )
        )
    if bundle.instrument_names:
        instruments = ", ".join(bundle.instrument_names)
        claims.append(
            _songsterr_bundle_claim(
                "songsterr_full_tab_tracks",
                "instrumentation",
                f"Songsterr full tab tracks loaded: {instruments}",
                source_url,
                0.78,
                f"Loaded full Songsterr track payloads for {instruments}",
            )
        )
    sections = _sections_from_bundle(bundle)
    for order, section in enumerate(sections):
        claims.append(
            _songsterr_bundle_claim(
                f"songsterr_section_{order}",
                "section",
                section,
                source_url,
                0.68,
                f"Songsterr tab marker: {section}",
                section_name=_normalize_songsterr_section(section),
            )
        )
    for track in bundle.tracks:
        summary = (
            f"{track.instrument_family.title()} tab loaded from Songsterr: "
            f"{track.name} ({len(track.measures)} measures, {track.note_count} note events)"
        )
        claims.append(
            _songsterr_bundle_claim(
                f"songsterr_track_{track.part_id}",
                "tab",
                summary,
                source_url,
                0.8,
                summary,
            )
        )
        if track.instrument_family in {"bass", "drums"}:
            groove = _track_groove_summary(track)
            claims.append(
                _songsterr_bundle_claim(
                    f"songsterr_trait_{track.part_id}",
                    "trait",
                    groove,
                    source_url,
                    0.66,
                    groove,
                )
            )
    for index, warning in enumerate(bundle.warnings):
        claims.append(
            _songsterr_bundle_claim(
                f"songsterr_warning_{index}",
                "metadata",
                f"Songsterr tab warning: {warning}",
                source_url,
                0.35,
                warning,
            )
        )
    return ConnectorResult(source_name="Songsterr", query=resolved.model_copy(update={"source_url": source_url}), fetch_status="fetched", claims=claims)


def _songsterr_bundle_claim(
    claim_id: str,
    claim_type: str,
    value: str,
    source_url: str,
    confidence: float,
    snippet: str,
    *,
    section_name: str | None = None,
) -> EvidenceClaim:
    return EvidenceClaim(
        claim_id=claim_id,
        claim_type=claim_type,  # type: ignore[arg-type]
        value=value,
        normalized_value=value,
        section_name=section_name,
        source_name="Songsterr",
        source_url=source_url,
        extraction_method="api",
        confidence=confidence,
        snippet=snippet[:280],
    )


def _sections_from_bundle(bundle: SongsterrTabBundle) -> list[str]:
    sections: list[str] = []
    for track in bundle.tracks:
        for measure in track.measures:
            if measure.marker and measure.marker not in sections:
                sections.append(measure.marker)
    return sections


def _normalize_songsterr_section(section: str) -> str:
    value = section.strip().lower()
    value = re.sub(r"\b(i{1,3}|iv|v|vi{0,3}|\d+)\b$", "", value).strip()
    aliases = {
        "verse": "verse",
        "chorus": "chorus",
        "intro": "intro",
        "outro": "outro",
        "bridge": "bridge",
        "break": "break",
        "solo": "solo",
    }
    return aliases.get(value, value)


def _track_groove_summary(track) -> str:
    markers = [measure.marker for measure in track.measures if measure.marker]
    marker_text = ", ".join(markers[:6]) if markers else "no section markers"
    return (
        f"{track.instrument_family.title()} has {len(track.measures)} tab measures, "
        f"{track.note_count} note events, and markers: {marker_text}"
    )


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


def _resolve_song_query(query: str) -> ResolvedSongQuery:
    cleaned = re.sub(r"\s+", " ", query).strip()
    by_match = re.match(r"(?P<title>.+?)\s+by\s+(?P<artist>.+)$", cleaned, flags=re.IGNORECASE)
    if by_match:
        return ResolvedSongQuery(
            title=_clean_song_part(by_match.group("title")),
            artist=_clean_song_part(by_match.group("artist")),
        )
    return ResolvedSongQuery(title=cleaned)


def _clean_song_part(value: str) -> str:
    cleaned = value.strip(" \t\r\n\"'")
    return re.sub(r"\s+", " ", cleaned)


def _search_query(query: ResolvedSongQuery) -> str:
    return " ".join(part for part in [query.title, query.artist] if part).strip()


def _collect_with_candidates(
    connector: SongSourceConnector,
    resolved: ResolvedSongQuery,
    search_results: list,
) -> ConnectorResult:
    attempts = [resolved]
    attempts.extend(
        resolved.model_copy(update={"source_url": result.url})
        for result in search_results
        if _matches_source(connector.source_name, result.site, result.url)
    )
    failures = []
    last_result: ConnectorResult | None = None
    seen_urls: set[str | None] = set()
    for attempt in attempts:
        if attempt.source_url in seen_urls:
            continue
        seen_urls.add(attempt.source_url)
        result = connector.collect(attempt)
        if result.claims:
            return result.model_copy(update={"failures": failures + result.failures})
        failures.extend(result.failures)
        last_result = result
    if last_result is None:
        return connector.collect(resolved)
    return last_result.model_copy(update={"failures": failures})


def _matches_source(source_name: str, site: str, url: str) -> bool:
    source = source_name.lower().replace(" ", "")
    site_key = site.lower().replace(" ", "")
    url_key = url.lower()
    if source and source in site_key:
        return True
    if source == "hooktheory":
        return "hooktheory.com" in url_key
    if source == "cifraclub":
        return "cifraclub.com" in url_key
    if source == "lacuerda":
        return "lacuerda.net" in url_key
    if source == "songsterr":
        return "songsterr.com" in url_key
    if source == "ultimateguitar":
        return "ultimate-guitar.com" in url_key
    if source == "musescore":
        return "musescore.com" in url_key
    return False
