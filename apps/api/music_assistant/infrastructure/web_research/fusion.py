"""Fuse web research claims into a compact reference profile."""

from __future__ import annotations

import hashlib
import re
from collections import defaultdict

from music_assistant.domain.reference_profile import (
    AnalysisNote,
    MusicProfile,
    ReferenceProfile,
    ReferenceSource,
    ResearchEvidence,
)
from music_assistant.ports.song_researcher import ResearchPage


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
        music = MusicProfile(
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
            music=music,
            summary=" ".join(summary_parts),
            research_evidence=evidence,
        )


def _reference_id(query: str) -> str:
    digest = hashlib.sha1(query.strip().lower().encode("utf-8")).hexdigest()[:12]
    return f"ref_{digest}"


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
