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
from music_assistant.application.compose_song import ComposeConfigurationError, ComposeSong
from music_assistant.application.language import is_spanish
from music_assistant.application.music_tool_models import (
    AnswerToolOutput,
    ChatAgentDecision as ChatToolDecision,
    CompositionRequestToolInput,
    CompositionToolOutput,
    TabExcerptToolOutput,
)
from music_assistant.application.music_tools import MusicTools
from music_assistant.domain.audio_profile import ExplanationAnswer, MelodyProfile, ReferenceProfile
from music_assistant.domain.errors import OffTopicRequest
from music_assistant.domain.song_state import SongState
from music_assistant.domain.usage import USAGE_TRACKER, UsageTracker
from music_assistant.ports.llm import ChatModel
from music_assistant.ports.reference_store import ReferenceStore
from music_assistant.ports.song_researcher import SongResearcher
from music_assistant.ports.songsterr_tab_store import SongsterrTabStore


Intent = Literal[
    "answer_reference",
    "research_song",
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
    conversation_context: Optional[str] = Field(default=None, max_length=1600)
    current_song: Optional[SongState] = None


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


class ChordChartRow(BaseModel):
    label: str
    chords: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)


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
    reference_label: Optional[str] = None
    answer: Optional[ExplanationAnswer] = None
    chord_chart: list[ChordChartRow] = Field(default_factory=list)
    melody_preview: Optional[MelodyProfile] = None
    tab_excerpt: Optional[TabExcerptToolOutput] = None
    compose: Optional[ChatComposeResult] = None
    clarification: Optional[str] = None
    usage: Optional[UsageInfo] = None
    error: Optional[dict[str, Any]] = None


