from __future__ import annotations

from music_assistant.application.composition_brief import BuildCompositionBrief
from music_assistant.domain.audio_profile import (
    ReferenceInstrumentProfile,
    ReferenceTransferIntent,
    ReferenceTransferItem,
    SongIdentity,
    SongKnowledgeProfile,
)


def test_composition_brief_embeds_llm_intent_and_instrument_profile():
    knowledge = SongKnowledgeProfile(
        profile_id="song_fixture",
        identity=SongIdentity(title="Fixture Song"),
    )
    bass_profile = ReferenceInstrumentProfile(
        source_reference_id="ref_fixture",
        source_profile_id="song_fixture",
        instrument_family="bass",
        track_name="Fender Precision Bass",
        confidence=0.8,
    )
    intent = ReferenceTransferIntent(
        items=[
            ReferenceTransferItem(
                instrument_family="bass",
                reference_id="ref_fixture",
                transfer_mode="literal",
                fidelity=0.9,
            )
        ]
    )

    result = BuildCompositionBrief().execute(
        "usa el bajo igual",
        [knowledge],
        transfer_intent=intent,
        instrument_profiles={"ref_fixture": {"bass": bass_profile}},
    )

    assert result.brief is not None
    request = result.brief.instrument_requests["bass"]
    assert request["intent"]["transfer_mode"] == "literal"
    assert "reference_profile" not in request
    assert "timbre" in request
    assert "pattern" in request
    assert request["musical_memory_summary"] == ""
    assert request["literal_application"] is False
    assert "no note pack" in result.brief.uncertainty_notes[0].lower()
    assert result.brief.transfer_policy["song_fixture"] == ["instrument:bass"]


def test_literal_intent_without_profile_adds_uncertainty_note():
    knowledge = SongKnowledgeProfile(
        profile_id="song_fixture",
        identity=SongIdentity(title="Fixture Song"),
    )
    intent = ReferenceTransferIntent(
        items=[
            ReferenceTransferItem(
                instrument_family="piano",
                reference_id="ref_fixture",
                transfer_mode="literal",
                fidelity=0.9,
            )
        ]
    )

    result = BuildCompositionBrief().execute(
        "usa el mismo piano",
        [knowledge],
        transfer_intent=intent,
        instrument_profiles={"ref_fixture": {}},
    )

    assert result.brief is not None
    assert "piano" in result.brief.uncertainty_notes[0].lower()
