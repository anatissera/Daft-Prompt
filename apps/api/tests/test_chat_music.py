"""Chat-music intent router (Phase 5 of the chat-musical MVP)."""

from __future__ import annotations

from typing import Optional

import pytest

from music_assistant.application.answer_music_question import AnswerMusicQuestion
from music_assistant.application.artist_style_profile import ArtistStyleProfileResult
from music_assistant.application.chat_agent import ChatAgentResult
from music_assistant.application.chat_music import ChatMusic, ChatRequest
from music_assistant.application.compose_song import ComposeConfigurationError, ComposeSong
from music_assistant.application.music_tool_models import TabExcerptEvent, TabExcerptMeasure, TabExcerptToolOutput
from music_assistant.canned import canned_song
from music_assistant.domain.audio_profile import (
    ArtistStyleProfile,
    AudioProfile,
    ChordEstimate,
    ExplanationAnswer,
    MelodyEvent,
    MelodyProfile,
    ReferenceProfile,
    ReferenceSource,
    SectionProfile,
)
from music_assistant.domain.song_state import Header, Note, Part, RosterItem, SongState
from music_assistant.infrastructure.storage.in_memory_reference_store import InMemoryReferenceStore
from music_assistant.infrastructure.storage.in_memory_songsterr_tab_store import InMemorySongsterrTabStore
from music_assistant.infrastructure.web_research.songsterr_tabs import InstrumentTabTrack, SongsterrTabBundle, TabEvent, TabMeasure


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
        self.calls: list[object] = []
        self.revision_calls: list[tuple[str, str]] = []

    def compose(self, style) -> tuple[SongState, str]:
        self.calls.append(style)
        return canned_song(getattr(style, "user_request", style)), "canned"

    def revise_instrument(self, song: SongState, instruction: str, instrument_id: str) -> tuple[SongState, str]:
        self.revision_calls.append((instruction, instrument_id))
        part = song.parts[instrument_id].model_copy(
            update={
                "notes": [Note(bar=0, start_beat=0.0, pitch=67, dur=0.5)],
                "notes_summary": "revised to be less busy",
            }
        )
        return song.model_copy(update={"parts": {**song.parts, instrument_id: part}}), "director"


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
    chat_model=None,
    song_researcher=None,
    artist_style_profile_builder=None,
    enable_web_research: bool = True,
    songsterr_tab_store=None,
) -> tuple[ChatMusic, _RecordingComposer, _CountingExplainer, InMemoryReferenceStore]:
    store = store or InMemoryReferenceStore()
    composer = composer or _RecordingComposer()
    explainer = explainer or _CountingExplainer()
    chat = ChatMusic(
        compose_song=composer,  # ducktyped: only .compose used
        answer_music_question=AnswerMusicQuestion(explainer),
        reference_store=store,
        chat_model=chat_model,
        song_researcher=song_researcher,
        songsterr_tab_store=songsterr_tab_store,
        artist_style_profile_builder=artist_style_profile_builder,
        enable_web_research=enable_web_research,
    )
    return chat, composer, explainer, store


class _FailingChatModel:
    def with_structured_output(self, _schema):
        raise RuntimeError("chat model should not be used for this request")


class _ComposerUnavailable:
    def compose(self, _style: str):
        raise ComposeConfigurationError()


class _ArtistStyleBuilder:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self.profile = ArtistStyleProfile(
            profile_id="artist_fixture_band",
            artist_name="Fixture Band",
            genre_tags=["alt pop"],
            common_progressions=["i - VI - III - VII"],
            typical_instruments=["drums", "bass", "piano"],
            confidence=0.7,
        )

    def execute(self, request):
        self.calls.append(str(request))
        return ArtistStyleProfileResult(profile=self.profile)


def test_compose_intent_when_no_reference_and_no_question_topic():
    chat, composer, explainer, _ = _make_chat()

    response = chat.handle(ChatRequest(message="compose a sad piano sketch"))

    assert response.intent == "compose"
    assert response.compose is not None
    assert response.compose.source == "canned"
    assert composer.calls == ["compose a sad piano sketch"]
    assert explainer.calls == []