_COMPOSE_RE = re.compile(
    r"\b(compose|generate|make|write|create|sketch|produce|compon[eé]|componer|gener[aá]|generar|cre[aá]|crear)\b",
    re.IGNORECASE,
)
_REFERENCE_TOPIC_RE = re.compile(
    r"\b(chord|chords|tempo|bpm|key|energy|section|sections|chorus|verse|analysis|analyze|profile|progression|harmony|harmonic"
    # deep-listening vocabulary — route these to the evidence-backed answer path
    r"|swing|swings|swung|groove|syncopated|syncopation|shuffle|feel|build|builds|drop|drops|dynamics|loudness"
    r"|timbre|bright|dark|warm|noisy|sound|sounds|arrangement|instrument|instruments|tab|tabs|melody|melodic|riff|solo|lead"
    r"|acorde|acordes|tonalidad|energ[ií]a|secci[oó]n|secciones|coro|estrofa|ritmo|bater[ií]a|bajo|guitarra|teclado|piano|melod[ií]a|fraseo|instrumentos|estructura)\b",
    re.IGNORECASE,
)
_RESEARCH_RE = re.compile(r"\b(research|look\s*up|search|buscar|busc[aá])\b", re.IGNORECASE)
_RESEARCH_PREFIX_RE = re.compile(
    r"^\s*(please\s+)?(can\s+you\s+)?(research|look\s*up|search|buscar|busc[aá])"
    r"(\s+(in|on)\s+(the\s+)?(web|internet))?"
    r"(\s+(for|about|and\s+analyze|sobre))?\s*",
    re.IGNORECASE,
)
_GETTING_STARTED_RE = re.compile(
    r"\b(what\s+can\s+you\s+(do|help)|how\s+(can|do)\s+(you|i)\s+(use|start)|help|"
    r"what\s+do\s+you\s+do|qu[eé]\s+(pod[eé]s|puedes)\s+hacer|c[oó]mo\s+(uso|empiezo)|ayuda)\b",
    re.IGNORECASE,
)
_REFERENCE_GUIDE_RE = re.compile(
    r"\b(like\s+this|like\s+the\s+(reference|song|track)|based\s+on\s+(this|the\s+(reference|song|track))|using\s+(this|the)\s+(reference|song|track)|inspired\s+by\s+(this|the\s+(reference|song|track))|same\s+(vibe|feel|energy)|in\s+this\s+style"
    r"|como\s+(esta|ésta|la)\s+(referencia|canci[oó]n|tema)|basad[oa]\s+en\s+(esta|la)\s+(referencia|canci[oó]n|tema)|usando\s+(esta|la)\s+(referencia|canci[oó]n|tema)|con\s+la\s+misma\s+(energ[ií]a|onda|vibra|estilo)|en\s+este\s+estilo)\b",
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
        enable_web_research: bool = True,
    ) -> None:
        self.compose_song = compose_song
        self.answer_music_question = answer_music_question
        self.reference_store = reference_store
        self.chat_model = chat_model
        self.song_researcher = song_researcher
        self.songsterr_tab_store = songsterr_tab_store
        self.enable_web_research = enable_web_research

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
        if request.current_song is not None and _looks_like_song_edit(message):
            return self._revise_current_song(message, request.current_song)
        profile = (
            self.reference_store.get(request.reference_id)
            if request.reference_id
            else None
        )
        profiles = _profiles_from_request(request, self.reference_store)
        if profile is None and profiles:
            profile = profiles[0]

        if self.chat_model is None and _GETTING_STARTED_RE.search(message):
            return _getting_started_response(message)

        intent = self._classify(message, has_reference=profile is not None)
        if intent == "research_song":
            return self._execute_deterministic_intent(intent, message, profile)
        if profile is not None and intent == "answer_reference" and _should_answer_reference_locally(message, profiles):
            return self._execute_deterministic_intent(intent, message, profile)

        if self.chat_model is not None:
            try:
                return self._handle_with_llm_tools(request, message, profile, profiles)
            except Exception:
                if profile is not None:
                    return self._execute_deterministic_intent(intent, message, profile)
                raise

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
            enable_web_research=self.enable_web_research,
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
        tab_excerpt = output if isinstance(output, TabExcerptToolOutput) else None
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
        if output is not None and output.error and output.intent == "clarify":
            message = output.answer or output.error
            return ChatResponse(
                intent="clarify",
                reply=message,
                reference_id=output.reference_id,
                clarification=message,
                error={"code": output.error, "message": message},
            )
        reference_id = agent_result.reference_id
        reference_label = None
        if reference_id:
            profile = self.reference_store.get(reference_id)
            if profile is not None:
                reference_label = _reference_label(profile)
        return ChatResponse(
            intent=agent_result.intent,  # type: ignore[arg-type]
            reply=agent_result.reply,
            reference_id=reference_id,
            reference_label=reference_label,
            answer=answer,
            tab_excerpt=tab_excerpt,
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
            if _looks_like_named_song_analysis(message):
                return ChatResponse(
                    intent="clarify",
                    reply=(
                        "Subí un audio para analizarlo localmente. Si querés buscar datos web "
                        "sobre esa canción, escribí search/research con el título y artista."
                    ),
                    clarification="Subí audio local o pedí search/research explícitamente.",
                )
            return ChatResponse(
                intent="clarify",
                reply=(
                    "I can analyze an attached file, answer about a reference you already shared, "
                    "or compose a new sketch. What would you like?"
                ),
                clarification="Tell me whether to analyze, answer about the current reference, or compose.",
            )

        if intent == "research_song":
            if not self.enable_web_research:
                return _web_research_disabled_response(message)
            if self.song_researcher is None:
                return ChatResponse(
                    intent="clarify",
                    reply=(
                        "Web research is not configured on this server, so I cannot look that up. "
                        "You can still upload the audio file for analysis."
                    ),
                    clarification="Configure song research or attach an audio file instead.",
                )
            query = _RESEARCH_PREFIX_RE.sub("", message).strip() or message
            researched = self.song_researcher.research(query)
            self.reference_store.save(researched)
            return ChatResponse(
                intent="answer_reference",
                reply=_research_ready_reply(researched),
                reference_id=researched.reference_id,
                reference_label=_reference_label(researched),
            )

        if intent == "answer_reference":
            assert profile is not None
            answer = self.answer_music_question.execute(message, profile)
            return ChatResponse(
                intent="answer_reference",
                reply=answer.answer,
                reference_id=profile.reference_id,
                reference_label=_reference_label(profile),
                answer=answer,
                chord_chart=_chord_chart(profile) if _is_chord_question(message) else [],
                melody_preview=_melody_preview(profile) if _is_melody_question(message) else None,
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
        except ComposeConfigurationError as exc:
            return _compose_unavailable_response(exc.code, user_message=style)
        return ChatResponse(
            intent="compose",
            reply=_compose_reply(song, source, spanish=is_spanish(style)),
            compose=ChatComposeResult(song=song, source=source, warnings=_composition_warnings(song)),
        )

    def _revise_current_song(self, message: str, song: SongState) -> ChatResponse:
        match = _target_instrument(song, message)
        if match is None:
            choices = ", ".join(_instrument_label(item) for item in song.roster) or "the generated parts"
            clarification = (
                f"¿Qué instrumento generado querés revisar? Instrumentos disponibles: {choices}."
                if is_spanish(message)
                else f"Which generated instrument should I revise? Available instruments: {choices}."
            )
            return ChatResponse(intent="clarify", reply=clarification, clarification=clarification)
        try:
            revised, source = self.compose_song.revise_instrument(song, message, match.id)
        except OffTopicRequest as refusal:
            return _off_topic_response(refusal)
        except ComposeConfigurationError as exc:
            return _compose_unavailable_response(exc.code, user_message=message)
        return ChatResponse(
            intent="compose",
            reply=(f"Actualicé la parte de {match.instrument} y preservé el resto del arreglo."
                   if is_spanish(message)
                   else f"Updated the {match.instrument} part while preserving the rest of the arrangement."),
            compose=ChatComposeResult(song=revised, source=source, warnings=_composition_warnings(revised)),
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
        except ComposeConfigurationError as exc:
            return _compose_unavailable_response(exc.code, reference_id=profiles[0].reference_id, user_message=message)
        return ChatResponse(
            intent="compose_from_reference",
            reply=_compose_reply(song, source, reference=profiles[0], spanish=is_spanish(message)),
            reference_id=profiles[0].reference_id,
            reference_label=_reference_label(profiles[0]),
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
                    reference_label=_reference_label(profile),
                )
            if built.brief is not None:
                try:
                    song, source = self.compose_song.compose(built.brief)
                except OffTopicRequest as refusal:
                    return _off_topic_response(refusal)
                except ComposeConfigurationError as exc:
                    return _compose_unavailable_response(exc.code, reference_id=profile.reference_id, user_message=message)
                return ChatResponse(
                    intent="compose_from_reference",
                    reply=_compose_reply(song, source, reference=profile, spanish=is_spanish(message)),
                    reference_id=profile.reference_id,
                    reference_label=_reference_label(profile),
                    compose=ChatComposeResult(song=song, source=source, warnings=_composition_warnings(song)),
                )

        style = _style_with_reference(message, profile)
        try:
            song, source = self.compose_song.compose(style)
        except OffTopicRequest as refusal:
            return _off_topic_response(refusal)
        except ComposeConfigurationError as exc:
            return _compose_unavailable_response(exc.code, reference_id=profile.reference_id, user_message=message)
        return ChatResponse(
            intent="compose_from_reference",
            reply=_compose_reply(song, source, reference=profile, spanish=is_spanish(message)),
            reference_id=profile.reference_id,
            reference_label=_reference_label(profile),
            compose=ChatComposeResult(song=song, source=source, warnings=_composition_warnings(song)),
        )

    def _classify(self, message: str, *, has_reference: bool) -> Intent:
        if not message:
            return "clarify"

        # Research is deterministic (no LLM needed) — check it before topic
        # words so "look up and analyze X" researches instead of answering
        # from whatever reference happens to be loaded.
        if _RESEARCH_RE.search(message):
            return "research_song"

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
            # A current reference is conversation state. Natural question-shaped
            # follow-ups query it deterministically instead of asking the LLM to
            # rediscover which freshly researched song the user means.
            if "?" in message or _LOCAL_REFERENCE_QUESTION_RE.search(message):
                return "answer_reference"
            return "clarify"

        if wants_compose:
            return "compose"
        if asks_about_reference:
            return "clarify"
        return "compose"


def _off_topic_response(refusal: OffTopicRequest) -> ChatResponse:
    return ChatResponse(intent="off_topic", reply=refusal.message)


def _getting_started_response(message: str) -> ChatResponse:
    reply = (
        "Puedo ayudarte a componer un boceto, explicar teoría musical y buscar información musical "
        "cuando habilites la búsqueda web. Para generar con IA, configurá un proveedor LLM opcional; "
        "mientras tanto probá: “componé un groove funk de 8 compases”."
        if is_spanish(message)
        else "I can help you compose a sketch, explain music theory, and research music when web research is enabled. "
        "Configure an optional LLM provider for AI generation; meanwhile try: “compose an 8-bar funk groove.”"
    )
    return ChatResponse(intent="clarify", reply=reply, clarification=reply)


def _compose_unavailable_response(
    code: str, *, reference_id: str | None = None, user_message: str = ""
) -> ChatResponse:
    message = (
        "No pude componer porque el proveedor LLM no está disponible."
        if is_spanish(user_message)
        else "I could not compose because the LLM provider is unavailable."
    )
    return ChatResponse(
        intent="clarify",
        reply=message,
        reference_id=reference_id,
        clarification=message,
        error={"code": code, "message": message},
    )


def _web_research_disabled_response(user_message: str = "") -> ChatResponse:
    message = (
        "Pediste una búsqueda de canción, pero la búsqueda web está desactivada. "
        "Configurá ENABLE_WEB_RESEARCH=true y reiniciá la aplicación."
        if is_spanish(user_message)
        else "You asked me to research a song, but web research is disabled. "
        "Set ENABLE_WEB_RESEARCH=true and restart the application."
    )
    return ChatResponse(
        intent="clarify",
        reply=message,
        clarification=message,
        error={"code": "web_research_disabled", "message": message},
    )


def _compose_reply(
    song: SongState, source: str, *, reference: Optional[ReferenceProfile] = None, spanish: bool = False
) -> str:
    header = song.header
    base = (
        f"Generé un boceto de {header.genre} a {header.tempo_bpm} BPM en {header.key} "
        f"({len(song.roster)} instrumentos, fuente={source})."
        if spanish
        else f"Generated a {header.genre} sketch at {header.tempo_bpm} BPM in {header.key} "
        f"({len(song.roster)} instruments, source={source})."
    )
    if reference is not None:
        base += (
            f" Usé {reference.source.label} como guía de estilo."
            if spanish else f" Used reference {reference.source.label} as style guide."
        )
    warnings = _composition_warnings(song)
    if warnings:
        base += (
            f" Se generó con fallas parciales: {'; '.join(warnings)}."
            if spanish else f" Generated with partial failures: {'; '.join(warnings)}."
        )
    return base


def _reference_label(profile: ReferenceProfile) -> str:
    if profile.knowledge is not None:
        artist = profile.knowledge.identity.artist
        title = profile.knowledge.identity.title
        return f"{title} by {artist}" if artist else title
    return profile.source.label


def _research_ready_reply(profile: ReferenceProfile) -> str:
    bits: list[str] = []
    if profile.summary:
        bits.append(profile.summary)
    audio = profile.audio
    if audio is not None:
        facts = []
        if audio.tempo_bpm is not None:
            facts.append(f"tempo {audio.tempo_bpm:g} BPM")
        if audio.key:
            facts.append(f"key {audio.key}")
        if facts:
            bits.append("Found " + ", ".join(facts) + ".")
    if profile.knowledge is not None:
        instruments = []
        for claim in profile.knowledge.evidence_claims:
            if claim.claim_type in {"instrumentation", "tab"} and claim.source_name == "Songsterr":
                instruments.append(claim.value)
        if instruments:
            bits.append("Songsterr evidence: " + "; ".join(instruments[:3]) + ".")
    return " ".join(bits) or "Research ready from source-backed evidence."


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


def _is_chord_question(message: str) -> bool:
    return bool(re.search(r"\b(chord|chords|progression|harmony|harmonic|acorde|acordes|progresi[oó]n|armon[ií]a)\b", message, re.IGNORECASE))



def _is_melody_question(message: str) -> bool:
    return bool(re.search(r"\b(melody|melodic|riff|solo|lead|melod[ií]a|fraseo)\b", message, re.IGNORECASE))


def _melody_preview(profile: ReferenceProfile) -> MelodyProfile | None:
    melody = profile.audio.melody if profile.audio else None
    return melody if melody is not None and melody.note_count else None


def _chord_chart(profile: ReferenceProfile) -> list[ChordChartRow]:
    audio = profile.audio
    if audio is None:
        return []
    return [
        ChordChartRow(
            label=f"{estimate.start_seconds:g}-{estimate.end_seconds:g}s",
            chords=estimate.chords,
            confidence=estimate.confidence,
        )
        for estimate in audio.chord_estimates[:4]
        if estimate.chords
    ]


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


_LOCAL_REFERENCE_QUESTION_RE = re.compile(
    r"^\s*(what|where|when|why|how|does|do|is|are|can|tell me|show me|decime|dime|mostrame|cu[aá]l|d[oó]nde|por qu[eé]|c[oó]mo|qu[eé])\b",
    re.IGNORECASE,
)

_SONG_EDIT_RE = re.compile(
    r"\b(make|regenerate|revise|modify|change|update|edit|less|more|busier|quieter|louder|faster|slower"
    r"|hac[eé]|rehac[eé]|regener[aá]|revis[aá]|modific[aá]|cambi[aá]|actualiz[aá]|edit[aá]"
    r"|menos|m[aá]s|r[aá]pido|lento)\b",
    re.IGNORECASE,
)


def _should_answer_reference_locally(message: str, profiles: list[ReferenceProfile]) -> bool:
    if len(profiles) > 1:
        return False
    return bool("?" in message or _LOCAL_REFERENCE_QUESTION_RE.search(message))


def _looks_like_named_song_analysis(message: str) -> bool:
    normalized = message.strip().lower()
    return bool(
        re.search(r"\banaly[sz]e\b", normalized)
        and not re.search(r"\b(this|attached|file|audio|upload|archivo|adjunto|este audio)\b", normalized)
    )


def _looks_like_song_edit(message: str) -> bool:
    return bool(_SONG_EDIT_RE.search(message))


def _instrument_label(item) -> str:
    return item.instrument or item.id


def _target_instrument(song: SongState, message: str):
    normalized = message.lower()
    scored_matches = []
    for item in song.roster:
        if item.id not in song.parts:
            continue
        candidates = {
            item.id.lower(),
            item.instrument.lower(),
            item.role.lower(),
        }
        if "guitar" in item.instrument.lower() or "guitar" in item.id.lower():
            candidates.add("guitar")
        if "bass" in item.instrument.lower() or "bass" in item.id.lower():
            candidates.update({"bass", "bajo"})
        if item.is_drum or "drum" in item.instrument.lower() or "drum" in item.id.lower():
            candidates.update({"drum", "drums", "batería", "bateria", "percusión", "percusion"})
        if "guitar" in item.instrument.lower() or "guitar" in item.id.lower():
            candidates.add("guitarra")
        if "piano" in item.instrument.lower() or "piano" in item.id.lower():
            candidates.add("piano")
        matched = any(candidate and re.search(rf"\b{re.escape(candidate)}\b", normalized) for candidate in candidates)
        score = 1 if matched else 0
        score += _guitar_edit_specificity_score(item, normalized)
        if score > 0:
            scored_matches.append((score, item))
    if not scored_matches:
        return None
    top_score = max(score for score, _item in scored_matches)
    top = [item for score, item in scored_matches if score == top_score]
    return top[0] if len(top) == 1 else None


def _guitar_edit_specificity_score(item, normalized_message: str) -> int:
    item_text = f"{item.id} {item.instrument} {item.role} {item.playing_style}".lower()
    if "guitar" not in item_text:
        return 0
    score = 0
    if "hard rock guitar" in normalized_message:
        if any(token in item_text for token in ["overdriven", "distort", "lead", "hard rock", "heavy"]):
            score += 4
        else:
            score -= 1
    if any(token in normalized_message for token in ["distorted", "distortion", "overdriven", "overdrive", "heavy"]):
        if any(token in item_text for token in ["overdriven", "distort", "lead", "heavy"]):
            score += 3
    if "lead guitar" in normalized_message:
        if any(token in item_text for token in ["lead", "melody", "hook", "solo"]):
            score += 3
    if "rhythm guitar" in normalized_message:
        if any(token in item_text for token in ["rhythm", "riff", "harmonic", "chord"]):
            score += 3
    return score


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
