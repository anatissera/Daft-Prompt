"""Fuse web research claims into a compact reference profile."""

from __future__ import annotations

import hashlib
import re
from collections import defaultdict

from music_assistant.domain.audio_profile import (
    AnalysisNote,
    AudioProfile,
    EvidenceClaim,
    EvidenceConflict,
    MissingData,
    ReferenceProfile,
    ReferenceSource,
    ResearchEvidence,
    SongIdentity,
    SongKnowledgeProfile,
    SongSectionProfile,
)
from music_assistant.ports.song_researcher import ResearchPage
from music_assistant.ports.song_source_connector import ConnectorResult, ResolvedSongQuery


_BPM_RE = re.compile(r"(?P<bpm>\d+(?:\.\d+)?)\s*(?:bpm)?", re.IGNORECASE)


class EvidenceFuser:
    def fuse(self, query: str, pages: list[ResearchPage]) -> ReferenceProfile:
        reference_id = _reference_id(query)
        grouped = _group_claims(pages)
        tempo_bpm, tempo_confidence = _fuse_tempo(grouped.get("tempo", []))
        key, key_confidence, notes = _fuse_key(grouped.get("key", []))
        evidence = [
            ResearchEvidence(
                url=page.url,
                site=page.site,
                claim_type=claim.type,
                value=claim.value,
                confidence=claim.confidence,
                snippet=claim.snippet,
            )
            for page in pages
            for claim in page.claims
        ]
        confidence = max(tempo_confidence, key_confidence)
        audio = AudioProfile(
            duration_seconds=0.0,
            tempo_bpm=tempo_bpm,
            tempo_confidence=tempo_confidence,
            key=key,
            key_confidence=key_confidence,
            confidence=confidence,
            overall_confidence=confidence,
            analysis_notes=notes,
        )
        source_count = len({page.url for page in pages if page.claims})
        summary_parts = [f"Research found {len(evidence)} musical claims from {source_count} sources."]
        if tempo_bpm is not None:
            summary_parts.append(f"Likely tempo is around {tempo_bpm:g} BPM.")
        if key:
            summary_parts.append(f"Likely key is {key}.")
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
            summary=" ".join(summary_parts),
            research_evidence=evidence,
        )

    def fuse_connector_results(
        self,
        query: ResolvedSongQuery,
        results: list[ConnectorResult],
    ) -> SongKnowledgeProfile:
        claims = [claim for result in results for claim in result.claims]
        sections = _build_sections(claims)
        conflicts = _build_conflicts(claims)
        summary = _confidence_summary(claims, conflicts)
        missing = _missing_data(claims, sections)
        return SongKnowledgeProfile(
            profile_id=_song_profile_id(query),
            identity=SongIdentity(
                title=query.title,
                artist=query.artist,
                album=query.album,
                year=query.year,
                version=query.version,
            ),
            evidence_claims=claims,
            sections=sections,
            conflicts=conflicts,
            missing_data=missing,
            confidence_summary=summary,
        )


def _reference_id(query: str) -> str:
    digest = hashlib.sha1(query.strip().lower().encode("utf-8")).hexdigest()[:12]
    return f"ref_{digest}"


def _song_profile_id(query: ResolvedSongQuery) -> str:
    parts = [query.artist or "", query.title, query.version or ""]
    slug = re.sub(r"[^a-z0-9]+", "_", " ".join(parts).lower()).strip("_")
    return f"song_{slug or _reference_id(query.title)}"


def _build_sections(claims: list[EvidenceClaim]) -> list[SongSectionProfile]:
    section_names = []
    for claim in claims:
        if claim.section_name and claim.section_name not in section_names:
            section_names.append(claim.section_name)
        elif claim.claim_type == "section" and claim.value.lower() not in section_names:
            section_names.append(claim.value.lower())

    sections: list[SongSectionProfile] = []
    for index, name in enumerate(section_names, start=1):
        matching = [
            claim
            for claim in claims
            if claim.section_name == name or (claim.claim_type == "section" and claim.value.lower() == name)
        ]
        sections.append(
            SongSectionProfile(
                name=name,
                order=index,
                chord_claims=[claim for claim in matching if claim.claim_type == "chord_progression"],
                lyric_claims=[claim for claim in matching if claim.claim_type == "lyrics"],
                key_claims=[claim for claim in matching if claim.claim_type == "key"],
                instrument_claims=[
                    claim
                    for claim in matching
                    if claim.claim_type in {"instrumentation", "groove", "timbre", "trait"}
                ],
                evidence_ids=[claim.claim_id for claim in matching],
            )
        )
    return sections