def test_artist_style_profile_request_returns_profile_context():
    builder = _ArtistStyleBuilder()
    chat, composer, _, _ = _make_chat(artist_style_profile_builder=builder)

    response = chat.handle(ChatRequest(message="style profile for Fixture Band"))

    assert response.intent == "artist_style"
    assert response.artist_style_profiles[0].artist_name == "Fixture Band"
    assert response.compose is None
    assert composer.calls == []


def test_artist_similarity_composition_builds_profile_and_passes_brief():
    builder = _ArtistStyleBuilder()
    chat, composer, _, _ = _make_chat(artist_style_profile_builder=builder)

    response = chat.handle(ChatRequest(message="compose something similar to Fixture Band with a funk bassline"))

    assert response.intent == "compose"
    assert response.compose is not None
    assert response.artist_style_profiles[0].profile_id == "artist_fixture_band"
    assert builder.calls == ["Fixture Band"]
    brief = composer.calls[0]
    assert getattr(brief, "artist_style_profile_ids") == ["artist_fixture_band"]


def test_artist_style_followup_reuses_profile_from_chat_context():
    builder = _ArtistStyleBuilder()
    chat, composer, _, _ = _make_chat()

    response = chat.handle(
        ChatRequest(
            message="compose more like them, but slower",
            artist_style_profiles=[builder.profile],
        )
    )

    assert response.intent == "compose"
    assert response.artist_style_profiles[0].artist_name == "Fixture Band"
    brief = composer.calls[0]
    assert getattr(brief, "artist_style_profile_ids") == ["artist_fixture_band"]


def test_no_provider_getting_started_question_returns_useful_local_guidance():
    chat, composer, _, _ = _make_chat(chat_model=None)

    response = chat.handle(ChatRequest(message="What can you help me with?"))

    assert response.intent == "clarify"
    assert "compose" in response.reply.lower()
    assert composer.calls == []


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
    assert response.chord_chart[0].chords == ["Am", "F", "C", "G"]


def test_riff_question_returns_native_melody_preview_when_transcription_exists():
    chat, _, _, store = _make_chat()
    profile = _make_profile()
    profile = profile.model_copy(update={
        "audio": profile.audio.model_copy(update={
            "melody": MelodyProfile(
                note_count=2,
                pitch_low=60,
                pitch_high=64,
                contour="rising",
                representative_events=[
                    MelodyEvent(bar=0, start_beat=0.0, duration_beats=1.0, pitch=60),
                    MelodyEvent(bar=0, start_beat=1.0, duration_beats=1.0, pitch=64),
                ],
                confidence=0.4,
            )
        })
    })
    store.save(profile)

    response = chat.handle(ChatRequest(message="How do I play this riff?", reference_id=profile.reference_id))

    assert response.intent == "answer_reference"
    assert response.melody_preview is not None
    assert response.melody_preview.representative_events[1].pitch == 64


def test_tab_tool_output_is_exposed_as_a_native_chat_excerpt():
    profile = _make_profile()
    chat, _, _, store = _make_chat()
    store.save(profile)
    output = TabExcerptToolOutput(
        reference_id=profile.reference_id,
        answer="Bass excerpt from Songsterr.",
        summary="Bass excerpt from Songsterr track Bass.",
        instrument="bass",
        track_name="Bass",
        tuning=["E1", "A1", "D2", "G2"],
        measures=[
            TabExcerptMeasure(
                index=0,
                marker="Verse",
                note_events=1,
                events=[TabExcerptEvent(beat_index=0.0, string=3, fret=5)],
            )
        ],
    )

    response = chat._response_from_agent_result(
        ChatAgentResult(intent="answer_reference", reply=output.answer, reference_id=profile.reference_id, tool_output=output)
    )

    assert response.tab_excerpt is not None
    assert response.tab_excerpt.track_name == "Bass"
    assert response.tab_excerpt.measures[0].events[0].fret == 5


