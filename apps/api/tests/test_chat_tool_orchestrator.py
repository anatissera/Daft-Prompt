from __future__ import annotations

from music_assistant.application.answer_music_question import AnswerMusicQuestion
from music_assistant.application.chat_music import ChatMusic, ChatRequest, ChatToolDecision
from music_assistant.application.compose_song import prompt_from_composition_brief
from music_assistant.canned import canned_song
from music_assistant.domain.audio_profile import (
    EvidenceClaim,
    ReferenceProfile,
    ReferenceSource,
    ReferenceTransferIntent,
    ReferenceTransferItem,
    SongIdentity,
    SongKnowledgeProfile,
)
from music_assistant.domain.song_state import SongState
from music_assistant.domain.song_state import Header, Part, RosterItem
from music_assistant.infrastructure.storage.in_memory_reference_store import InMemoryReferenceStore
from music_assistant.infrastructure.storage.in_memory_songsterr_tab_store import InMemorySongsterrTabStore
from music_assistant.infrastructure.web_research.songsterr_tabs import (
    InstrumentTabTrack,
    SongsterrTabBundle,
    TabEvent,
    TabMeasure,
)


class FakeStructuredInvoker:
    def __init__(self, decisions: list[ChatToolDecision]):
        self.decisions = decisions
        self.calls = []

    def invoke(self, messages):
        self.calls.append(messages)
        return self.decisions.pop(0)


class FakeChatModel:
    def __init__(self, decisions: list[ChatToolDecision]):
        self.invoker = FakeStructuredInvoker(decisions)

    def with_structured_output(self, schema):
        assert schema is ChatToolDecision
        return self.invoker


class SequencedSchemaModel:
    def __init__(self, outputs):
        self.outputs = list(outputs)
        self.schemas = []

    def with_structured_output(self, schema):
        self.schemas.append(schema)
        output = self.outputs.pop(0)

        class Invoker:
            def invoke(self, _messages):
                return output

        return Invoker()


class RecordingComposer:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def compose(self, style: str) -> tuple[SongState, str]:
        prompt = prompt_from_composition_brief(style) if hasattr(style, "brief_id") else style
        self.calls.append(prompt)
        return canned_song(prompt), "canned"


class PartialFailureComposer:
    def compose(self, style: str) -> tuple[SongState, str]:
        song = SongState(
            request=str(style),
            header=Header(genre="grunge", key="E minor", tempo_bpm=120, num_bars=4),
            roster=[
                RosterItem(id="bass", instrument="electric_bass", midi_range=(28, 55), role="foundation"),
                RosterItem(id="guitar", instrument="electric_guitar", midi_range=(40, 84), role="riff"),
            ],
            parts={
                "bass": Part(instrument_id="bass", notes_summary="(failed to compose: LLMAllProvidersFailed)"),
                "guitar": Part(instrument_id="guitar", notes_summary="distorted power chords"),
            },
        )
        return song, "director"


class FakeResearcher:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def research(self, query: str) -> ReferenceProfile:
        self.calls.append(query)
        claim = EvidenceClaim(
            claim_id="tempo",
            claim_type="tempo",
            value="111 BPM",
            source_name="Fixture",
            source_url="https://fixture.test",
            extraction_method="site_parser",
            confidence=0.8,
            snippet="Tempo: 111 BPM",
        )
        return ReferenceProfile(
            reference_id="ref_researched",
            source=ReferenceSource(
                reference_id="ref_researched",
                kind="metadata",
                label=query,
                uri=f"research://{query}",
                authorized=True,
            ),
            summary="Research ready.",
            knowledge=SongKnowledgeProfile(
                profile_id="song_researched",
                identity=SongIdentity(title=query),
                evidence_claims=[claim],
            ),
        )


