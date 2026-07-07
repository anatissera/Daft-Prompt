"""Conversational orchestrator that routes chat intents to existing use cases.

The orchestrator picks one intent per turn — analyze, answer over a stored
ReferenceProfile, compose from scratch, compose from reference, or ask a single
clarification — and delegates to the application services that already exist.
It never touches HTTP, MIR libraries, or LLM clients directly.
"""

from __future__ import annotations

import re
import time
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

from music_assistant.application.answer_music_question import AnswerMusicQuestion, MusicQuestionExplainer
from music_assistant.application.chat_agent import ChatAgent
from music_assistant.application.composition_brief import BuildCompositionBrief
from music_assistant.application.compose_song import ComposeSong
from music_assistant.application.music_tool_models import (
    AnswerToolOutput,
    ChatAgentDecision as ChatToolDecision,
    CompositionRequestToolInput,
    CompositionToolOutput,
)
from music_assistant.application.music_tools import MusicTools
from music_assistant.domain.audio_profile import ExplanationAnswer, ReferenceProfile
from music_assistant.domain.errors import OffTopicRequest
from music_assistant.domain.song_state import SongState
from music_assistant.domain.usage import USAGE_TRACKER, UsageTracker
from music_assistant.ports.llm import ChatModel
from music_assistant.ports.reference_store import ReferenceStore
from music_assistant.ports.song_researcher import SongResearcher
from music_assistant.ports.songsterr_tab_store import SongsterrTabStore


Intent = Literal[
    "answer_reference",
    "compose",
    "compose_from_reference",
    "clarify",
    "off_topic",
]
class ChatRequest(BaseModel):
    message: str = Field(min_length=1)
    reference_id: Optional[str] = None
    reference_ids: list[str] = Field(default_factory=list)
    reference_context: Optional[str] = None


class ChatArtifacts(BaseModel):
    midi: str
    musicxml: str


class ChatComposeResult(BaseModel):
    song: SongState
    source: str
    artifacts: Optional[ChatArtifacts] = None
    reference_transfer_intent: Optional[dict[str, Any]] = None
    instrument_requests_summary: list[dict[str, Any]] = Field(default_factory=list)
    literal_applications: list[dict[str, Any]] = Field(default_factory=list)
    uncertainty_notes: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class UsageInfo(BaseModel):
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    calls: int = 0
    elapsed_seconds: float = 0.0


