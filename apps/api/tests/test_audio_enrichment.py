from __future__ import annotations

from music_assistant.application.audio_enrichment import enrich_profile_with_audio
from music_assistant.domain.audio_profile import (
    AudioProfile,
    ChordEstimate,
    EnergyPoint,
    EvidenceClaim,
    ReferenceProfile,
    ReferenceSource,
    SectionProfile,
    SongIdentity,
    SongKnowledgeProfile,
)


def source(reference_id: str = "ref_demo") -> ReferenceSource:
    return ReferenceSource(
        reference_id=reference_id,
        kind="upload",
        label="demo.wav",
        uri="local://demo.wav",
        authorized=True,
    )


def audio_profile(*, key: str = "A minor", key_confidence: float = 0.72, tempo: float = 111.0) -> ReferenceProfile:
    return ReferenceProfile(
        reference_id="ref_audio",
        source=source("ref_audio"),
        audio=AudioProfile(
            duration_seconds=90.0,
            tempo_bpm=tempo,
            tempo_confidence=0.8,
            key=key,
            key_confidence=key_confidence,
            energy_curve=[EnergyPoint(time_seconds=0, energy=0.4), EnergyPoint(time_seconds=45, energy=0.8)],
            chord_estimates=[
                ChordEstimate(start_seconds=30, end_seconds=45, chords=["Bm7", "E9", "Amaj7"], confidence=0.42)
            ],
            sections=[SectionProfile(name="chorus", start_seconds=30, end_seconds=60, energy=0.8, energy_confidence=0.7)],
        ),
    )


def web_profile() -> ReferenceProfile:
    key_claim = EvidenceClaim(
        claim_id="web_key",
        claim_type="key",
        value="A minor",
        source_name="Web",
        source_url="https://web.test",
        extraction_method="site_parser",
        confidence=0.74,
        snippet="Key: A minor",
    )
    return ReferenceProfile(
        reference_id="ref_web",
        source=source("ref_web"),
        knowledge=SongKnowledgeProfile(
            profile_id="song_demo",
            identity=SongIdentity(title="Demo Song", artist="Fixture Artist"),
            evidence_claims=[key_claim],
        ),
    )


def test_audio_only_enrichment_creates_audio_evidence_claims():
    enriched = enrich_profile_with_audio(audio_profile())

    assert enriched.knowledge is not None
    claim_types = {claim.claim_type for claim in enriched.knowledge.evidence_claims}
    assert {"tempo", "key", "section", "audio_estimate"} <= claim_types
    assert all(
        claim.extraction_method == "audio_analyzer"
        for claim in enriched.knowledge.evidence_claims
        if claim.source_name == "local audio analyzer"
    )


def test_audio_web_agreement_keeps_profile_without_conflict():
    enriched = enrich_profile_with_audio(audio_profile(), base_profile=web_profile())

    assert enriched.knowledge is not None
    assert not enriched.knowledge.conflicts
    assert any(claim.source_name == "Web" for claim in enriched.knowledge.evidence_claims)
    assert any(claim.extraction_method == "audio_analyzer" for claim in enriched.knowledge.evidence_claims)


def test_audio_web_conflict_is_preserved_as_profile_note():
    enriched = enrich_profile_with_audio(audio_profile(key="C major"), base_profile=web_profile())

    assert enriched.knowledge is not None
    assert any(conflict.claim_type == "key" for conflict in enriched.knowledge.conflicts)
    assert any(note.code == "web_audio_key_conflict" for note in enriched.audio.analysis_notes)


def test_low_confidence_audio_estimates_are_marked_approximate():
    enriched = enrich_profile_with_audio(audio_profile(key_confidence=0.32))

    assert enriched.knowledge is not None
    key_claim = next(claim for claim in enriched.knowledge.evidence_claims if claim.claim_type == "key")
    assert "approximate" in key_claim.notes
    chord_claim = next(claim for claim in enriched.knowledge.evidence_claims if claim.claim_type == "chord_progression")
    assert "approximate" in chord_claim.notes


def test_stem_listening_profiles_become_timbre_groove_and_dynamics_claims():
    from music_assistant.domain.audio_profile import (
        DynamicsEvent,
        RhythmProfile,
        StemDynamics,
        StemProfile,
        TimbreProfile,
    )

    profile = audio_profile()
    drums = StemProfile(
        name="drums",
        role="percussion",
        timbre=TimbreProfile(brightness="bright", noisiness="noisy", band_balance="high-heavy", confidence=0.6),
        rhythm=RhythmProfile(feel="swung", density="busy", syncopation=0.5, confidence=0.7),
        dynamics=StemDynamics(
            events=[DynamicsEvent(kind="build", start_bar=8, end_bar=15), DynamicsEvent(kind="drop", start_bar=15, end_bar=16)],
            confidence=0.5,
        ),
    )
    profile = profile.model_copy(update={"audio": profile.audio.model_copy(update={"stems": [drums]})})

    enriched = enrich_profile_with_audio(profile, base_profile=None)
    claims = enriched.knowledge.evidence_claims

    timbre = [c for c in claims if c.claim_type == "timbre"]
    groove = [c for c in claims if c.claim_type == "groove"]
    assert timbre and "drums: bright, noisy, high-heavy" == timbre[0].value
    assert groove and groove[0].value == "drums: swung, busy, syncopated"
    dynamics = [c for c in claims if "builds through bars 8-15" in c.value or "drops at bar 16" in c.value]
    assert len(dynamics) == 2
    assert all("approximate" in c.notes for c in timbre + groove + dynamics)


def test_stems_without_listening_profiles_emit_no_extra_claims():
    enriched = enrich_profile_with_audio(audio_profile(), base_profile=None)
    assert not [c for c in enriched.knowledge.evidence_claims if c.claim_type in ("timbre", "groove")]