def _build_conflicts(claims: list[EvidenceClaim]) -> list[EvidenceConflict]:
    conflicts: list[EvidenceConflict] = []
    key_claims = [claim for claim in claims if claim.claim_type == "key"]
    if _distinct_normalized_values(key_claims) > 1:
        conflicts.append(
            EvidenceConflict(
                conflict_id="key_conflict",
                claim_type="key",
                description="Sources disagree on the likely key.",
                claims=key_claims,
            )
        )

    chord_claims_by_section: dict[str, list[EvidenceClaim]] = defaultdict(list)
    for claim in claims:
        if claim.claim_type == "chord_progression":
            chord_claims_by_section[claim.section_name or "global"].append(claim)
    for section, section_claims in chord_claims_by_section.items():
        if _distinct_chord_values(section_claims) <= 1:
            continue
        if _same_source_extended_repeat(section_claims):
            continue
        has_capo_hint = any("capo" in " ".join(claim.notes).lower() for claim in section_claims)
        conflicts.append(
            EvidenceConflict(
                conflict_id=f"{section}_chord_progression_conflict",
                claim_type="chord_progression",
                description=(
                    f"Sources disagree on {section} chords; capo or transposition may explain the difference."
                    if has_capo_hint
                    else f"Sources disagree on {section} chords."
                ),
                claims=section_claims,
                resolution="capo_or_transposition_possible" if has_capo_hint else None,
            )
        )
    return conflicts


def _confidence_summary(
    claims: list[EvidenceClaim],
    conflicts: list[EvidenceConflict],
) -> dict[str, str]:
    summary: dict[str, str] = {}
    conflict_types = {conflict.claim_type for conflict in conflicts}
    tempo_claims = [claim for claim in claims if claim.claim_type == "tempo"]
    key_claims = [claim for claim in claims if claim.claim_type == "key"]
    chord_claims = [claim for claim in claims if claim.claim_type == "chord_progression"]
    if tempo_claims:
        summary["tempo"] = _aggregate_label(tempo_claims)
    if "key" in conflict_types:
        summary["key"] = "conflicting"
    elif key_claims:
        summary["key"] = _aggregate_label(key_claims)
    if "chord_progression" in conflict_types:
        summary["harmony"] = "conflicting"
    elif chord_claims:
        summary["harmony"] = _aggregate_label(chord_claims)
    return summary


def _missing_data(claims: list[EvidenceClaim], sections: list[SongSectionProfile]) -> list[MissingData]:
    present = {claim.claim_type for claim in claims}
    missing: list[MissingData] = []
    for field, reason in [
        ("tempo", "No source-backed tempo claim found."),
        ("key", "No source-backed key claim found."),
        ("harmony", "No source-backed chord or progression claim found."),
    ]:
        required = "chord_progression" if field == "harmony" else field
        if required not in present:
            missing.append(
                MissingData(
                    field=field,
                    reason=reason,
                    needed_evidence=f"source claim for {field}",
                )
            )
    if sections and all(section.start_seconds is None for section in sections):
        missing.append(
            MissingData(
                field="section_timestamps",
                reason="Sources provide sections but no timing.",
                needed_evidence="timestamped source or audio analysis",
            )
        )
    return missing


def _aggregate_label(claims: list[EvidenceClaim]) -> str:
    if not claims:
        return "missing"
    average = sum(claim.confidence for claim in claims) / len(claims)
    if len({claim.source_name for claim in claims}) > 1:
        average = min(0.95, average + 0.05)
    return _confidence_word(average)


def _confidence_word(confidence: float) -> str:
    if confidence >= 0.75:
        return "high"
    if confidence >= 0.5:
        return "medium"
    return "low"


def _distinct_normalized_values(claims: list[EvidenceClaim]) -> int:
    values = {
        _normalize_key(claim.normalized_value or claim.value)
        for claim in claims
        if (claim.normalized_value or claim.value).strip()
    }
    return len(values)


def _distinct_chord_values(claims: list[EvidenceClaim]) -> int:
    values = {_normalize_chord_progression(claim.normalized_value or claim.value) for claim in claims}
    return len({value for value in values if value})