def make_chat(
    decisions: list[ChatToolDecision],
    *,
    store: InMemoryReferenceStore | None = None,
    researcher: FakeResearcher | None = None,
) -> tuple[ChatMusic, FakeChatModel, RecordingComposer, FakeResearcher, InMemoryReferenceStore]:
    store = store or InMemoryReferenceStore()
    model = FakeChatModel(decisions)
    composer = RecordingComposer()
    researcher = researcher or FakeResearcher()
    chat = ChatMusic(
        compose_song=composer,
        answer_music_question=AnswerMusicQuestion(),
        reference_store=store,
        chat_model=model,
        song_researcher=researcher,
    )
    return chat, model, composer, researcher, store


def test_llm_tool_orchestrator_researches_and_persists_profile():
    chat, model, composer, researcher, store = make_chat(
        [ChatToolDecision(action="research_song", query="Space Cowboy")]
    )

    response = chat.handle(ChatRequest(message="Who wrote Space Cowboy?"))

    assert response.intent == "answer_reference"
    assert response.reference_id == "ref_researched"
    assert "Research ready" in response.reply
    assert researcher.calls == ["Space Cowboy"]
    assert store.get("ref_researched") is not None
    assert composer.calls == []
    assert model.invoker.calls


def test_llm_tool_orchestrator_answers_current_profile_with_deterministic_tool():
    store = InMemoryReferenceStore()
    researcher = FakeResearcher()
    profile = researcher.research("Space Cowboy")
    store.save(profile)
    chat, _, composer, _, _ = make_chat(
        [ChatToolDecision(action="answer_profile")],
        store=store,
        researcher=researcher,
    )

    response = chat.handle(ChatRequest(message="what is the tempo?", reference_id="ref_researched"))

    assert response.intent == "answer_reference"
    assert "111 BPM" in response.reply
    assert composer.calls == []


def test_llm_tool_orchestrator_prompt_names_current_reference_so_this_song_is_not_ambiguous():
    store = InMemoryReferenceStore()
    researcher = FakeResearcher()
    profile = researcher.research("Another One Bites the Dust Queen")
    store.save(profile)
    chat, model, _, _, _ = make_chat(
        [ChatToolDecision(action="compose_from_reference", composition_request="bass like this song")],
        store=store,
        researcher=researcher,
    )

    chat.handle(
        ChatRequest(
            message="Componé algo nuevo pero con un bajo parecido al de esta canción",
            reference_id="ref_researched",
        )
    )

    prompt_text = str(model.invoker.calls[0])
    assert "Another One Bites the Dust Queen" in prompt_text
    assert "If the user says this song" in prompt_text


def test_llm_tool_orchestrator_recovers_when_model_clarifies_for_existing_reference():
    store = InMemoryReferenceStore()
    researcher = FakeResearcher()
    profile = researcher.research("Another One Bites the Dust Queen")
    store.save(profile)
    model = SequencedSchemaModel(
        [
            ChatToolDecision(action="clarify", clarification="Please provide the reference song for the bassline."),
            ReferenceTransferIntent(
                items=[
                    ReferenceTransferItem(
                        instrument_family="bass",
                        reference_id="ref_researched",
                        transfer_mode="similar",
                    )
                ]
            ),
        ]
    )
    composer = RecordingComposer()
    tab_store = InMemorySongsterrTabStore()
    tab_store.save(
        "ref_researched",
        SongsterrTabBundle(
            source_url="https://songsterr.test/space",
            song_id=1,
            revision_id=2,
            image="img",
            title="Space Cowboy",
            tracks=[
                InstrumentTabTrack(
                    part_id=4,
                    name="Fender Jazz Bass",
                    instrument="Electric Bass (finger)",
                    instrument_family="bass",
                    tuning=["E1", "A1", "D2", "G2"],
                    is_bass=True,
                    measures=[
                        TabMeasure(
                            index=0,
                            marker="Verse",
                            events=[TabEvent(measure_index=0, beat_index=0, duration="1/4", string=1, fret=5)],
                        )
                    ],
                    note_count=1,
                    beat_count=1,
                )
            ],
        ),
    )
    chat = ChatMusic(
        compose_song=composer,
        answer_music_question=AnswerMusicQuestion(),
        reference_store=store,
        chat_model=model,
        songsterr_tab_store=tab_store,
    )

    response = chat.handle(
        ChatRequest(
            message="Componé algo nuevo pero con un bajo parecido al de esta canción",
            reference_id="ref_researched",
        )
    )

    assert response.intent == "compose_from_reference"
    assert response.compose is not None
    assert "Fender Jazz Bass" in composer.calls[0]


