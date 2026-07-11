from __future__ import annotations

from music_assistant.application.composition_brief import (
    BuildCompositionBrief,
    BriefBuildResult,
)
from music_assistant.domain.audio_profile import (
    AudioProfile,
    EvidenceClaim,
    EvidenceConflict,
    PlayablePart,
    MelodyProfile,
    SongIdentity,
    SongKnowledgeProfile,
    SongSectionProfile,
)


def claim(claim_id: str, claim_type: str, value: str, *, section: str | None = None, confidence: float = 0.7):
    return EvidenceClaim(
        claim_id=claim_id,
        claim_type=claim_type,  # type: ignore[arg-type]
        value=value,
        normalized_value=value,
        section_name=section,
        source_name="Fixture",
        source_url="https://fixture.test",
        extraction_method="manual_fixture",
        confidence=confidence,
        snippet=value,
    )


def profile(profile_id: str, title: str, *, with_drums: bool = True, harmony: str = "Am - F - C - G") -> SongKnowledgeProfile:
    drum = claim("drums", "groove", "four-on-the-floor funk drums", confidence=0.72)
    chords = claim("chords", "chord_progression", harmony, section="chorus", confidence=0.74)
    tempo = claim("tempo", "tempo", "112 BPM", confidence=0.8)
    claims = [tempo, chords]
    if with_drums:
        claims.append(drum)
    return SongKnowledgeProfile(
        profile_id=profile_id,
        identity=SongIdentity(title=title, artist="Fixture Artist"),
        evidence_claims=claims,
        sections=[SongSectionProfile(name="chorus", order=1, chord_claims=[chords])],
    )


def test_builds_scratch_brief_without_references():
    result = BuildCompositionBrief().execute("compose a dark cumbia loop", [])

    assert result.brief is not None
    assert result.clarification is None
    assert result.brief.references_used == []
    assert result.brief.global_constraints["mood"] == "dark"
    assert result.brief.global_constraints["genre"] == "cumbia"


def test_builds_single_reference_brief_for_drums_request():
    source = profile("song_space", "Space Cowboy")

    result = BuildCompositionBrief().execute("use this song's drums but make it darker", [source])

    assert result.brief is not None
    assert result.brief.references_used == ["song_space"]
    assert result.brief.transfer_policy["song_space"] == ["rhythmic_guidance"]
    assert "four-on-the-floor" in result.brief.rhythmic_guidance["song_space"][0]
    assert result.brief.global_constraints["mood"] == "dark"


def test_reference_brief_carries_fidelity_mode_instrument_salience_and_guardrails():
    source = profile("song_something", "Something")
    source.metadata["songsterr_tab_index"] = {
        "tracks": [
            {"instrument": "guitar", "name": "George Harrison guitar"},
            {"instrument": "bass", "name": "Paul McCartney bass"},
            {"instrument": "drums", "name": "Ringo drums"},
        ]
    }

    similar = BuildCompositionBrief().execute("compose a similar song", [source]).brief
    exact = BuildCompositionBrief().execute("make it exactly as close as possible", [source]).brief

    assert similar is not None and exact is not None
    assert similar.fidelity_mode == "similar"
    assert exact.fidelity_mode == "exact_or_as_close_as_possible"
    instrumentation = exact.reference_instrumentation["song_something"]
    assert instrumentation["families"] == ["bass", "drums", "guitar"]
    assert instrumentation["salience"]["guitar_led"] is True
    assert "guitar" in exact.style_guardrails["expected_families"]
    assert "creative_note" in exact.style_guardrails


def test_builds_multi_reference_brief_by_dimension():
    drums = profile("song_drums", "Drum Song")
    harmony = profile("song_harmony", "Harmony Song", harmony="Dm - G - Cmaj7")

    result = BuildCompositionBrief().execute(
        "use drums from Drum Song and harmony from Harmony Song",
        [drums, harmony],
    )

    assert result.brief is not None
    assert result.brief.transfer_policy["song_drums"] == ["rhythmic_guidance"]
    assert result.brief.transfer_policy["song_harmony"] == ["harmonic_guidance"]
    assert result.brief.harmonic_guidance["song_harmony"][0] == "Dm - G - Cmaj7"


def test_requested_melody_uses_compact_transcription_style_not_events():
    source = profile("song_melody", "Melody Song")
    source.audio = AudioProfile(
        duration_seconds=30.0,
        melody=MelodyProfile(note_count=18, pitch_low=60, pitch_high=72, contour="rising", confidence=0.4),
    )

    result = BuildCompositionBrief().execute("compose a new solo using this song's melodic contour", [source])

    assert result.brief is not None
    guidance = result.brief.melodic_guidance["song_melody"]
    assert guidance["contour"] == "rising"
    assert guidance["pitch_low"] == 60
    assert "copy events" in guidance["instruction"]
    assert "representative_events" not in guidance


def test_missing_requested_trait_returns_uncertainty_note():
    no_drums = profile("song_sparse", "Sparse Song", with_drums=False)

    result = BuildCompositionBrief().execute("use this song's drums", [no_drums])

    assert result.brief is not None
    assert "drum" in result.brief.uncertainty_notes[0].lower()


def test_exact_playable_part_request_is_preserved_in_brief():
    source = profile("song_drums", "Drum Song")
    source.playable_parts = [
        PlayablePart(
            part_id="songsterr_drums_1",
            kind="drum_tab",
            instrument_family="drums",
            title="Drum tab",
            source_name="Songsterr",
            source_url="https://songsterr.test/drum-song",
            confidence=0.82,
        )
    ]

    result = BuildCompositionBrief().execute(
        "compose a new song but keep this drum groove exactly",
        [source],
    )

    assert result.brief is not None
    assert result.brief.playable_parts_to_preserve[0].part_id == "songsterr_drums_1"
    assert result.brief.preservation_requests == ["keep drums exactly from Drum Song"]
    assert "preserve:drums" in result.brief.transfer_policy["song_drums"]


def test_exact_playable_part_request_without_evidence_adds_uncertainty():
    source = profile("song_sparse", "Sparse Song")

    result = BuildCompositionBrief().execute("keep this bass exactly", [source])

    assert result.brief is not None
    assert result.brief.playable_parts_to_preserve == []
    assert "no playable bass evidence" in result.brief.uncertainty_notes[0]


def test_conflicting_references_return_clarification_for_ambiguous_request():
    one = profile("song_one", "One", harmony="Am - F - C - G")
    two = profile("song_two", "Two", harmony="Dm - Bb - F - C")
    one.conflicts = [
        EvidenceConflict(
            conflict_id="harmony_conflict",
            claim_type="chord_progression",
            description="Conflicting harmony.",
            claims=[],
        )
    ]

    result = BuildCompositionBrief().execute("make it like these two songs", [one, two])

    assert result.brief is None
    assert result.clarification is not None
    assert "which traits" in result.clarification.lower()


def test_result_model_represents_clarification_without_brief():
    result = BriefBuildResult(clarification="Which reference should provide harmony?")

    assert result.brief is None
    assert "harmony" in result.clarification
