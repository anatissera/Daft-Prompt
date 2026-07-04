from __future__ import annotations

from music_assistant.application.chat_music import ChatMusic, ChatRequest, ChatToolDecision
from music_assistant.application.composition_brief import BuildCompositionBrief
from music_assistant.domain.audio_profile import EvidenceClaim, ReferenceProfile, ReferenceSource, SongIdentity, SongKnowledgeProfile
from music_assistant.infrastructure.storage.in_memory_reference_store import InMemoryReferenceStore
from music_assistant.canned import canned_song


def claim(claim_id: str, claim_type: str, value: str, confidence: float = 0.7) -> EvidenceClaim:
    return EvidenceClaim(
        claim_id=claim_id,
        claim_type=claim_type,  # type: ignore[arg-type]
        value=value,
        normalized_value=value,
        source_name="Fixture",
        source_url="https://fixture.test",
        extraction_method="manual_fixture",
        confidence=confidence,
        snippet=value,
    )


def knowledge(profile_id: str, title: str, *, tempo: str = "112 BPM", harmony: str = "Am - F - C - G") -> SongKnowledgeProfile:
    return SongKnowledgeProfile(
        profile_id=profile_id,
        identity=SongIdentity(title=title),
        evidence_claims=[
            claim(f"{profile_id}_tempo", "tempo", tempo, 0.8),
            claim(f"{profile_id}_harmony", "chord_progression", harmony, 0.74),
            claim(f"{profile_id}_drums", "groove", f"{title} drum groove", 0.72),
            claim(f"{profile_id}_synth", "timbre", f"{title} bright synth", 0.65),
        ],
    )


def reference(reference_id: str, profile: SongKnowledgeProfile) -> ReferenceProfile:
    return ReferenceProfile(
        reference_id=reference_id,
        source=ReferenceSource(reference_id=reference_id, kind="metadata", label=profile.identity.title, uri="research://x", authorized=True),
        knowledge=profile,
    )


class FakeStructured:
    def __init__(self, decision):
        self.decision = decision

    def invoke(self, _messages):
        return self.decision


class FakeModel:
    def __init__(self, decision):
        self.structured = FakeStructured(decision)

    def with_structured_output(self, _schema):
        return self.structured


class RecordingComposer:
    def __init__(self):
        self.calls = []

    def compose(self, style):
        self.calls.append(style)
        return canned_song(str(style)), "canned"


def test_builder_mixes_compatible_multi_reference_dimensions():
    drums = knowledge("song_drums", "Drum Song")
    harmony = knowledge("song_harmony", "Harmony Song", harmony="Dm - G - Cmaj7")
    synths = knowledge("song_synths", "Synth Song")

    result = BuildCompositionBrief().execute(
        "use drums from Drum Song, harmony from Harmony Song, synths from Synth Song",
        [drums, harmony, synths],
    )

    assert result.brief is not None
    assert result.brief.transfer_policy["song_drums"] == ["rhythmic_guidance"]
    assert result.brief.transfer_policy["song_harmony"] == ["harmonic_guidance"]
    assert result.brief.transfer_policy["song_synths"] == ["timbre_traits"]


def test_builder_clarifies_when_requested_tempo_conflicts_between_references():
    one = knowledge("song_one", "One", tempo="100 BPM")
    two = knowledge("song_two", "Two", tempo="140 BPM")

    result = BuildCompositionBrief().execute("use the tempo from these songs", [one, two])

    assert result.brief is None
    assert "tempo" in result.clarification.lower()


def test_builder_does_not_transfer_missing_or_low_confidence_trait_silently():
    sparse = knowledge("song_sparse", "Sparse")
    sparse.evidence_claims = [claim("weak_drums", "groove", "unclear groove", 0.3)]

    result = BuildCompositionBrief().execute("use this song's drums", [sparse])

    assert result.brief is not None
    assert result.brief.uncertainty_notes
    assert "low confidence" in result.brief.uncertainty_notes[0].lower()


def test_chat_request_supports_multiple_reference_ids_for_reference_mixing():
    store = InMemoryReferenceStore()
    store.save(reference("ref_drums", knowledge("song_drums", "Drum Song")))
    store.save(reference("ref_harmony", knowledge("song_harmony", "Harmony Song", harmony="Dm - G - Cmaj7")))
    composer = RecordingComposer()
    chat = ChatMusic(
        compose_song=composer,
        answer_music_question=None,  # not used
        reference_store=store,
        chat_model=FakeModel(ChatToolDecision(action="compose_from_reference", composition_request="use drums from Drum Song and harmony from Harmony Song")),
    )

    response = chat.handle(
        ChatRequest(
            message="use drums from Drum Song and harmony from Harmony Song",
            reference_ids=["ref_drums", "ref_harmony"],
        )
    )

    assert response.intent == "compose_from_reference"
    assert response.compose is not None
    assert hasattr(composer.calls[0], "brief_id")
    assert composer.calls[0].transfer_policy["song_drums"] == ["rhythmic_guidance"]
    assert composer.calls[0].transfer_policy["song_harmony"] == ["harmonic_guidance"]