def test_reference_tab_followup_invokes_tab_tool_and_returns_visible_content():
    profile = _make_profile("ref_tab")
    store = InMemoryReferenceStore()
    store.save(profile)
    tabs = InMemorySongsterrTabStore()
    tabs.save("ref_tab", SongsterrTabBundle(
        source_url="https://songsterr.test/tab",
        song_id=1,
        revision_id=2,
        image="fixture",
        title="Fixture Song",
        artist="Fixture Artist",
        tracks=[InstrumentTabTrack(
            part_id=4,
            name="Electric Guitar",
            instrument="Guitar",
            instrument_family="guitar",
            is_guitar=True,
            tuning=["E4", "B3", "G3", "D3", "A2", "E2"],
            source_url="https://songsterr.test/tab",
            measures=[TabMeasure(index=0, marker="Intro", events=[
                TabEvent(measure_index=0, beat_index=0, duration="1/4", string=2, fret=3, pitch=62),
            ])],
            note_count=1,
            beat_count=1,
        )],
    ))
    chat, _, _, _ = _make_chat(store=store, songsterr_tab_store=tabs, chat_model=_FailingChatModel())

    response = chat.handle(ChatRequest(message="Show me the guitar tab", reference_id="ref_tab"))

    assert response.tab_excerpt is not None
    assert response.tab_excerpt.error is None
    assert response.tab_excerpt.measures[0].events[0].fret == 3
    assert response.tab_excerpt.measures[0].note_events == 1


def test_generated_song_tab_is_derived_from_current_song_without_regeneration():
    chat, composer, _, _ = _make_chat()

    response = chat.handle(ChatRequest(message="Show the guitar tab", current_song=_generated_song()))

    assert response.tab_excerpt is not None
    assert response.tab_excerpt.error is None
    assert response.tab_excerpt.track_name == "electric_guitar"
    assert response.tab_excerpt.measures[0].events[0].pitch == 64
    assert response.tab_excerpt.measures[0].events[0].fret == 0
    assert composer.calls == []
    assert composer.revision_calls == []


def test_generated_song_bass_tab_uses_bass_tuning_positions():
    chat, composer, _, _ = _make_chat()

    response = chat.handle(ChatRequest(message="Show the bass tab", current_song=_generated_song()))

    assert response.tab_excerpt is not None
    assert response.tab_excerpt.error is None
    assert response.tab_excerpt.instrument == "bass"
    assert response.tab_excerpt.tuning == ["G2", "D2", "A1", "E1"]
    assert response.tab_excerpt.measures[0].events[0].string == 2
    assert response.tab_excerpt.measures[0].events[0].fret == 2
    assert composer.calls == []


def test_generated_song_drum_tab_uses_gm_drum_hits():
    chat, composer, _, _ = _make_chat()

    response = chat.handle(ChatRequest(message="Show the drum tab", current_song=_generated_song_with_drums_and_keys()))

    assert response.tab_excerpt is not None
    assert response.tab_excerpt.error is None
    assert response.tab_excerpt.instrument == "drums"
    assert response.tab_excerpt.measures[0].events[0].pitch == 38
    assert response.tab_excerpt.measures[0].events[0].fret == 38
    assert composer.calls == []


def test_generated_song_piano_keys_preserve_midi_pitches():
    chat, composer, _, _ = _make_chat()

    response = chat.handle(ChatRequest(message="Show the piano keys", current_song=_generated_song_with_drums_and_keys()))

    assert response.tab_excerpt is not None
    assert response.tab_excerpt.error is None
    assert response.tab_excerpt.instrument == "piano"
    assert response.tab_excerpt.measures[0].events[0].pitch == 60
    assert response.tab_excerpt.measures[0].events[0].string is None
    assert response.tab_excerpt.measures[0].events[0].fret is None
    assert composer.calls == []


def test_tab_failure_returns_renderable_user_facing_attachment():
    profile = _make_profile("ref_no_tabs")
    chat, _, _, store = _make_chat(songsterr_tab_store=InMemorySongsterrTabStore())
    store.save(profile)

    response = chat.handle(ChatRequest(message="Show me guitar tab", reference_id="ref_no_tabs"))

    assert response.tab_excerpt is not None
    assert response.tab_excerpt.error == "songsterr_bundle_missing"
    assert "do not have loaded" in response.reply
    assert response.error == {"code": "songsterr_bundle_missing", "message": response.reply}


def test_reference_question_uses_local_analysis_before_llm_router():
    profile = _make_profile()
    chat, composer, explainer, store = _make_chat(chat_model=_FailingChatModel())
    store.save(profile)

    response = chat.handle(
        ChatRequest(message="what key is this in?", reference_id=profile.reference_id),
    )

    assert response.intent == "answer_reference"
    assert response.answer is not None
    assert response.answer.reference_id == profile.reference_id
    assert composer.calls == []
    assert explainer.calls == [("what key is this in?", profile.reference_id)]


