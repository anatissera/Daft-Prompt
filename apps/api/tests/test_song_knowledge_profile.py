from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from music_assistant.domain.audio_profile import (
    CompositionBrief,
    EvidenceClaim,
    EvidenceConflict,
    InstrumentTrait,
    ReferenceProfile,
    ReferenceSource,
    SongKnowledgeProfile,
    SongSectionProfile,
)


FIXTURE_DIR = Path(__file__).parent / "fixtures" / "song_knowledge"


def load_fixture(name: str) -> dict:
    return json.loads((FIXTURE_DIR / name).read_text(encoding="utf-8"))


def test_song_knowledge_profile_serializes_traceable_section_evidence():
    profile = SongKnowledgeProfile.model_validate(load_fixture("space_cowboy.json"))

    assert profile.identity.title == "Space Cowboy"
    assert profile.identity.artist == "Jamiroquai"
    assert profile.sections[1].name == "chorus"
    assert profile.sections[1].chord_claims[0].section_name == "chorus"
    assert profile.sections[1].lyric_claims[0].section_name == "chorus"
    assert profile.evidence_claims[0].confidence_label == "high"
    assert profile.missing_data == []

    dumped = profile.model_dump(mode="json")
    assert dumped["sections"][1]["chord_claims"][0]["extraction_method"] == "site_parser"
    assert dumped["evidence_claims"][0]["confidence_label"] == "high"


def test_profile_can_represent_conflicts_and_incomplete_data():
    conflicted = SongKnowledgeProfile.model_validate(load_fixture("conflicting_key_song.json"))
    incomplete = SongKnowledgeProfile.model_validate(load_fixture("incomplete_song.json"))

    assert conflicted.conflicts[0].claim_type == "key"
    assert {claim.value for claim in conflicted.conflicts[0].claims} == {"A major", "F# minor"}
    assert conflicted.confidence_summary["key"] == "conflicting"

    assert incomplete.missing_data[0].field == "section_timestamps"
    assert incomplete.sections[0].start_seconds is None
    assert incomplete.sections[0].timestamp_confidence is None


def test_evidence_claim_requires_source_and_bounded_confidence():
    with pytest.raises(ValidationError):
        EvidenceClaim(
            claim_id="bad",
            claim_type="tempo",
            value="118 BPM",
            source_name="",
            source_url="https://example.test/song",
            extraction_method="site_parser",
            confidence=1.2,
        )


def test_reference_profile_accepts_optional_song_knowledge_profile():
    knowledge = SongKnowledgeProfile.model_validate(load_fixture("space_cowboy.json"))
    reference = ReferenceProfile(
        reference_id="ref_space_cowboy",
        source=ReferenceSource(
            reference_id="ref_space_cowboy",
            kind="metadata",
            label="Jamiroquai - Space Cowboy",
            uri="research://space-cowboy",
            authorized=True,
        ),
        summary="Known-song profile from web evidence.",
        knowledge=knowledge,
    )

    assert reference.knowledge is not None
    assert reference.knowledge.identity.title == "Space Cowboy"
    assert reference.audio is None


def test_composition_brief_models_reference_transfer_policy_and_traits():
    source_profile = SongKnowledgeProfile.model_validate(load_fixture("space_cowboy.json"))
    brief = CompositionBrief(
        brief_id="brief_demo",
        user_request="Use the drums from Space Cowboy but make the harmony darker.",
        references_used=[source_profile.profile_id],
        transfer_policy={
            source_profile.profile_id: ["rhythmic_guidance", "groove"],
        },
        global_constraints={"genre": "acid jazz", "mood": "darker"},
        rhythmic_guidance={
            "groove_family": "four-on-the-floor funk",
            "confidence": "medium",
        },
        forbidden_traits=["do not copy the vocal melody"],
        uncertainty_notes=["Harmony evidence is incomplete; use original darker chords."],
    )

    assert brief.references_used == ["song_jamiroquai_space_cowboy"]
    assert "rhythmic_guidance" in brief.transfer_policy[source_profile.profile_id]
    assert brief.harmonic_guidance == {}


def test_instrument_trait_and_section_models_keep_evidence_scoped():
    claim = EvidenceClaim(
        claim_id="claim_drums",
        claim_type="instrumentation",
        value="Syncopated hi-hat and kick pattern",
        source_name="manual fixture",
        source_url="file://fixture",
        extraction_method="manual_fixture",
        confidence=0.7,
        section_name="verse",
    )
    section = SongSectionProfile(
        name="verse",
        order=1,
        instrument_claims=[claim],
    )
    trait = InstrumentTrait(
        instrument="drums",
        role="groove",
        traits={"pattern": "syncopated hi-hat", "density": "medium"},
        source_claim_ids=[claim.claim_id],
        confidence=0.7,
    )

    assert section.instrument_claims[0].section_name == "verse"
    assert trait.source_claim_ids == ["claim_drums"]
