"""Convert local audio analysis into traceable knowledge-profile evidence."""

from __future__ import annotations

import re

from music_assistant.domain.audio_profile import (
    AnalysisNote,
    AudioProfile,
    EvidenceClaim,
    EvidenceConflict,
    ReferenceProfile,
    SongIdentity,
    SongKnowledgeProfile,
    SongSectionProfile,
)


def enrich_profile_with_audio(
    audio_profile: ReferenceProfile,
    *,
    base_profile: ReferenceProfile | None = None,
) -> ReferenceProfile:
    audio = audio_profile.audio
    if audio is None:
        return audio_profile

    base_knowledge = base_profile.knowledge if base_profile and base_profile.knowledge else None
    identity = (
        base_knowledge.identity
        if base_knowledge is not None
        else SongIdentity(title=audio_profile.source.label)
    )
    existing_claims = list(base_knowledge.evidence_claims) if base_knowledge else []
    audio_claims = _audio_claims(audio, audio_profile.reference_id)
    all_claims = [*existing_claims, *audio_claims]
    sections = _merge_sections(base_knowledge, audio_claims)
    conflicts = list(base_knowledge.conflicts) if base_knowledge else []
    conflicts.extend(_web_audio_conflicts(existing_claims, audio_claims))
    notes = list(audio.analysis_notes)
    if any(conflict.claim_type == "key" for conflict in conflicts):
        notes.append(
            AnalysisNote(
                code="web_audio_key_conflict",
                message="Audio key estimate disagrees with at least one web source.",
                severity="warning",
            )
        )
    enriched_audio = audio.model_copy(update={"analysis_notes": notes})
    knowledge = SongKnowledgeProfile(
        profile_id=base_knowledge.profile_id if base_knowledge else audio_profile.reference_id.replace("ref_", "song_", 1),
        identity=identity,
        metadata=dict(base_knowledge.metadata) if base_knowledge else {},
        evidence_claims=all_claims,
        sections=sections,
        traits=list(base_knowledge.traits) if base_knowledge else [],
        conflicts=conflicts,
        missing_data=list(base_knowledge.missing_data) if base_knowledge else [],
        confidence_summary=dict(base_knowledge.confidence_summary) if base_knowledge else {},
        audio=enriched_audio,
    )
    return audio_profile.model_copy(
        update={
            "audio": enriched_audio,
            "knowledge": knowledge,
            "summary": audio_profile.summary or (base_profile.summary if base_profile else ""),
        }
    )


def _audio_claims(audio: AudioProfile, reference_id: str) -> list[EvidenceClaim]:
    claims: list[EvidenceClaim] = []
    source_url = f"local-audio://{reference_id}"
    if audio.tempo_bpm is not None:
        claims.append(
            _claim(
                "tempo",
                f"{round(audio.tempo_bpm, 1):g} BPM",
                source_url,
                audio.tempo_confidence,
                "Audio tempo estimate.",
            )
        )
    if audio.key:
        notes = ["approximate"] if audio.key_confidence < 0.5 else []
        claims.append(_claim("key", audio.key, source_url, audio.key_confidence, "Audio key estimate.", notes=notes))
    for section in audio.sections:
        claims.append(
            _claim(
                "section",
                section.name,
                source_url,
                section.confidence,
                f"Audio section estimate: {section.name}.",
                section_name=section.name,
                notes=["approximate"],
            )
        )
        if section.energy is not None:
            claims.append(
                _claim(
                    "audio_estimate",
                    f"energy {section.energy:.2f}",
                    source_url,
                    section.energy_confidence,
                    f"Estimated section energy for {section.name}.",
                    section_name=section.name,
                    notes=["approximate"],
                )
            )
    for point in audio.energy_curve:
        claims.append(
            _claim(
                "audio_estimate",
                f"energy {point.energy:.2f} at {point.time_seconds:.1f}s",
                source_url,
                point.confidence,
                "Audio energy curve point.",
                notes=["approximate"],
            )
        )
    for estimate in audio.chord_estimates:
        if not estimate.chords:
            continue
        claims.append(
            _claim(
                "chord_progression",
                " - ".join(estimate.chords),
                source_url,
                estimate.confidence,
                "Audio chord estimate.",
                notes=["approximate", "probable"],
            )
        )
    claims.extend(_stem_listening_claims(audio, source_url))
    return claims


