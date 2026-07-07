from __future__ import annotations

from music_assistant.application.reference_transfer_intent import BuildReferenceTransferIntent
from music_assistant.domain.audio_profile import (
    ReferenceInstrumentProfile,
    ReferenceTransferIntent,
    ReferenceTransferItem,
)


class FakeStructured:
    def __init__(self, output):
        self.output = output
        self.calls = []

    def invoke(self, messages):
        self.calls.append(messages)
        return self.output


class FakeModel:
    def __init__(self, output):
        self.structured = FakeStructured(output)

    def with_structured_output(self, schema):
        assert schema is ReferenceTransferIntent
        return self.structured


def _profile(instrument: str) -> ReferenceInstrumentProfile:
    return ReferenceInstrumentProfile(
        source_reference_id="ref_song",
        source_profile_id="song_fixture",
        instrument_family=instrument,
        track_name=f"{instrument} track",
        confidence=0.8,
    )


def test_llm_decides_similar_bass_intent_without_keyword_rules():
    output = ReferenceTransferIntent(
        items=[
            ReferenceTransferItem(
                instrument_family="bass",
                reference_id="ref_song",
                transfer_mode="similar",
                fidelity=0.65,
                constraints=["keep it funky"],
            )
        ]
    )
    model = FakeModel(output)

    result = BuildReferenceTransferIntent(chat_model=model).execute(
        "quiero un bajo como el de esta cancion",
        {"ref_song": {"bass": _profile("bass")}},
    )

    assert result.intent.items[0].instrument_family == "bass"
    assert result.intent.items[0].transfer_mode == "similar"
    prompt_text = str(model.structured.calls[0]).lower()
    assert "do not infer transfer mode from fixed keywords" in prompt_text


def test_prompt_explains_literal_requires_exact_note_pack_when_available():
    output = ReferenceTransferIntent(
        items=[
            ReferenceTransferItem(
                instrument_family="bass",
                reference_id="ref_song",
                transfer_mode="literal",
                fidelity=0.95,
            )
        ]
    )
    model = FakeModel(output)

    BuildReferenceTransferIntent(chat_model=model).execute(
        "usa el mismo bajo de esta cancion",
        {"ref_song": {"bass": _profile("bass")}},
    )

    prompt_text = str(model.structured.calls[0]).lower()
    assert "literal means the user wants the same instrument part" in prompt_text
    assert "only choose literal when a note pack or symbolic seed is available" in prompt_text


def test_prompt_limits_full_reference_intent_to_available_instruments():
    output = ReferenceTransferIntent(items=[])
    model = FakeModel(output)

    BuildReferenceTransferIntent(chat_model=model).execute(
        "hace toda la cancion lo mas igual posible",
        {"ref_song": {"bass": _profile("bass"), "drums": _profile("drums")}},
    )

    prompt_text = str(model.structured.calls[0]).lower()
    assert "for full-song recreation requests, create one item for every available instrument family" in prompt_text
    assert "do not introduce piano" in prompt_text
    assert "do not put operational warnings" in prompt_text


def test_llm_can_request_literal_or_timbre_only_transfer():
    output = ReferenceTransferIntent(
        items=[
            ReferenceTransferItem(
                instrument_family="guitar",
                reference_id="ref_song",
                transfer_mode="timbre_only",
                fidelity=0.4,
            ),
            ReferenceTransferItem(
                instrument_family="bass",
                reference_id="ref_song",
                transfer_mode="literal",
                fidelity=0.95,
            ),
        ]
    )

    result = BuildReferenceTransferIntent(chat_model=FakeModel(output)).execute(
        "quiero ese sonido de guitarra y el bajo igual",
        {"ref_song": {"bass": _profile("bass"), "guitar": _profile("guitar")}},
    )

    modes = {item.instrument_family: item.transfer_mode for item in result.intent.items}
    assert modes == {"guitar": "timbre_only", "bass": "literal"}


def test_missing_llm_returns_clarification_instead_of_guessing_complex_intent():
    result = BuildReferenceTransferIntent(chat_model=None).execute(
        "usa instrumentos de esta referencia",
        {"ref_song": {"drums": _profile("drums")}},
    )

    assert result.intent is None
    assert "need the chat model" in result.clarification.lower()