def test_reference_chord_question_uses_local_analysis_before_llm_router():
    profile = _make_profile()
    chat, composer, explainer, store = _make_chat(chat_model=_FailingChatModel())
    store.save(profile)

    response = chat.handle(
        ChatRequest(message="what chords are probably here?", reference_id=profile.reference_id),
    )

    assert response.intent == "answer_reference"
    assert response.answer is not None
    assert response.answer.reference_id == profile.reference_id
    assert composer.calls == []
    assert explainer.calls == [("what chords are probably here?", profile.reference_id)]


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


# ---- keyless routing fixes: research intent + deep-listening vocabulary --------


class _FakeResearcher:
    def __init__(self) -> None:
        self.queries: list[str] = []

    def research(self, query: str) -> ReferenceProfile:
        self.queries.append(query)
        profile = _make_profile("ref_researched")
        return profile.model_copy(update={"summary": "Research ready: Every Breath You Take."})


def test_research_phrase_triggers_web_research_without_an_llm():
    store = InMemoryReferenceStore()
    researcher = _FakeResearcher()
    chat = ChatMusic(
        compose_song=_RecordingComposer(),
        answer_music_question=AnswerMusicQuestion(_CountingExplainer()),
        reference_store=store,
        song_researcher=researcher,
        enable_web_research=True,
    )

    response = chat.handle(ChatRequest(message="Research Every Breath You Take by The Police"))

    assert response.intent == "answer_reference"
    assert response.reference_id == "ref_researched"
    assert "Research ready" in response.reply
    assert researcher.queries == ["Every Breath You Take by The Police"]  # verb stripped
    assert store.get("ref_researched") is not None


def test_research_followup_reuses_stored_profile_without_llm_rediscovery():
    store = InMemoryReferenceStore()
    researcher = _FakeResearcher()
    explainer = _CountingExplainer()
    chat = ChatMusic(
        compose_song=_RecordingComposer(),
        answer_music_question=AnswerMusicQuestion(explainer),
        reference_store=store,
        chat_model=_FailingChatModel(),
        song_researcher=researcher,
        enable_web_research=True,
    )
    researched = chat.handle(ChatRequest(message="Research Every Breath You Take by The Police"))

    followup = chat.handle(ChatRequest(message="What evidence did you find?", reference_id=researched.reference_id))

    assert followup.intent == "answer_reference"
    assert followup.reference_id == "ref_researched"
    assert followup.answer is not None
    assert followup.answer.evidence == ["fake evidence"]
    assert explainer.calls == [("What evidence did you find?", "ref_researched")]


def test_look_up_and_analyze_routes_to_research_even_with_a_reference_loaded():
    store = InMemoryReferenceStore()
    profile = _make_profile()
    store.save(profile)
    researcher = _FakeResearcher()
    chat = ChatMusic(
        compose_song=_RecordingComposer(),
        answer_music_question=AnswerMusicQuestion(_CountingExplainer()),
        reference_store=store,
        song_researcher=researcher,
        enable_web_research=True,
    )

    response = chat.handle(
        ChatRequest(
            message="Look up on the internet and analyze Every breath you take by The Police",
            reference_id=profile.reference_id,
        )
    )

    assert response.intent == "answer_reference"
    assert researcher.queries and "Every breath you take" in researcher.queries[0]


def test_research_without_configured_researcher_explains_instead_of_generic_clarify():
    chat, _, _, _ = _make_chat(enable_web_research=True)

    response = chat.handle(ChatRequest(message="Research Get Lucky by Daft Punk"))

    assert response.intent == "clarify"
    assert "not configured" in response.reply


def test_research_is_disabled_in_explicit_offline_mode_and_does_not_call_researcher():
    researcher = _FakeResearcher()
    chat, _, _, store = _make_chat(song_researcher=researcher, enable_web_research=False)

    response = chat.handle(ChatRequest(message="Research Get Lucky by Daft Punk"))

    assert response.intent == "clarify"
    assert "ENABLE_WEB_RESEARCH=true" in response.reply
    assert researcher.queries == []
    assert store.get("ref_researched") is None


