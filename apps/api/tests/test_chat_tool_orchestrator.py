from __future__ import annotations

from music_assistant.application.answer_music_question import AnswerMusicQuestion
from music_assistant.application.chat_music import ChatMusic, ChatRequest, ChatToolDecision
from music_assistant.canned import canned_song
from music_assistant.domain.audio_profile import (
    EvidenceClaim,
    ReferenceProfile,
    ReferenceSource,
    SongIdentity,
    SongKnowledgeProfile,
)
from music_assistant.domain.song_state import SongState
from music_assistant.infrastructure.storage.in_memory_reference_store import InMemoryReferenceStore


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


class RecordingComposer:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def compose(self, style: str) -> tuple[SongState, str]:
        self.calls.append(style)
        return canned_song(style), "canned"


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
    assert "make it darker" in composer.calls[0]
    compact_context = model.invoker.calls[0][1]["content"]
    assert "raw html" not in compact_context.lower()
    assert "full lyrics" not in compact_context.lower()


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
