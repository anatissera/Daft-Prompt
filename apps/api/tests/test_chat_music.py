"""Chat-music intent router (Phase 5 of the chat-musical MVP)."""

from __future__ import annotations

from typing import Optional

import pytest

from music_assistant.application.answer_music_question import AnswerMusicQuestion
from music_assistant.application.chat_music import ChatMusic, ChatRequest
from music_assistant.application.compose_song import ComposeSong
from music_assistant.canned import canned_song
from music_assistant.domain.audio_profile import (
    AudioProfile,
    ChordEstimate,
    ExplanationAnswer,
    HarmonicProfile,
    KeyProfile,
    ResearchEvidence,
    ReferenceProfile,
    ReferenceSource,
    SectionProfile,
    StructuralSection,
    StructureProfile,
    ProgressionEstimate,
)
from music_assistant.domain.song_state import SongState
from music_assistant.infrastructure.storage.in_memory_reference_store import InMemoryReferenceStore


def _make_profile(reference_id: str = "ref_demo") -> ReferenceProfile:
    source = ReferenceSource(
        reference_id=reference_id,
        kind="upload",
        label="demo.wav",
        uri="local://demo.wav",
        authorized=True,
    )
    audio = AudioProfile(
        duration_seconds=90.0,
        tempo_bpm=118.0,
        tempo_confidence=0.8,
        key="C major",
        key_confidence=0.7,
        overall_confidence=0.85,
        chord_estimates=[
            ChordEstimate(start_seconds=0.0, end_seconds=12.0, chords=["Am", "F", "C", "G"], confidence=0.66),
        ],
        sections=[
            SectionProfile(name="chorus", start_seconds=24.0, end_seconds=48.0, energy=0.85, energy_confidence=0.8),
        ],
    )
    return ReferenceProfile(reference_id=reference_id, source=source, audio=audio)


class _RecordingComposer:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def compose(self, style: str) -> tuple[SongState, str]:
        self.calls.append(style)
        return canned_song(style), "canned"


class _CountingExplainer:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def answer(self, question: str, profile: ReferenceProfile) -> ExplanationAnswer:
        self.calls.append((question, profile.reference_id))
        return ExplanationAnswer(
            reference_id=profile.reference_id,
            answer=f"fake answer about {question}",
            evidence=["fake evidence"],
        )


def _make_chat(
    *,
    store: Optional[InMemoryReferenceStore] = None,
    composer: Optional[_RecordingComposer] = None,
    explainer: Optional[_CountingExplainer] = None,
) -> tuple[ChatMusic, _RecordingComposer, _CountingExplainer, InMemoryReferenceStore]:
    store = store or InMemoryReferenceStore()
    composer = composer or _RecordingComposer()
    explainer = explainer or _CountingExplainer()
    chat = ChatMusic(
        compose_song=composer,  # ducktyped: only .compose used
        answer_music_question=AnswerMusicQuestion(explainer),
        reference_store=store,
    )
    return chat, composer, explainer, store


def test_compose_intent_when_no_reference_and_no_question_topic():
    chat, composer, explainer, _ = _make_chat()

    response = chat.handle(ChatRequest(message="compose a sad piano sketch"))

    assert response.intent == "compose"
    assert response.compose is not None
    assert response.compose.source == "canned"
    assert composer.calls == ["compose a sad piano sketch"]
    assert explainer.calls == []


def test_answer_reference_intent_when_question_matches_profile_topic():
    profile = _make_profile()
    chat, composer, explainer, store = _make_chat()
    store.save(profile)

    response = chat.handle(
        ChatRequest(message="what chords does the chorus play?", reference_id=profile.reference_id),
    )

    assert response.intent == "answer_reference"
    assert response.answer is not None
    assert response.answer.reference_id == profile.reference_id
    assert composer.calls == []
    assert explainer.calls == [("what chords does the chorus play?", profile.reference_id)]


def test_compose_from_reference_intent_when_user_asks_to_compose_with_reference():
    profile = _make_profile()
    chat, composer, _, store = _make_chat()
    store.save(profile)

    response = chat.handle(
        ChatRequest(message="compose something like this", reference_id=profile.reference_id),
    )

    assert response.intent == "compose_from_reference"
    assert response.compose is not None
    assert response.reference_id == profile.reference_id
    assert composer.calls, "compose_song.compose should have been invoked"
    style = composer.calls[0]
    assert "inspired by reference demo.wav" in style
    assert "118 BPM" in style