class ChatResponse(BaseModel):
    intent: Intent
    reply: str
    reference_id: Optional[str] = None
    answer: Optional[ExplanationAnswer] = None
    compose: Optional[ChatComposeResult] = None
    clarification: Optional[str] = None
    usage: Optional[UsageInfo] = None
    error: Optional[dict[str, Any]] = None


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
        chat_model: ChatModel | None = None,
        song_researcher: SongResearcher | None = None,
        songsterr_tab_store: SongsterrTabStore | None = None,
    ) -> None:
        self.compose_song = compose_song
        self.answer_music_question = answer_music_question
        self.reference_store = reference_store
        self.chat_model = chat_model
        self.song_researcher = song_researcher
        self.songsterr_tab_store = songsterr_tab_store

    def handle(self, request: ChatRequest) -> ChatResponse:
        tracker = UsageTracker()
        token = USAGE_TRACKER.set(tracker)
        started_at = time.monotonic()
        try:
            response = self._handle(request)
        finally:
            USAGE_TRACKER.reset(token)
        elapsed = time.monotonic() - started_at
        usage = UsageInfo(
            input_tokens=tracker.input_tokens,
            output_tokens=tracker.output_tokens,
            total_tokens=tracker.total_tokens,
            calls=tracker.calls,
            elapsed_seconds=round(elapsed, 3),
        )
        return response.model_copy(update={"usage": usage})

    def _handle(self, request: ChatRequest) -> ChatResponse:
        message = request.message.strip()
        profile = (
            self.reference_store.get(request.reference_id)
            if request.reference_id
            else None
        )
        profiles = _profiles_from_request(request, self.reference_store)
        if profile is None and profiles:
            profile = profiles[0]

        if self.chat_model is not None:
            return self._handle_with_llm_tools(request, message, profile, profiles)

        intent = self._classify(message, has_reference=profile is not None)
        return self._execute_deterministic_intent(intent, message, profile)

    def _handle_with_llm_tools(
        self,
        request: ChatRequest,
        message: str,
        profile: ReferenceProfile | None,
        profiles: list[ReferenceProfile],
    ) -> ChatResponse:
        assert self.chat_model is not None
        tools = MusicTools(
            compose_song=self.compose_song,
            answer_music_question=self.answer_music_question,
            reference_store=self.reference_store,
            song_researcher=self.song_researcher,
            songsterr_tab_store=self.songsterr_tab_store,
            chat_model=self.chat_model,
        )
        agent_request = request.model_copy(
            update={"reference_context": _compact_profiles_context(profiles or ([profile] if profile else []))}
        )
        agent_result = ChatAgent(chat_model=self.chat_model, tools=tools).run(agent_request)
        if profile is not None and _clarification_asks_for_existing_reference(agent_result.reply):
            output = tools.request_composition(
                CompositionRequestToolInput(
                    composition_request=message,
                    reference_id=profile.reference_id,
                    reference_ids=request.reference_ids,
                )
            )
            if isinstance(output, CompositionToolOutput) and output.song is not None and output.source is not None:
                return ChatResponse(
                    intent="compose_from_reference",
                    reply=output.answer,
                    reference_id=profile.reference_id,
                    compose=_compose_result_from_tool_output(output),
                )
        return self._response_from_agent_result(agent_result)

    def _response_from_agent_result(self, agent_result) -> ChatResponse:
        output = agent_result.tool_output
        answer = output.explanation if isinstance(output, AnswerToolOutput) else None
        compose = None
        if isinstance(output, CompositionToolOutput) and output.song is not None and output.source is not None:
            compose = _compose_result_from_tool_output(output)
        if isinstance(output, CompositionToolOutput) and compose is None and output.error:
            clarification = output.answer if output.error == "clarification_needed" else None
            return ChatResponse(
                intent="clarify" if clarification else "clarify",
                reply=output.answer or "Composition could not be completed.",
                reference_id=output.reference_id,
                clarification=clarification,
                error={"code": output.error, "message": output.answer or output.error},
            )
        return ChatResponse(
            intent=agent_result.intent,  # type: ignore[arg-type]
            reply=agent_result.reply,
            reference_id=agent_result.reference_id,
            answer=answer,
            compose=compose,
            clarification=agent_result.clarification,
        )

    def _execute_deterministic_intent(
        self,
        intent: Intent,
        message: str,
        profile: ReferenceProfile | None,
    ) -> ChatResponse:

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
            return self._compose_from_reference(message, profile)

        return self._compose(message or "demo")

    def _compose(self, style: str) -> ChatResponse:
        try:
            song, source = self.compose_song.compose(style)
        except OffTopicRequest as refusal:
            return _off_topic_response(refusal)
        return ChatResponse(
            intent="compose",
            reply=_compose_reply(song, source),
            compose=ChatComposeResult(song=song, source=source, warnings=_composition_warnings(song)),
        )

    def _compose_from_references(self, message: str, profiles: list[ReferenceProfile]) -> ChatResponse:
        knowledge_profiles = [profile.knowledge for profile in profiles if profile.knowledge is not None]
        if len(knowledge_profiles) != len(profiles):
            return ChatResponse(
                intent="clarify",
                reply="All selected references need song knowledge profiles before I can mix traits.",
                clarification="Research or analyze the missing references first.",
            )
        built = BuildCompositionBrief().execute(message, knowledge_profiles)
        if built.clarification:
            return ChatResponse(intent="clarify", reply=built.clarification, clarification=built.clarification)
        assert built.brief is not None
        try:
            song, source = self.compose_song.compose(built.brief)
        except OffTopicRequest as refusal:
            return _off_topic_response(refusal)
        return ChatResponse(
            intent="compose_from_reference",
            reply=_compose_reply(song, source, reference=profiles[0]),
            reference_id=profiles[0].reference_id,
            compose=ChatComposeResult(song=song, source=source, warnings=_composition_warnings(song)),
        )

    def _compose_from_reference(self, message: str, profile: ReferenceProfile) -> ChatResponse:
        if profile.knowledge is not None:
            built = BuildCompositionBrief().execute(message, [profile.knowledge])
            if built.clarification:
                return ChatResponse(
                    intent="clarify",
                    reply=built.clarification,
                    clarification=built.clarification,
                    reference_id=profile.reference_id,
                )
            if built.brief is not None:
                try:
                    song, source = self.compose_song.compose(built.brief)
                except OffTopicRequest as refusal:
                    return _off_topic_response(refusal)
                return ChatResponse(
                    intent="compose_from_reference",
                    reply=_compose_reply(song, source, reference=profile),
                    reference_id=profile.reference_id,
                    compose=ChatComposeResult(song=song, source=source, warnings=_composition_warnings(song)),
                )

        style = _style_with_reference(message, profile)
        try:
            song, source = self.compose_song.compose(style)
        except OffTopicRequest as refusal:
            return _off_topic_response(refusal)
        return ChatResponse(
            intent="compose_from_reference",
            reply=_compose_reply(song, source, reference=profile),
            reference_id=profile.reference_id,
            compose=ChatComposeResult(song=song, source=source, warnings=_composition_warnings(song)),
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


def _off_topic_response(refusal: OffTopicRequest) -> ChatResponse:
    return ChatResponse(intent="off_topic", reply=refusal.message)


def _compose_reply(song: SongState, source: str, *, reference: Optional[ReferenceProfile] = None) -> str:
    header = song.header
    base = (
        f"Generated a {header.genre} sketch at {header.tempo_bpm} BPM in {header.key} "
        f"({len(song.roster)} instruments, source={source})."
    )
    if reference is not None:
        base += f" Used reference {reference.source.label} as style guide."
    warnings = _composition_warnings(song)
    if warnings:
        base += f" Generated with partial failures: {'; '.join(warnings)}."
    return base


def _compose_result_from_tool_output(output: CompositionToolOutput) -> ChatComposeResult:
    assert output.song is not None and output.source is not None
    return ChatComposeResult(
        song=output.song,
        source=output.source,
        reference_transfer_intent=output.reference_transfer_intent,
        instrument_requests_summary=output.instrument_requests_summary,
        literal_applications=output.literal_applications,
        uncertainty_notes=output.uncertainty_notes,
        warnings=output.warnings,
    )


def _composition_warnings(song: SongState) -> list[str]:
    warnings: list[str] = []
    for instrument_id, part in song.parts.items():
        summary = part.notes_summary or ""
        marker = "(failed to compose:"
        if marker not in summary:
            continue
        reason = summary.split(marker, 1)[1].split(")", 1)[0].strip()
        warnings.append(f"{instrument_id} failed to compose: {reason}")
    warnings.extend(error for error in song.errors if error)
    return warnings


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


def _profiles_from_request(request: ChatRequest, store: ReferenceStore) -> list[ReferenceProfile]:
    ids = list(request.reference_ids)
    if request.reference_id and request.reference_id not in ids:
        ids.insert(0, request.reference_id)
    profiles: list[ReferenceProfile] = []
    for reference_id in ids:
        profile = store.get(reference_id)
        if profile is not None:
            profiles.append(profile)
    return profiles


def _clarification_asks_for_existing_reference(reply: str) -> bool:
    normalized = reply.lower()
    return (
        ("reference" in normalized or "song" in normalized or "canción" in normalized or "cancion" in normalized)
        and ("provide" in normalized or "which" in normalized or "what" in normalized or "qué" in normalized or "que" in normalized)
    )


def _compact_profiles_context(profiles: list[ReferenceProfile]) -> str:
    if not profiles:
        return "No current profile."
    return "\n".join(_compact_profile_context(profile) for profile in profiles)


def _chat_decision_messages(message: str, profile: ReferenceProfile | None) -> list[dict[str, str]]:
    context = _compact_profile_context(profile) if profile else "No current profile."
    return [
        {
            "role": "system",
            "content": (
                "You are LLMinem's music chat orchestrator. Choose one tool action only: "
                "research_song, answer_profile, compose, compose_from_reference, clarify, or off_topic. "
                "Use tools for evidence; do not answer from memory, scrape directly, output raw HTML, "
                "full lyrics, or generated song JSON."
            ),
        },
        {"role": "system", "content": f"Current compact profile context: {context}"},
        {"role": "user", "content": message},
    ]


def _compact_profile_context(profile: ReferenceProfile) -> str:
    if profile.knowledge is not None:
        knowledge = profile.knowledge
        sections = ", ".join(section.name for section in knowledge.sections[:6]) or "none"
        claims = ", ".join(
            f"{claim.claim_type}:{claim.value}" for claim in knowledge.evidence_claims[:8]
        ) or "none"
        conflicts = ", ".join(conflict.claim_type for conflict in knowledge.conflicts[:4]) or "none"
        return (
            f"id={profile.reference_id}; title={knowledge.identity.title}; "
            f"artist={knowledge.identity.artist or 'unknown'}; sections={sections}; "
            f"claims={claims}; conflicts={conflicts}"
        )
    audio = profile.audio
    if audio is None:
        return f"id={profile.reference_id}; label={profile.source.label}; no audio or knowledge profile"
    bits = [f"id={profile.reference_id}", f"label={profile.source.label}"]
    if audio.tempo_bpm is not None:
        bits.append(f"tempo={round(audio.tempo_bpm)} BPM")
    if audio.key:
        bits.append(f"key={audio.key}")
    if audio.sections:
        bits.append("sections=" + ", ".join(section.name for section in audio.sections[:6]))
    return "; ".join(bits)