def test_research_is_enabled_by_default_for_named_song_requests():
    researcher = _FakeResearcher()
    chat, _, _, store = _make_chat(song_researcher=researcher)

    response = chat.handle(ChatRequest(message="Research Get Lucky by Daft Punk"))

    assert response.intent == "answer_reference"
    assert researcher.queries == ["Get Lucky by Daft Punk"]
    assert store.get("ref_researched") is not None


def test_explicit_web_search_uses_research_without_llm_when_enabled():
    researcher = _FakeResearcher()
    chat, _, _, store = _make_chat(
        chat_model=_FailingChatModel(),
        song_researcher=researcher,
        enable_web_research=True,
    )

    response = chat.handle(ChatRequest(message="Search in the web for Around the World by Daft Punk"))

    assert response.intent == "answer_reference"
    assert response.reference_id == "ref_researched"
    assert researcher.queries == ["Around the World by Daft Punk"]
    assert store.get("ref_researched") is not None


def test_ambiguous_named_song_analysis_without_llm_points_to_public_evidence():
    chat, _, _, _ = _make_chat()

    response = chat.handle(ChatRequest(message="Analyze Around the World by Daft Punk"))

    assert response.intent == "clarify"
    assert "evidencia pública" in response.reply
    assert "Songsterr" in response.reply


def test_compose_configuration_error_returns_clear_chat_error():
    chat, _, _, _ = _make_chat(composer=_ComposerUnavailable())

    response = chat.handle(ChatRequest(message="compose a slow blues"))

    assert response.intent == "clarify"
    assert response.error is not None
    assert response.error["code"] == "llm_not_configured"
    assert "I could not compose" in response.reply
    assert "LLM" in response.reply


def test_spanish_compose_error_stays_in_spanish():
    chat, _, _, _ = _make_chat(composer=_ComposerUnavailable())

    response = chat.handle(ChatRequest(message="Componé un blues lento"))

    assert response.intent == "clarify"
    assert "No pude componer" in response.reply


def test_spanish_disabled_research_stays_in_spanish():
    chat, _, _, _ = _make_chat(song_researcher=_FakeResearcher(), enable_web_research=False)

    response = chat.handle(ChatRequest(message="Buscá Get Lucky de Daft Punk"))

    assert response.intent == "clarify"
    assert "búsqueda web está desactivada" in response.reply
    assert "ENABLE_WEB_RESEARCH=true" in response.reply


def _generated_song() -> SongState:
    header = Header(genre="rock", key="E minor", tempo_bpm=128, num_bars=4)
    guitar = RosterItem(id="guitar", instrument="electric_guitar", midi_range=(52, 88), role="riff")
    bass = RosterItem(id="bass", instrument="electric_bass", midi_range=(28, 55), role="low end")
    return SongState(
        request="compose rock",
        header=header,
        roster=[guitar, bass],
        parts={
            "guitar": Part(
                instrument_id="guitar",
                notes=[Note(bar=0, start_beat=0.0, pitch=64, dur=0.25)],
                notes_summary="busy guitar",
            ),
            "bass": Part(
                instrument_id="bass",
                notes=[Note(bar=0, start_beat=0.0, pitch=40, dur=1.0)],
                notes_summary="steady bass",
            ),
        },
    )


def _generated_song_with_drums_and_keys() -> SongState:
    song = _generated_song()
    drums = RosterItem(id="drums", instrument="drum_kit", midi_range=(35, 81), role="backbeat", is_drum=True)
    piano = RosterItem(id="piano", instrument="acoustic_piano", midi_range=(21, 108), role="keys")
    return song.model_copy(
        update={
            "roster": [*song.roster, drums, piano],
            "parts": {
                **song.parts,
                "drums": Part(
                    instrument_id="drums",
                    notes=[Note(bar=0, start_beat=1.0, pitch=38, dur=0.25)],
                    notes_summary="snare backbeat",
                ),
                "piano": Part(
                    instrument_id="piano",
                    notes=[Note(bar=0, start_beat=0.0, pitch=60, dur=1.0)],
                    notes_summary="middle C",
                ),
            },
        }
    )


