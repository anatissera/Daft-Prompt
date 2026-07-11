from __future__ import annotations

from pydantic import BaseModel

from music_assistant.application.answer_music_question import AnswerMusicQuestion
from music_assistant.application.chat_music import ChatMusic, ChatRequest
from music_assistant.application.music_tool_models import ChatAgentDecision
from music_assistant.domain.audio_profile import EvidenceClaim, ReferenceProfile, ReferenceSource, SongIdentity, SongKnowledgeProfile
from music_assistant.infrastructure.storage.in_memory_reference_store import InMemoryReferenceStore
from music_assistant.infrastructure.storage.in_memory_songsterr_tab_store import InMemorySongsterrTabStore
from music_assistant.infrastructure.web_research.songsterr_tabs import InstrumentTabTrack, SongsterrTabBundle, TabEvent, TabMeasure


class _SomethingResearcher:
    def research(self, query: str) -> ReferenceProfile:
        knowledge = SongKnowledgeProfile(
            profile_id="song_something",
            identity=SongIdentity(title="Something", artist="The Beatles"),
            metadata={"songsterr_tab_index": {"loaded": True, "sections": ["Intro", "Chorus"]}},
            evidence_claims=[EvidenceClaim(
                claim_id="something_chords",
                claim_type="chord_progression",
                value="**Intro:** C | Cmaj7 | F | G",
                normalized_value="**Intro:** C | Cmaj7 | F | G",
                section_name="intro",
                source_name="Chord Fixture",
                source_url="https://fixture.test/something",
                extraction_method="manual_fixture",
                confidence=0.82,
                snippet="source-backed Something chord progression",
            )],
        )
        return ReferenceProfile(
            reference_id="ref_something",
            source=ReferenceSource(
                reference_id="ref_something",
                kind="metadata",
                label=query,
                uri="research://something",
                authorized=True,
            ),
            knowledge=knowledge,
        )


class _StructuredRouter:
    def __init__(self) -> None:
        self.calls = 0

    def with_structured_output(self, schema: type[BaseModel]):
        assert schema is ChatAgentDecision
        router = self

        class Invoker:
            def invoke(self, _messages):
                router.calls += 1
                return ChatAgentDecision(
                    action="search_song_evidence",
                    research_scope="song",
                    song_title="Something",
                    song_artist="The Beatles",
                    requested_info=["chords"],
                    original_query="What chords does Something by The Beatles have?",
                )

        return Invoker()


def _tabs() -> InMemorySongsterrTabStore:
    store = InMemorySongsterrTabStore()
    store.save("ref_something", SongsterrTabBundle(
        source_url="https://songsterr.test/something",
        song_id=1,
        revision_id=1,
        image="fixture",
        title="Something",
        artist="The Beatles",
        tracks=[InstrumentTabTrack(
            part_id=1,
            name="George Harrison guitar",
            instrument="Guitar",
            instrument_family="guitar",
            is_guitar=True,
            tuning=["E4", "B3", "G3", "D3", "A2", "E2"],
            source_url="https://songsterr.test/something/guitar",
            measures=[
                TabMeasure(index=0, marker="Intro", events=[
                    TabEvent(measure_index=0, beat_index=0, duration="1/4", string=1, fret=2),
                    TabEvent(measure_index=0, beat_index=1, duration="1/4", string=2, fret=10),
                ]),
                TabMeasure(index=1, marker="Chorus", events=[
                    TabEvent(measure_index=1, beat_index=0, duration="1/4", string=3, fret=4),
                ]),
            ],
            note_count=3,
            beat_count=3,
        )],
    ))
    return store


def test_something_chord_question_is_answered_on_first_response_without_markdown_artifacts():
    store = InMemoryReferenceStore()
    router = _StructuredRouter()
    chat = ChatMusic(
        compose_song=None,  # type: ignore[arg-type]
        answer_music_question=AnswerMusicQuestion(),
        reference_store=store,
        chat_model=router,
        song_researcher=_SomethingResearcher(),
        songsterr_tab_store=_tabs(),
    )

    response = chat.handle(ChatRequest(message="What chords does Something by The Beatles have?"))

    assert response.intent == "answer_reference"
    assert "Cmaj7" in response.reply
    assert "**" not in response.reply
    assert response.reference_id == "ref_something"
    assert router.calls == 1


def test_something_intro_tab_request_selects_intro_measures():
    store = InMemoryReferenceStore()
    profile = _SomethingResearcher().research("Something by The Beatles")
    store.save(profile)
    chat = ChatMusic(
        compose_song=None,  # type: ignore[arg-type]
        answer_music_question=AnswerMusicQuestion(),
        reference_store=store,
        songsterr_tab_store=_tabs(),
    )

    response = chat.handle(ChatRequest(message="Show the intro guitar tabs", reference_id="ref_something"))

    assert response.tab_excerpt is not None
    assert response.tab_excerpt.section_name == "intro"
    assert [measure.index for measure in response.tab_excerpt.measures] == [0]
    assert response.tab_excerpt.measures[0].events[1].fret == 10

