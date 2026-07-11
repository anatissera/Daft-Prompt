"""Conversational orchestrator that routes chat intents to existing use cases.

The orchestrator picks one intent per turn — analyze, answer over a stored
ReferenceProfile, compose from scratch, compose from reference, or ask a single
clarification — and delegates to the application services that already exist.
It never touches HTTP, MIR libraries, or LLM clients directly.
"""

from __future__ import annotations

import json
import re
import time
from typing import Literal, Optional

from pydantic import BaseModel, Field

from music_assistant.application.answer_music_question import AnswerMusicQuestion, MusicQuestionExplainer
from music_assistant.application.compose_song import ComposeSong
from music_assistant.domain.audio_profile import ExplanationAnswer, ReferenceProfile
from music_assistant.domain.errors import OffTopicRequest
from music_assistant.domain.song_state import SongState
from music_assistant.domain.usage import USAGE_TRACKER, UsageTracker
from music_assistant.ports.reference_store import ReferenceStore


Intent = Literal[
    "answer_reference",
    "song_question",
    "edit_song",
    "compose",
    "compose_from_reference",
    "clarify",
    "off_topic",
]


class ChatRequest(BaseModel):
    message: str = Field(min_length=1)
    reference_id: Optional[str] = None
    # job_id of the last composed song in this chat — enables edit intents
    # ("swap the piano for a rhodes") to load and modify it.
    edit_job_id: Optional[str] = None


class ChatArtifacts(BaseModel):
    midi: str
    musicxml: str


class ChatComposeResult(BaseModel):
    song: SongState
    source: str
    artifacts: Optional[ChatArtifacts] = None


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


_COMPOSE_RE = re.compile(r"\b(compose|generate|make|write|create|sketch|produce)\b", re.IGNORECASE)
_REFERENCE_TOPIC_RE = re.compile(
    r"\b(chord|chords|tempo|bpm|key|energy|section|sections|chorus|verse|analysis|analyze|profile|progression|harmony|harmonic)\b",
    re.IGNORECASE,
)
# A QUESTION about a known song ("which chords does Something by The
# Beatles got?", "¿qué acordes tiene X?") must be ANSWERED, not turned into
# a composition — compose used to be the unconditional default. Requires an
# interrogative shape AND a music-info topic so plain style prompts
# ("something dark and heavy") don't get hijacked.
# Iteration on the PREVIOUS output: "cambiale el piano", "subí el pitch",
# "sacá los vientos", "más lento". Only meaningful when the frontend sent
# the last job id (has_previous). Explicit new-song words opt out.
_EDIT_VERB_RE = re.compile(
    r"\b(cambi[aá](?:le|me)?|reemplaz[aá]|remplaz[aá]|sac[aá](?:le|me)?|"
    r"quit[aá](?:le|me)?|elimin[aá]|sub[ií](?:le|r)?|baj[aá](?:le|r)?|"
    r"transpon[eé]|pon[eé]le?|replace|change|swap|remove|drop|raise|lower|"
    r"transpose|mute)\b"
    r"|\bm[aá]s\s+(r[aá]pid[oa]|lent[oa]|fuerte|suave|agud[oa]|grave)\b"
    r"|\b(faster|slower|louder|quieter|higher|lower)\b",
    re.IGNORECASE,
)
_NEW_SONG_RE = re.compile(
    r"\b(otra|another|nueva?|new song|from scratch|de cero|desde cero)\b",
    re.IGNORECASE,
)