def _two_guitar_song() -> SongState:
    header = Header(genre="grunge rock", key="F minor", tempo_bpm=117, num_bars=4)
    drums = RosterItem(id="drums", instrument="drum_kit", role="rhythm foundation", is_drum=True)
    bass = RosterItem(id="bass", instrument="electric_bass", midi_range=(28, 55), role="bass line")
    rhythm = RosterItem(
        id="rhythm_guitar",
        instrument="electric_guitar_clean",
        midi_range=(40, 84),
        role="harmonic rhythm",
    )
    lead = RosterItem(
        id="lead_guitar",
        instrument="electric_guitar_overdriven",
        midi_range=(52, 88),
        role="melodic lead",
        playing_style="Hard rock tone with short hooks.",
    )
    return SongState(
        request="compose grunge",
        header=header,
        roster=[drums, bass, rhythm, lead],
        parts={
            "drums": Part(instrument_id="drums", notes=[Note(bar=0, start_beat=0.0, pitch=36, dur=0.25)], notes_summary="backbeat"),
            "bass": Part(instrument_id="bass", notes=[Note(bar=0, start_beat=0.0, pitch=41, dur=1.0)], notes_summary="steady bass"),
            "rhythm_guitar": Part(instrument_id="rhythm_guitar", notes=[Note(bar=0, start_beat=0.0, pitch=53, dur=1.0)], notes_summary="clean chords"),
            "lead_guitar": Part(instrument_id="lead_guitar", notes=[Note(bar=0, start_beat=0.0, pitch=65, dur=0.5)], notes_summary="overdriven hook"),
        },
    )


def test_current_song_edit_routes_to_targeted_instrument_revision():
    composer = _RecordingComposer()
    chat, _, _, _ = _make_chat(composer=composer)

    response = chat.handle(
        ChatRequest(
            message="Make the guitar less busy and regenerate only that part.",
            current_song=_generated_song(),
        )
    )

    assert response.intent == "compose"
    assert response.compose is not None
    assert "Updated the electric_guitar part" in response.reply
    assert composer.calls == []
    assert composer.revision_calls == [("Make the guitar less busy and regenerate only that part.", "guitar")]
    assert response.compose.song.parts["guitar"].notes_summary == "revised to be less busy"
    assert response.compose.song.parts["bass"].notes_summary == "steady bass"


def test_current_song_edit_clarifies_when_target_instrument_is_missing():
    chat, composer, _, _ = _make_chat()

    response = chat.handle(
        ChatRequest(
            message="Regenerate the saxophone part.",
            current_song=_generated_song(),
        )
    )

    assert response.intent == "clarify"
    assert "which generated instrument" in response.reply.lower()
    assert composer.calls == []
    assert composer.revision_calls == []


def test_current_song_edit_maps_hard_rock_guitar_to_overdriven_guitar():
    composer = _RecordingComposer()
    chat, _, _, _ = _make_chat(composer=composer)

    response = chat.handle(
        ChatRequest(
            message="I do not like the hard rock guitar. Make it less busy.",
            current_song=_two_guitar_song(),
        )
    )

    assert response.intent == "compose"
    assert response.compose is not None
    assert "Updated the electric_guitar_overdriven part" in response.reply
    assert composer.revision_calls == [
        ("I do not like the hard rock guitar. Make it less busy.", "lead_guitar")
    ]


def test_current_song_edit_ambiguous_guitar_still_asks_one_clarification():
    chat, composer, _, _ = _make_chat()

    response = chat.handle(
        ChatRequest(
            message="Make the guitar less busy.",
            current_song=_two_guitar_song(),
        )
    )

    assert response.intent == "clarify"
    assert "electric_guitar_clean" in response.reply
    assert "electric_guitar_overdriven" in response.reply
    assert composer.revision_calls == []


def test_timbre_edit_changes_only_target_roster_identity_and_preserves_all_notes():
    chat, composer, _, _ = _make_chat()
    original = _generated_song()

    response = chat.handle(ChatRequest(message="Make the guitar sound clean.", current_song=original))

    assert response.compose is not None
    revised = response.compose.song
    assert revised.header == original.header
    assert revised.parts == original.parts
    assert revised.roster[1] == original.roster[1]
    assert revised.roster[0].instrument == "electric_guitar_clean"
    assert revised.roster[0].midi_program == 27
    assert composer.revision_calls == []


def test_unspecified_timbre_edit_asks_for_the_desired_sound_without_mutating_song():
    chat, composer, _, _ = _make_chat()

    response = chat.handle(ChatRequest(message="Change the guitar sound.", current_song=_generated_song()))

    assert response.intent == "clarify"
    assert "What sound" in response.reply
    assert composer.revision_calls == []