def test_llm_tool_orchestrator_composes_from_reference_with_compact_tool_output():
    store = InMemoryReferenceStore()
    researcher = FakeResearcher()
    profile = researcher.research("Space Cowboy")
    store.save(profile)
    chat, model, composer, _, _ = make_chat(
        [ChatToolDecision(action="compose_from_reference", composition_request="make it darker")],
        store=store,
        researcher=researcher,
    )

    response = chat.handle(ChatRequest(message="make it darker with this groove", reference_id="ref_researched"))

    assert response.intent == "compose_from_reference"
    assert response.compose is not None
    assert "CompositionBrief" in composer.calls[0]
    assert "make it darker" in composer.calls[0]
    compact_context = model.invoker.calls[0][1]["content"]
    assert "raw html" not in compact_context.lower()
    assert "full lyrics" not in compact_context.lower()


def test_llm_tool_orchestrator_enriches_reference_composition_with_instrument_intent():
    store = InMemoryReferenceStore()
    researcher = FakeResearcher()
    profile = researcher.research("Space Cowboy")
    store.save(profile)
    tab_store = InMemorySongsterrTabStore()
    tab_store.save(
        "ref_researched",
        SongsterrTabBundle(
            source_url="https://songsterr.test/space",
            song_id=1,
            revision_id=2,
            image="img",
            title="Space Cowboy",
            tracks=[
                InstrumentTabTrack(
                    part_id=4,
                    name="Fender Jazz Bass",
                    instrument="Electric Bass (finger)",
                    instrument_family="bass",
                    tuning=["E1", "A1", "D2", "G2"],
                    is_bass=True,
                    measures=[
                        TabMeasure(
                            index=0,
                            marker="Verse",
                            events=[TabEvent(measure_index=0, beat_index=0, duration="1/4", string=1, fret=5)],
                        )
                    ],
                    note_count=1,
                    beat_count=1,
                )
            ],
        ),
    )
    model = SequencedSchemaModel(
        [
            ChatToolDecision(action="compose_from_reference", composition_request="haz un bajo con esa intencion"),
            ReferenceTransferIntent(
                items=[
                    ReferenceTransferItem(
                        instrument_family="bass",
                        reference_id="ref_researched",
                        transfer_mode="similar",
                        fidelity=0.7,
                    )
                ]
            ),
        ]
    )
    composer = RecordingComposer()
    chat = ChatMusic(
        compose_song=composer,
        answer_music_question=AnswerMusicQuestion(),
        reference_store=store,
        chat_model=model,
        songsterr_tab_store=tab_store,
    )

    response = chat.handle(ChatRequest(message="quiero un bajo con esa intencion", reference_id="ref_researched"))

    assert response.intent == "compose_from_reference"
    assert "instrument_requests" in composer.calls[0]
    assert "Fender Jazz Bass" in composer.calls[0]
    assert model.schemas == [ChatToolDecision, ReferenceTransferIntent]
    assert response.compose is not None
    assert response.compose.reference_transfer_intent is not None
    assert response.compose.reference_transfer_intent["items"][0]["instrument_family"] == "bass"
    assert response.compose.instrument_requests_summary[0]["instrument_family"] == "bass"
    assert response.compose.instrument_requests_summary[0]["transfer_mode"] == "similar"