def _normalize_chord_progression(value: str) -> str:
    return re.sub(r"[^a-g0-9#bmmajindimsusaugadd/]+", " ", value.lower()).strip()


def _same_source_extended_repeat(claims: list[EvidenceClaim]) -> bool:
    sources = {claim.source_name for claim in claims}
    if len(sources) != 1:
        return False
    cores = {_progression_core_signature(claim.normalized_value or claim.value) for claim in claims}
    cores.discard("")
    return len(cores) == 1


def _progression_core_signature(value: str) -> str:
    bars = _bar_segments(value)
    repeat = _find_repeating_cell(tuple(bars))
    if repeat is not None:
        cell, _, _ = repeat
        return " | ".join(_normalize_bar(bar) for bar in cell)
    return " | ".join(_normalize_bar(bar) for bar in bars[:8])


def _bar_segments(value: str) -> list[str]:
    return [
        " ".join(segment.strip().split())
        for segment in value.split("|")
        if segment.strip()
    ]


def _find_repeating_cell(bars: tuple[str, ...]) -> tuple[tuple[str, ...], int, tuple[str, ...]] | None:
    for cell_size in [1, 2, 4, 8]:
        if len(bars) < cell_size * 2:
            continue
        cell = bars[:cell_size]
        repeat_count = 1
        cursor = cell_size
        while tuple(bars[cursor: cursor + cell_size]) == cell:
            repeat_count += 1
            cursor += cell_size
        covered = repeat_count * cell_size
        if repeat_count >= 2 and covered >= min(len(bars), cell_size * 2):
            return cell, repeat_count, bars[covered:]
    return None


def _normalize_bar(value: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-g0-9#bmmajindimsusaugadd()/]+", " ", value.lower())).strip()


def _group_claims(pages: list[ResearchPage]) -> dict[str, list[tuple[str, float]]]:
    grouped: dict[str, list[tuple[str, float]]] = defaultdict(list)
    for page in pages:
        for claim in page.claims:
            grouped[claim.type.lower()].append((claim.value, claim.confidence))
    return grouped


def _fuse_tempo(claims: list[tuple[str, float]]) -> tuple[float | None, float]:
    bpms: list[tuple[float, float]] = []
    for value, confidence in claims:
        match = _BPM_RE.search(value)
        if match:
            bpms.append((float(match.group("bpm")), confidence))
    if not bpms:
        return None, 0.0
    total_weight = sum(confidence for _, confidence in bpms) or 1.0
    bpm = sum(value for value, _ in bpms) / len(bpms)
    spread = max(value for value, _ in bpms) - min(value for value, _ in bpms)
    confidence = min(0.95, total_weight / len(bpms))
    if spread > 4:
        confidence *= 0.65
    return round(bpm, 1), round(confidence, 2)


def _fuse_key(claims: list[tuple[str, float]]) -> tuple[str | None, float, list[AnalysisNote]]:
    if not claims:
        return None, 0.0, []
    scores: dict[str, float] = defaultdict(float)
    for value, confidence in claims:
        scores[_normalize_key(value)] += confidence
    ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    top_key, top_score = ranked[0]
    total = sum(scores.values()) or 1.0
    confidence = top_score / total
    notes: list[AnalysisNote] = []
    if len(ranked) > 1 and ranked[1][1] >= top_score * 0.75:
        confidence *= 0.65
        notes.append(
            AnalysisNote(
                code="conflicting_key_claims",
                message="Different sources disagree on the likely key.",
                severity="warning",
            )
        )
    return top_key, round(confidence, 2), notes


def _normalize_key(value: str) -> str:
    cleaned = value.strip().replace("♯", "#").replace("♭", "b")
    cleaned = re.sub(r"\s+", " ", cleaned)
    lower = cleaned.lower()
    if lower.endswith("m") and not lower.endswith(" major"):
        return f"{cleaned[:-1].strip()} minor"
    if "minor" in lower:
        root = re.sub(r"\bminor\b", "", cleaned, flags=re.IGNORECASE).strip()
        return f"{root} minor"
    if "major" in lower:
        root = re.sub(r"\bmajor\b", "", cleaned, flags=re.IGNORECASE).strip()
        return f"{root} major"
    return f"{cleaned} major"