_QUESTION_SHAPE_RE = re.compile(
    r"\?|^\s*(which|what|who|when|where|how|does|do|is|are|can you tell|"
    r"qu[eé]\b|cu[aá]l(?:es)?|qui[eé]n(?:es)?|c[oó]mo|cu[aá]ndo|d[oó]nde|"
    r"tiene[ns]?\b|sab[eé]s)\b",
    re.IGNORECASE,
)
_SONG_INFO_TOPIC_RE = re.compile(
    r"\b(chords?|cords?|acordes?|key|tonalidad|tono|tempo|bpm|scale|escala|"
    r"progression|progresi[oó]n|meter|comp[aá]s|lyrics?|letra|se(?:cc|ct)ions?|"
    r"verse|chorus|estribillo|album|[aá]lbum|year|a[nñ]o|genre|g[eé]nero|"
    r"artists?|artistas?|bands?|bandas?|singers?|cantantes?|canta|sings?|"
    r"toca|plays|m[uú]sic[ao]|song|canci[oó]n|discograf[ií]a|discography|"
    r"influences?|influencias?|estilo|style)\b",
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
            try:
                song, source = self.compose_song.compose(style)
            except OffTopicRequest as refusal:
                return _off_topic_response(refusal)
            return ChatResponse(
                intent="compose_from_reference",
                reply=_compose_reply(song, source, reference=profile),
                reference_id=profile.reference_id,
                compose=ChatComposeResult(song=song, source=source),
            )

        if intent == "song_question":
            return self._answer_song_question(message)

        try:
            song, source = self.compose_song.compose(message or "demo")
        except OffTopicRequest as refusal:
            return _off_topic_response(refusal)
        return ChatResponse(
            intent="compose",
            reply=_compose_reply(song, source),
            compose=ChatComposeResult(song=song, source=source),
        )

    def _answer_song_question(self, message: str) -> ChatResponse:
        """Answer a question about a known song from scraped evidence
        (MusicBrainz resolution + chord-site connectors). Deterministic —
        no LLM, no hallucinated chords; when the evidence isn't there we
        say so instead of inventing (or worse, composing)."""
        from music_assistant.band_agent.tools.song_evidence import gather_song_evidence

        evidence = gather_song_evidence(message)
        if not evidence:
            # Not a resolvable song — treat it as a GENERAL music question
            # ("qué género toca tal artista") and answer from a web search.
            return self._answer_from_websearch(message)
        lines = [f"**{evidence['song']}** — {evidence['artist']}"]
        by_type: dict[str, list[dict]] = {}
        for c in evidence["claims"]:
            by_type.setdefault(c["type"], []).append(c)
        for t in ("key", "tempo", "meter"):
            for c in by_type.get(t, [])[:1]:
                lines.append(f"{t.capitalize()}: {c['value']} (via {c['source']})")
        progressions = by_type.get("chord_progression", [])
        if progressions:
            lines.append("Chords:")
            for c in progressions[:6]:
                section = c["section"] or "all"
                lines.append(f"- {section}: {c['value']}")
            sources = sorted({c["source"] for c in progressions})
            lines.append(f"(source: {', '.join(sources)})")
        return ChatResponse(intent="song_question", reply="\n".join(lines))

    def _answer_from_websearch(self, message: str) -> ChatResponse:
        """General music Q&A: DDG search + page excerpts + one small LLM call
        to synthesize an answer grounded in what the pages actually say."""
        from pydantic import BaseModel as _BM

        from music_assistant.band_agent.tools import search_web
        from music_assistant.band_agent.tools.style_research import fetch_style_excerpts
        from music_assistant.infrastructure.llm import make_llm

        hits = search_web(message, decorate=False)
        excerpts = fetch_style_excerpts(hits) if hits else []
        if not hits:
            return ChatResponse(
                intent="song_question",
                reply=(
                    "No encontré resultados web para responder eso. Probá "
                    "reformular la pregunta con el nombre completo del artista "
                    "o la canción."
                ),
            )

        class _WebAnswer(_BM):
            answer: str

        context = {
            "question": message,
            "results": [{"title": h.get("title"), "site": h.get("site")} for h in hits[:6]],
            "excerpts": excerpts,
        }
        prompt = (
            "You answer music questions using ONLY the web evidence below. "
            "Reply in the user's language, in 1-4 sentences. If the evidence "
            "is thin or conflicting, say so explicitly instead of guessing. "
            "Do not invent facts, dates, credits or genres. Return ONLY the "
            "structured object via the tool — no prose outside it.\n\n"
            f"{json.dumps(context, ensure_ascii=False)}"
        )
        answer = ""
        try:
            llm = make_llm(role="director").with_structured_output(_WebAnswer)
            # The parse occasionally returns None on minimax-m3 (same flake
            # the skeleton retries around); a second attempt is cheap.
            for _ in range(2):
                result = llm.invoke(prompt)
                if isinstance(result, _WebAnswer) and result.answer.strip():
                    answer = result.answer.strip()
                    break
        except Exception:
            answer = ""
        if not answer:
            titles = "; ".join(h.get("title", "") for h in hits[:3])
            answer = (
                "No pude sintetizar una respuesta confiable, pero esto es lo "
                f"que encontré: {titles}"
            )
        sources = sorted({h.get("site", "") for h in hits[:4] if h.get("site")})
        if sources:
            answer += f"\n(fuentes: {', '.join(sources)})"
        return ChatResponse(intent="song_question", reply=answer)

    def _classify(
        self, message: str, *, has_reference: bool, has_previous: bool = False
    ) -> Intent:
        if not message:
            return "clarify"

        if (
            has_previous
            and _EDIT_VERB_RE.search(message)
            and not _NEW_SONG_RE.search(message)
        ):
            return "edit_song"

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
        if _QUESTION_SHAPE_RE.search(message) and _SONG_INFO_TOPIC_RE.search(message):
            return "song_question"
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