def test_llm_tool_orchestrator_exposes_literal_application_summary():
    store = InMemoryReferenceStore()
    researcher = FakeResearcher()
    profile = researcher.research("Space Cowboy")
    store.save(profile)
    tab_store = InMemorySongsterrTabStore()
    tab_store.save(
        "ref_researched",
        SongsterrTabBundle(
            source_url="https://songsterr.test/space",
            song_id=1,
            revision_id=2,
            image="img",
            title="Space Cowboy",
            tracks=[
                InstrumentTabTrack(
                    part_id=4,
                    name="Fender Jazz Bass",
                    instrument="Electric Bass (finger)",
                    instrument_family="bass",
                    tuning=["E1", "A1", "D2", "G2"],
                    is_bass=True,
                    measures=[
                        TabMeasure(
                            index=0,
                            marker="Verse",
                            events=[TabEvent(measure_index=0, beat_index=0, duration="1/4", string=1, fret=5)],
                        )
                    ],
                    note_count=1,
                    beat_count=1,
                )
            ],
        ),
    )
    model = SequencedSchemaModel(
        [
            ChatToolDecision(action="compose_from_reference", composition_request="usa exactamente el mismo bajo"),
            ReferenceTransferIntent(
                items=[
                    ReferenceTransferItem(
                        instrument_family="bass",
                        reference_id="ref_researched",
                        transfer_mode="literal",
                        fidelity=1.0,
                    )
                ]
            ),
        ]
    )
    composer = RecordingComposer()
    chat = ChatMusic(
        compose_song=composer,
        answer_music_question=AnswerMusicQuestion(),
        reference_store=store,
        chat_model=model,
        songsterr_tab_store=tab_store,
    )

    response = chat.handle(ChatRequest(message="usa exactamente el mismo bajo", reference_id="ref_researched"))

    assert response.compose is not None
    assert response.compose.literal_applications == [
        {
            "instrument_family": "bass",
            "note_pack_id": "bass_verse_0_0",
            "note_count": 1,
            "bar_count": 1,
            "applied": True,
            "mode": "literal_loop",
            "reason": "",
        }
    ]


def test_operational_clarification_does_not_block_full_reference_composition_or_invent_piano():
    store = InMemoryReferenceStore()
    researcher = FakeResearcher()
    profile = researcher.research("Another One Bites the Dust Queen")
    store.save(profile)
    tab_store = InMemorySongsterrTabStore()
    tab_store.save(
        "ref_researched",
        SongsterrTabBundle(
            source_url="https://songsterr.test/another-one",
            song_id=1,
            revision_id=2,
            image="img",
            title="Another One Bites the Dust",
            tracks=[
                InstrumentTabTrack(
                    part_id=4,
                    name="John Deacon | Fender Precision Bass",
                    instrument="Electric Bass (finger)",
                    instrument_family="bass",
                    tuning=["43", "38", "33", "28"],
                    is_bass=True,
                    measures=[
                        TabMeasure(
                            index=0,
                            marker="Intro",
                            events=[
                                TabEvent(measure_index=0, beat_index=0.5, duration="1/16", string=3, fret=5),
                                TabEvent(measure_index=0, beat_index=0.75, duration="1/16", string=3, fret=3),
                            ],
                        )
                    ],
                    note_count=2,
                    beat_count=2,
                )
            ],
        ),
    )
    model = SequencedSchemaModel(
        [
            ChatToolDecision(
                action="compose_from_reference",
                composition_request=(
                    "Intentá hacer una canción entera lo más igual posible a esta referencia. "
                    "Si falta evidencia para algún instrumento, aproximá y avisá."
                ),
            ),
            ReferenceTransferIntent(
                clarification=(
                    "Piano parts will be approximated since no symbolic data exists. "
                    "All other instruments will be recreated exactly where symbolic data is available."
                )
            ),
        ]
    )
    composer = RecordingComposer()
    chat = ChatMusic(
        compose_song=composer,
        answer_music_question=AnswerMusicQuestion(),
        reference_store=store,
        chat_model=model,
        songsterr_tab_store=tab_store,
    )

    response = chat.handle(
        ChatRequest(
            message=(
                "Intentá hacer una canción entera lo más igual posible a esta referencia. "
                "Copiá literalmente todos los instrumentos y secciones para los que tengas notas simbólicas reales; "
                "si falta evidencia para algún instrumento o sección, componelo lo más parecido posible y avisá."
            ),
            reference_id="ref_researched",
        )
    )

    assert response.intent == "compose_from_reference"
    assert response.compose is not None
    assert response.compose.literal_applications[0]["instrument_family"] == "bass"
    assert response.compose.literal_applications[0]["applied"] is True
    assert "Piano" not in " ".join(response.compose.warnings + response.compose.uncertainty_notes)
    assert "John Deacon | Fender Precision Bass" in composer.calls[0]


