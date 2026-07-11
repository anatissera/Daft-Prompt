from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from music_assistant.domain.audio_profile import (
    ArtistStyleProfile,
    CompositionBrief,
    EvidenceClaim,
    EvidenceConflict,
    InstrumentTab,
    InstrumentTrait,
    PlayablePart,
    ReferenceProfile,
    ReferenceSource,
    RepresentativeSong,
    SongKnowledgeProfile,
    SongSectionProfile,
    TabMeasureProfile,
    ToneProfile,
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


def test_song_profile_can_carry_playable_parts_and_tone_profiles():
    tab_claim = EvidenceClaim(
        claim_id="songsterr_guitar_intro",
        claim_type="tab",
        value="Intro guitar tab is available",
        source_name="Songsterr",
        source_url="https://songsterr.test/demo",
        extraction_method="source_connector",
        confidence=0.82,
        snippet="Songsterr track: Electric Guitar",
    )
    tab = InstrumentTab(
        instrument="electric guitar",
        instrument_family="guitar",
        track_name="Electric Guitar",
        tuning=["E", "A", "D", "G", "B", "E"],
        source_name="Songsterr",
        source_url="https://songsterr.test/demo",
        confidence=0.82,
        measures=[TabMeasureProfile(index=0, marker="intro")],
    )
    playable = PlayablePart(
        part_id="play_intro_guitar",
        kind="guitar_tab",
        instrument_family="guitar",
        title="Intro guitar tab",
        section_name="intro",
        source_name="Songsterr",
        source_url="https://songsterr.test/demo",
        evidence_claim_ids=[tab_claim.claim_id],
        tab=tab,
        confidence=0.82,
    )
    tone = ToneProfile(
        tone_id="tone_robot_guitar",
        instrument="electric guitar",
        family="guitar",
        description="Tight filtered rhythm guitar",
        patch_family="muted clean",
        source_claim_ids=[tab_claim.claim_id],
        confidence=0.61,
    )
    profile = SongKnowledgeProfile(
        profile_id="song_demo",
        identity={"title": "Demo Song", "artist": "Fixture Artist"},
        evidence_claims=[tab_claim],
        playable_parts=[playable],
        tone_profiles=[tone],
        source_names=["Songsterr"],
    )

    dumped = profile.model_dump(mode="json")

    assert dumped["playable_parts"][0]["kind"] == "guitar_tab"
    assert dumped["playable_parts"][0]["confidence_label"] == "high"
    assert dumped["tone_profiles"][0]["confidence_label"] == "medium"
    assert profile.source_names == ["Songsterr"]


def test_artist_style_profile_and_composition_brief_share_compact_traits():
    source_claim = EvidenceClaim(
        claim_id="style_sparse_verses",
        claim_type="style_profile",
        value="Sparse verses with punchy chorus contrast",
        source_name="style fixture",
        source_url="file://style-fixture",
        extraction_method="manual_fixture",
        confidence=0.68,
    )
    tone = ToneProfile(
        tone_id="tone_detuned_synth",
        instrument="synth",
        description="Compressed detuned synth lead",
        patch_family="detuned lead",
        confidence=0.66,
    )
    style = ArtistStyleProfile(
        profile_id="artist_fixture_band",
        artist_name="Fixture Band",
        representative_songs=[
            RepresentativeSong(
                title="Representative Song",
                artist="Fixture Band",
                profile_id="song_representative",
                reason="popular and tab-backed",
                source_claim_ids=[source_claim.claim_id],
                tab_available=True,
                confidence=0.74,
            )
        ],
        source_profile_ids=["song_representative"],
        genre_tags=["alt pop"],
        tempo_range_bpm=(92.0, 144.0),
        common_meters=["4/4"],
        common_progressions=["i - VI - III - VII"],
        typical_instruments=["drums", "bass", "piano", "synth"],
        drum_traits=["punchy chorus drums"],
        production_tone_traits=["dry verses", "wide chorus"],
        tone_profiles=[tone],
        source_claims=[source_claim],
        confidence=0.69,
    )
    playable = PlayablePart(
        part_id="drums_to_keep",
        kind="drum_tab",
        instrument_family="drums",
        title="Main drum groove",
        confidence=0.8,
    )
    brief = CompositionBrief(
        brief_id="brief_style",
        user_request="Compose like Fixture Band but keep this drum groove exactly.",
        references_used=["artist_fixture_band"],
        artist_style_profile_ids=[style.profile_id],
        artist_style_profiles=[style],
        playable_parts_to_preserve=[playable],
        preservation_requests=["keep drums exactly"],
        style_guidance={"artist_fixture_band": ["sparse verses", "big chorus contrast"]},
    )

    dumped = brief.model_dump(mode="json")

    assert dumped["artist_style_profiles"][0]["confidence_label"] == "medium"
    assert dumped["playable_parts_to_preserve"][0]["kind"] == "drum_tab"
    assert brief.preservation_requests == ["keep drums exactly"]