def test_repeated_edits_accumulate_on_current_song_without_changing_unrequested_material():
    composer = _RecordingComposer()
    chat, _, _, _ = _make_chat(composer=composer)
    original = _generated_song()

    timbre_response = chat.handle(
        ChatRequest(message="Make the guitar sound distorted.", current_song=original)
    )
    assert timbre_response.compose is not None
    after_timbre = timbre_response.compose.song
    notes_before_revision = after_timbre.parts["guitar"].notes
    bass_before_revision = after_timbre.parts["bass"]

    note_response = chat.handle(
        ChatRequest(message="Make the guitar less busy.", current_song=after_timbre)
    )

    assert note_response.compose is not None
    final = note_response.compose.song
    assert final.header == original.header
    assert final.request == original.request
    assert final.roster == after_timbre.roster
    assert final.roster[0].midi_program == 30
    assert final.parts["bass"] == bass_before_revision
    assert final.parts["guitar"].notes != notes_before_revision


def test_piano_chord_edit_changes_only_target_part_notes():
    chat, composer, _, _ = _make_chat()
    original = _generated_song_with_drums_and_keys()

    response = chat.handle(ChatRequest(message="Change the piano chord to Am.", current_song=original))

    assert response.intent == "compose"
    assert response.compose is not None
    revised = response.compose.song
    assert revised.header == original.header
    assert revised.roster == original.roster
    assert revised.parts["guitar"] == original.parts["guitar"]
    assert revised.parts["bass"] == original.parts["bass"]
    assert revised.parts["drums"] == original.parts["drums"]
    assert [note.pitch for note in revised.parts["piano"].notes] == [57, 60, 64]
    assert revised.parts["piano"].notes_summary == "Edited to Am chord tones."
    assert composer.calls == []
    assert composer.revision_calls == []


def test_piano_chord_edit_without_chord_asks_for_target_chord():
    chat, composer, _, _ = _make_chat()

    response = chat.handle(ChatRequest(message="Change the piano chord.", current_song=_generated_song_with_drums_and_keys()))

    assert response.intent == "clarify"
    assert "What chord" in response.reply
    assert composer.calls == []
    assert composer.revision_calls == []


def test_spanish_song_edit_routes_to_the_named_instrument():
    composer = _RecordingComposer()
    chat, _, _, _ = _make_chat(composer=composer)

    response = chat.handle(
        ChatRequest(
            message="Hacé la guitarra menos cargada y regenerá solo esa parte.",
            current_song=_generated_song(),
        )
    )

    assert response.intent == "compose"
    assert composer.revision_calls == [
        ("Hacé la guitarra menos cargada y regenerá solo esa parte.", "guitar")
    ]


def test_spanish_reference_question_routes_to_evidence_backed_answer():
    profile = _make_profile()
    chat, _, explainer, store = _make_chat()
    store.save(profile)

    response = chat.handle(ChatRequest(message="¿Qué acordes tiene esta canción?", reference_id=profile.reference_id))

    assert response.intent == "answer_reference"
    assert explainer.calls == [("¿Qué acordes tiene esta canción?", profile.reference_id)]


def test_spanish_composition_request_uses_current_reference():
    profile = _make_profile()
    chat, composer, _, store = _make_chat()
    store.save(profile)

    response = chat.handle(
        ChatRequest(message="Componé un solo usando esta referencia.", reference_id=profile.reference_id)
    )

    assert response.intent == "compose_from_reference"
    assert composer.calls


def test_listening_questions_route_to_the_answer_path():
    profile = _make_profile()
    chat, composer, explainer, store = _make_chat()
    store.save(profile)

    for question in [
        "Does it swing? Where does it build?",
        "How does it sound?",
        "What is the timbre of the drums?",
        "Where is the drop?",
    ]:
        response = chat.handle(ChatRequest(message=question, reference_id=profile.reference_id))
        assert response.intent == "answer_reference", question

    assert composer.calls == []
    assert [call[0] for call in explainer.calls] == [
        "Does it swing? Where does it build?",
        "How does it sound?",
        "What is the timbre of the drums?",
        "Where is the drop?",
    ]