def _stem_listening_claims(audio: AudioProfile, source_url: str) -> list[EvidenceClaim]:
    """Deep-listening evidence (timbre / groove / dynamics per stem). Only stems
    the analyzer actually profiled produce claims; everything stays labeled as
    an approximate audio estimate."""
    claims: list[EvidenceClaim] = []
    if audio.mix_timbre is not None and audio.mix_timbre.confidence > 0.0:
        mix = audio.mix_timbre
        claims.append(
            _claim(
                "timbre",
                f"mix: {mix.brightness}, {mix.noisiness}, {mix.band_balance}",
                source_url,
                mix.confidence,
                mix.interpretation or "Timbre estimate for the full mix.",
                notes=["approximate"],
            )
        )
    if audio.ensemble is not None:
        for callout in audio.ensemble.callouts[:4]:
            claims.append(
                _claim(
                    "instrumentation",
                    callout,
                    source_url,
                    audio.ensemble.confidence,
                    "Arrangement change from the bar-aligned ensemble timeline.",
                    notes=["approximate"],
                )
            )
    for stem in audio.stems:
        if stem.timbre is not None and stem.timbre.confidence > 0.0:
            timbre = stem.timbre
            claims.append(
                _claim(
                    "timbre",
                    f"{stem.name}: {timbre.brightness}, {timbre.noisiness}, {timbre.band_balance}",
                    source_url,
                    timbre.confidence,
                    timbre.interpretation or f"Timbre estimate for the {stem.name} stem.",
                    notes=["approximate"],
                )
            )
        if stem.rhythm is not None and stem.rhythm.confidence > 0.0:
            rhythm = stem.rhythm
            value = f"{stem.name}: {rhythm.feel}, {rhythm.density}"
            if rhythm.syncopation >= 0.35:
                value += ", syncopated"
            claims.append(
                _claim(
                    "groove",
                    value,
                    source_url,
                    rhythm.confidence,
                    rhythm.interpretation or f"Groove estimate for the {stem.name} stem.",
                    notes=["approximate"],
                )
            )
        if stem.dynamics is not None:
            for event in stem.dynamics.events[:4]:
                description = (
                    f"{stem.name} builds through bars {event.start_bar}-{event.end_bar}"
                    if event.kind == "build"
                    else f"{stem.name} drops at bar {event.end_bar}"
                )
                claims.append(
                    _claim(
                        "audio_estimate",
                        description,
                        source_url,
                        stem.dynamics.confidence,
                        "Bar-aligned loudness event from the stem dynamics curve.",
                        notes=["approximate"],
                    )
                )
    return claims


def _claim(
    claim_type: str,
    value: str,
    source_url: str,
    confidence: float,
    snippet: str,
    *,
    section_name: str | None = None,
    notes: list[str] | None = None,
) -> EvidenceClaim:
    raw_id = f"audio:{claim_type}:{section_name or ''}:{value}".lower()
    return EvidenceClaim(
        claim_id=re.sub(r"[^a-z0-9]+", "_", raw_id).strip("_")[:96],
        claim_type=claim_type,  # type: ignore[arg-type]
        value=value,
        normalized_value=value,
        section_name=section_name,
        source_name="local audio analyzer",
        source_url=source_url,
        extraction_method="audio_analyzer",
        confidence=confidence,
        snippet=snippet,
        notes=notes or [],
    )


def _merge_sections(
    base_knowledge: SongKnowledgeProfile | None,
    audio_claims: list[EvidenceClaim],
) -> list[SongSectionProfile]:
    sections = list(base_knowledge.sections) if base_knowledge else []
    seen = {section.name for section in sections}
    for claim in audio_claims:
        if claim.section_name and claim.section_name not in seen:
            sections.append(
                SongSectionProfile(
                    name=claim.section_name,
                    order=len(sections) + 1,
                    evidence_ids=[claim.claim_id],
                )
            )
            seen.add(claim.section_name)
    return sections


def _web_audio_conflicts(
    existing_claims: list[EvidenceClaim],
    audio_claims: list[EvidenceClaim],
) -> list[EvidenceConflict]:
    conflicts: list[EvidenceConflict] = []
    web_keys = [claim for claim in existing_claims if claim.claim_type == "key"]
    audio_keys = [claim for claim in audio_claims if claim.claim_type == "key"]
    for audio_key in audio_keys:
        disagreeing = [claim for claim in web_keys if _normalize_key(claim.value) != _normalize_key(audio_key.value)]
        if disagreeing:
            conflicts.append(
                EvidenceConflict(
                    conflict_id="web_audio_key_conflict",
                    claim_type="key",
                    description="Web evidence and audio estimate disagree on the likely key.",
                    claims=[*disagreeing, audio_key],
                )
            )
    return conflicts


def _normalize_key(value: str) -> str:
    lower = value.strip().lower()
    if lower.endswith("m") and "minor" not in lower:
        return f"{lower[:-1].strip()} minor"
    return lower.replace("major", "major").replace("minor", "minor")