def test_operational_clarification_for_available_instrument_is_preserved_as_uncertainty():
    store = InMemoryReferenceStore()
    researcher = FakeResearcher()
    profile = researcher.research("Electric Piano Song")
    store.save(profile)
    tab_store = InMemorySongsterrTabStore()
    tab_store.save(
        "ref_researched",
        SongsterrTabBundle(
            source_url="https://songsterr.test/piano",
            song_id=1,
            revision_id=2,
            image="img",
            title="Electric Piano Song",
            tracks=[
                InstrumentTabTrack(
                    part_id=5,
                    name="Rhodes",
                    instrument="Electric Piano",
                    instrument_family="piano",
                    is_piano=True,
                    measures=[
                        TabMeasure(
                            index=0,
                            marker="Verse",
                            events=[TabEvent(measure_index=0, beat_index=0, duration="1/2")],
                        )
                    ],
                    note_count=1,
                    beat_count=1,
                )
            ],
        ),
    )
    model = SequencedSchemaModel(
        [
            ChatToolDecision(action="compose_from_reference", composition_request="recreate the full song"),
            ReferenceTransferIntent(clarification="Piano parts will be approximated since no symbolic data exists."),
        ]
    )
    chat = ChatMusic(
        compose_song=RecordingComposer(),
        answer_music_question=AnswerMusicQuestion(),
        reference_store=store,
        chat_model=model,
        songsterr_tab_store=tab_store,
    )

    response = chat.handle(ChatRequest(message="recreate the full song", reference_id="ref_researched"))

    assert response.compose is not None
    assert "Piano parts will be approximated since no symbolic data exists" in response.compose.uncertainty_notes
    assert response.compose.instrument_requests_summary[0]["instrument_family"] == "piano"
    assert response.compose.instrument_requests_summary[0]["transfer_mode"] == "similar"


def test_unavailable_instrument_from_transfer_intent_is_not_passed_to_brief():
    store = InMemoryReferenceStore()
    researcher = FakeResearcher()
    profile = researcher.research("Another One Bites the Dust Queen")
    store.save(profile)
    tab_store = InMemorySongsterrTabStore()
    tab_store.save(
        "ref_researched",
        SongsterrTabBundle(
            source_url="https://songsterr.test/another-one",
            song_id=1,
            revision_id=2,
            image="img",
            title="Another One Bites the Dust",
            tracks=[
                InstrumentTabTrack(
                    part_id=4,
                    name="John Deacon | Fender Precision Bass",
                    instrument="Electric Bass (finger)",
                    instrument_family="bass",
                    tuning=["43", "38", "33", "28"],
                    is_bass=True,
                    measures=[
                        TabMeasure(
                            index=0,
                            marker="Intro",
                            events=[TabEvent(measure_index=0, beat_index=0, duration="1/4", string=3, fret=0)],
                        )
                    ],
                    note_count=1,
                    beat_count=1,
                )
            ],
        ),
    )
    model = SequencedSchemaModel(
        [
            ChatToolDecision(action="compose_from_reference", composition_request="recreate the full song"),
            ReferenceTransferIntent(
                items=[
                    ReferenceTransferItem(
                        instrument_family="piano",
                        reference_id="ref_researched",
                        transfer_mode="similar",
                    ),
                    ReferenceTransferItem(
                        instrument_family="bass",
                        reference_id="ref_researched",
                        transfer_mode="literal",
                    ),
                ]
            ),
        ]
    )
    chat = ChatMusic(
        compose_song=RecordingComposer(),
        answer_music_question=AnswerMusicQuestion(),
        reference_store=store,
        chat_model=model,
        songsterr_tab_store=tab_store,
    )

    response = chat.handle(ChatRequest(message="recreate the full song", reference_id="ref_researched"))

    assert response.compose is not None
    families = [item["instrument_family"] for item in response.compose.instrument_requests_summary]
    assert families == ["bass"]


