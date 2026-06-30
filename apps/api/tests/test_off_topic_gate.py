"""Off-topic gating lives in the director (the graph's first LLM node), not in a
separate web-side classifier. The director returns off_topic + a refusal when the
request is not a music-composition task; chat surfaces it as intent='off_topic'.
"""

from __future__ import annotations

import pytest

from llm_band.agents.director import DirectorOutput, run_director
from llm_band.application.answer_music_question import AnswerMusicQuestion
from llm_band.application.chat_music import ChatMusic, ChatRequest
from llm_band.domain.audio_profile import ExplanationAnswer, ReferenceProfile
from llm_band.domain.errors import OffTopicRequest
from llm_band.domain.song_state import SongState
from llm_band.infrastructure.storage.in_memory_reference_store import InMemoryReferenceStore

from tests.test_director import FakeLLM, _output


def test_director_raises_off_topic_when_request_is_not_music():
    out = DirectorOutput(off_topic=True, refusal="I only compose music sketches.")

    with pytest.raises(OffTopicRequest) as excinfo:
        run_director("what's the weather?", llm=FakeLLM(out))

    assert "compose music" in str(excinfo.value)


def test_director_composes_normally_when_in_scope():
    song = run_director("disco", llm=FakeLLM(_output(4)))

    assert isinstance(song, SongState)
    assert song.roster, "in-scope request should still produce a roster"


class _OffTopicComposer:
    """Stands in for ComposeSong: refuses by raising OffTopicRequest."""

    def __init__(self, message: str) -> None:
        self.message = message
        self.calls: list[str] = []

    def compose(self, style: str) -> tuple[SongState, str]:
        self.calls.append(style)
        raise OffTopicRequest(self.message)


class _StubExplainer:
    def answer(self, question: str, profile: ReferenceProfile) -> ExplanationAnswer:
        return ExplanationAnswer(reference_id=profile.reference_id, answer="", evidence=[])


def test_chat_returns_off_topic_intent_when_compose_refuses():
    composer = _OffTopicComposer("I only handle music tasks: compose, analyze audio, or ask about a reference.")
    chat = ChatMusic(
        compose_song=composer,
        answer_music_question=AnswerMusicQuestion(_StubExplainer()),
        reference_store=InMemoryReferenceStore(),
    )

    response = chat.handle(ChatRequest(message="write me a haiku about cats"))

    assert response.intent == "off_topic"
    assert "music tasks" in response.reply
    assert response.compose is None
    assert composer.calls == ["write me a haiku about cats"]
