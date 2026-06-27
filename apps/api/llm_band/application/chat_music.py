"""Conversational orchestrator that routes chat intents to existing use cases.

The orchestrator picks one intent per turn — analyze, answer over a stored
ReferenceProfile, compose from scratch, compose from reference, or ask a single
clarification — and delegates to the application services that already exist.
It never touches HTTP, MIR libraries, or LLM clients directly.
"""

from __future__ import annotations

import re
from typing import Literal, Optional

from pydantic import BaseModel, Field

from llm_band.application.answer_music_question import AnswerMusicQuestion, MusicQuestionExplainer
from llm_band.application.compose_song import ComposeSong
from llm_band.domain.audio_profile import ExplanationAnswer, ReferenceProfile
from llm_band.domain.song_state import SongState
from llm_band.ports.reference_store import ReferenceStore


Intent = Literal[
    "answer_reference",
    "compose",
    "compose_from_reference",
    "clarify",
]


class ChatRequest(BaseModel):
    message: str = Field(min_length=1)
    reference_id: Optional[str] = None


class ChatComposeResult(BaseModel):
    song: SongState
    source: str


class ChatResponse(BaseModel):
    intent: Intent
    reply: str
    reference_id: Optional[str] = None
    answer: Optional[ExplanationAnswer] = None
    compose: Optional[ChatComposeResult] = None
    clarification: Optional[str] = None


_COMPOSE_RE = re.compile(r"\b(compose|generate|make|write|create|sketch|produce)\b", re.IGNORECASE)
_REFERENCE_TOPIC_RE = re.compile(
    r"\b(chord|chords|tempo|bpm|key|energy|section|sections|chorus|verse|analysis|analyze|profile|progression|harmony|harmonic)\b",
    re.IGNORECASE,
)
_REFERENCE_GUIDE_RE = re.compile(
    r"\b(like\s+this|like\s+the\s+(reference|song|track)|based\s+on\s+(this|the\s+(reference|song|track))|using\s+(this|the)\s+(reference|song|track)|inspired\s+by\s+(this|the\s+(reference|song|track))|same\s+(vibe|feel|energy)|in\s+this\s+style)\b",
    re.IGNORECASE,
)


class ChatMusic:
    def __init__(
        self,
        *,
        compose_song: ComposeSong,
        answer_music_question: AnswerMusicQuestion,
        reference_store: ReferenceStore,
    ) -> None:
        self.compose_song = compose_song
        self.answer_music_question = answer_music_question
        self.reference_store = reference_store

    def handle(self, request: ChatRequest) -> ChatResponse:
        message = request.message.strip()
        profile = (
            self.reference_store.get(request.reference_id)
            if request.reference_id
            else None
        )

        intent = self._classify(message, has_reference=profile is not None)

        if intent == "clarify":
            return ChatResponse(
                intent="clarify",
                reply=(
                    "I can analyze an attached file, answer about a reference you already shared, "
                    "or compose a new sketch. What would you like?"
                ),
                clarification="Tell me whether to analyze, answer about the current reference, or compose.",
            )

        if intent == "answer_reference":
            assert profile is not None
            answer = self.answer_music_question.execute(message, profile)
            return ChatResponse(
                intent="answer_reference",
                reply=answer.answer,
                reference_id=profile.reference_id,
                answer=answer,
            )

        if intent == "compose_from_reference":
            assert profile is not None
            style = _style_with_reference(message, profile)
            song, source = self.compose_song.compose(style)
            return ChatResponse(
                intent="compose_from_reference",
                reply=_compose_reply(song, source, reference=profile),
                reference_id=profile.reference_id,
                compose=ChatComposeResult(song=song, source=source),
            )

        song, source = self.compose_song.compose(message or "demo")
        return ChatResponse(
            intent="compose",
            reply=_compose_reply(song, source),
            compose=ChatComposeResult(song=song, source=source),
        )

    def _classify(self, message: str, *, has_reference: bool) -> Intent:
        if not message:
            return "clarify"

        wants_compose = bool(_COMPOSE_RE.search(message))
        asks_about_reference = bool(_REFERENCE_TOPIC_RE.search(message))
        wants_reference_guidance = bool(_REFERENCE_GUIDE_RE.search(message))

        if has_reference:
            if wants_compose and (wants_reference_guidance or asks_about_reference):
                return "compose_from_reference"
            if wants_compose:
                return "compose"
            if asks_about_reference or wants_reference_guidance:
                return "answer_reference"
            return "clarify"

        if wants_compose:
            return "compose"
        if asks_about_reference:
            return "clarify"
        return "compose"


def _compose_reply(song: SongState, source: str, *, reference: Optional[ReferenceProfile] = None) -> str:
    header = song.header
    base = (
        f"Generated a {header.genre} sketch at {header.tempo_bpm} BPM in {header.key} "
        f"({len(song.roster)} instruments, source={source})."
    )
    if reference is not None:
        base += f" Used reference {reference.source.label} as style guide."
    return base


def _style_with_reference(message: str, profile: ReferenceProfile) -> str:
    audio = profile.audio
    if audio is None:
        return message or f"Inspired by {profile.source.label}"

    traits: list[str] = []
    if audio.tempo_bpm is not None:
        traits.append(f"around {round(audio.tempo_bpm)} BPM")
    if audio.key and audio.key_confidence >= 0.5:
        traits.append(f"in {audio.key}")
    if audio.sections:
        first = audio.sections[0]
        if first.energy is not None:
            traits.append(
                "high energy" if first.energy >= 0.7 else "low energy" if first.energy <= 0.35 else "medium energy"
            )

    prefix = message or "Compose something"
    if not traits:
        return f"{prefix} inspired by reference {profile.source.label}"
    return f"{prefix} inspired by reference {profile.source.label}: " + ", ".join(traits)