def test_clarify_intent_when_reference_present_but_message_is_ambiguous():
    profile = _make_profile()
    chat, composer, explainer, store = _make_chat()
    store.save(profile)

    response = chat.handle(ChatRequest(message="hello there", reference_id=profile.reference_id))

    assert response.intent == "clarify"
    assert response.clarification is not None
    assert composer.calls == []
    assert explainer.calls == []


def test_missing_reference_id_falls_back_to_compose():
    chat, composer, _, _ = _make_chat()

    response = chat.handle(ChatRequest(message="compose a short pop song", reference_id="ref_missing"))

    assert response.intent == "compose"
    assert composer.calls == ["compose a short pop song"]


def test_compose_from_reference_uses_message_as_prefix():
    profile = _make_profile("ref_pop")
    chat, composer, _, store = _make_chat()
    store.save(profile)

    response = chat.handle(
        ChatRequest(
            message="generate a chill chorus inspired by this song",
            reference_id="ref_pop",
        ),
    )

    assert response.intent == "compose_from_reference"
    style = composer.calls[0]
    assert style.startswith("generate a chill chorus inspired by this song")
    assert "demo.wav" in style


def test_show_chords_on_piano_returns_playable_chord_notes_from_sections():
    profile = _make_profile()
    assert profile.audio is not None
    profile.audio.structure = StructureProfile(
        sections=[
            StructuralSection(
                label="intro",
                start_bar=0,
                end_bar=4,
                start_seconds=0.0,
                end_seconds=12.0,
                confidence=0.82,
                main_progression=["Eb", "Bbm", "Fm"],
            )
        ],
        confidence=0.82,
    )
    chat, _, _, store = _make_chat()
    store.save(profile)

    response = chat.handle(
        ChatRequest(message="Can you show them to me in the piano?", reference_id=profile.reference_id),
    )

    assert response.intent == "playable_chords"
    assert response.playable_chords is not None
    assert response.playable_chords.instrument == "piano"
    section = response.playable_chords.sections[0]
    assert section.name == "intro"
    assert [chord.chord for chord in section.chords] == ["Eb", "Bbm", "Fm"]
    assert section.chords[0].midi_notes == [63, 67, 70]
    assert section.chords[1].notes == ["Bb", "Db", "F"]


def test_playable_chords_prefers_section_progressions_over_generic_harmony():
    profile = _make_profile()
    assert profile.audio is not None
    profile.audio.harmony = HarmonicProfile(
        key=KeyProfile(),
        progressions=[
            ProgressionEstimate(
                start_bar=0,
                end_bar=4,
                chords=["C", "G"],
                confidence=0.5,
            )
        ],
    )
    profile.audio.structure = StructureProfile(
        sections=[
            StructuralSection(
                label="chorus",
                start_bar=8,
                end_bar=12,
                start_seconds=24.0,
                end_seconds=36.0,
                confidence=0.9,
                main_progression=["Eb", "Bbm", "Fm"],
            )
        ],
        confidence=0.9,
    )
    chat, _, _, store = _make_chat()
    store.save(profile)

    response = chat.handle(
        ChatRequest(message="show the chords on piano", reference_id=profile.reference_id),
    )

    assert response.playable_chords is not None
    assert response.playable_chords.sections[0].name == "chorus"
    assert [chord.chord for chord in response.playable_chords.sections[0].chords] == ["Eb", "Bbm", "Fm"]


def test_show_chords_on_guitar_uses_chord_names_not_source_excerpt():
    source = ReferenceSource(
        reference_id="ref_clocks",
        kind="metadata",
        label="Clocks by Coldplay",
        uri="research://Clocks by Coldplay",
        authorized=True,
    )
    profile = ReferenceProfile(
        reference_id="ref_clocks",
        source=source,
        audio=AudioProfile(duration_seconds=0.0, overall_confidence=0.6),
        research_evidence=[
            ResearchEvidence(
                url="https://example.test/clocks",
                site="Example Tabs",
                claim_type="chord_progression",
                value="Eb Bbm Fm",
                confidence=0.64,
                snippet="intro: Eb Bbm Fm",
            )
        ],
    )
    chat, composer, _, store = _make_chat()
    store.save(profile)

    response = chat.handle(
        ChatRequest(message="Can you show them to me in the guitar?", reference_id=profile.reference_id),
    )

    assert response.intent == "playable_chords"
    assert response.playable_chords is not None
    assert response.playable_chords.instrument == "guitar"
    assert [chord.chord for chord in response.playable_chords.sections[0].chords] == ["Eb", "Bbm", "Fm"]
    assert response.playable_chords.sections[0].chords[0].midi_notes == []
    assert composer.calls == []