def test_blocking_reference_transfer_clarification_returns_clarify_not_empty_composition():
    store = InMemoryReferenceStore()
    researcher = FakeResearcher()
    profile = researcher.research("Space Cowboy")
    store.save(profile)
    tab_store = InMemorySongsterrTabStore()
    tab_store.save(
        "ref_researched",
        SongsterrTabBundle(
            source_url="https://songsterr.test/space",
            song_id=1,
            revision_id=2,
            image="img",
            title="Space Cowboy",
            tracks=[
                InstrumentTabTrack(
                    part_id=4,
                    name="Fender Jazz Bass",
                    instrument="Electric Bass (finger)",
                    instrument_family="bass",
                    tuning=["E1", "A1", "D2", "G2"],
                    is_bass=True,
                    measures=[
                        TabMeasure(
                            index=0,
                            marker="Verse",
                            events=[TabEvent(measure_index=0, beat_index=0, duration="1/4", string=1, fret=5)],
                        )
                    ],
                    note_count=1,
                    beat_count=1,
                )
            ],
        ),
    )
    model = SequencedSchemaModel(
        [
            ChatToolDecision(action="compose_from_reference", composition_request="compose from this reference"),
            ReferenceTransferIntent(clarification="Which instrument should I copy?"),
        ]
    )
    chat = ChatMusic(
        compose_song=RecordingComposer(),
        answer_music_question=AnswerMusicQuestion(),
        reference_store=store,
        chat_model=model,
        songsterr_tab_store=tab_store,
    )

    response = chat.handle(ChatRequest(message="compose from this reference", reference_id="ref_researched"))

    assert response.intent == "clarify"
    assert response.compose is None
    assert response.clarification == "Which instrument should I copy?"


def test_llm_tool_orchestrator_marks_partial_agent_failures_in_reply_and_warnings():
    store = InMemoryReferenceStore()
    researcher = FakeResearcher()
    profile = researcher.research("Space Cowboy")
    store.save(profile)
    model = FakeChatModel(
        [ChatToolDecision(action="compose_from_reference", composition_request="make grunge")]
    )
    chat = ChatMusic(
        compose_song=PartialFailureComposer(),
        answer_music_question=AnswerMusicQuestion(),
        reference_store=store,
        chat_model=model,
    )

    response = chat.handle(ChatRequest(message="make grunge", reference_id="ref_researched"))

    assert response.compose is not None
    assert "partial failures" in response.reply
    assert response.compose.warnings == ["bass failed to compose: LLMAllProvidersFailed"]


def test_llm_tool_orchestrator_clarifies_and_refuses_off_topic():
    clarify_chat, _, _, _, _ = make_chat([ChatToolDecision(action="clarify", clarification="Which song?")])
    refusal_chat, _, _, _, _ = make_chat([ChatToolDecision(action="off_topic", clarification="Music only.")])

    clarify = clarify_chat.handle(ChatRequest(message="compare these"))
    refusal = refusal_chat.handle(ChatRequest(message="write my tax return"))

    assert clarify.intent == "clarify"
    assert clarify.clarification == "Which song?"
    assert refusal.intent == "off_topic"
    assert refusal.reply == "Music only."


def test_deterministic_fallback_does_not_call_llm_for_profile_qa():
    store = InMemoryReferenceStore()
    researcher = FakeResearcher()
    profile = researcher.research("Space Cowboy")
    store.save(profile)
    model = FakeChatModel([ChatToolDecision(action="compose")])
    chat = ChatMusic(
        compose_song=RecordingComposer(),
        answer_music_question=AnswerMusicQuestion(),
        reference_store=store,
        chat_model=None,
        song_researcher=researcher,
    )

    response = chat.handle(ChatRequest(message="what is the tempo?", reference_id="ref_researched"))

    assert response.intent == "answer_reference"
    assert "111 BPM" in response.reply
    assert model.invoker.calls == []
