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
from music_assistant.music.theory import chord_tone_names
from music_assistant.ports.reference_store import ReferenceStore


Intent = Literal[
    "answer_reference",
    "song_question",
    "edit_song",
    "playable_chords",
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


class PlayableChord(BaseModel):
    chord: str
    notes: list[str] = Field(default_factory=list)
    midi_notes: list[int] = Field(default_factory=list)


class PlayableChordSection(BaseModel):
    name: str
    chords: list[PlayableChord] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)


class PlayableChords(BaseModel):
    instrument: Literal["piano", "guitar"]
    source_label: str
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    sections: list[PlayableChordSection] = Field(default_factory=list)


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
    playable_chords: Optional[PlayableChords] = None
    clarification: Optional[str] = None
    usage: Optional[UsageInfo] = None


_COMPOSE_RE = re.compile(r"\b(compose|generate|make|write|create|sketch|produce)\b", re.IGNORECASE)
_REFERENCE_TOPIC_RE = re.compile(
    r"\b(chord|chords|tempo|bpm|key|energy|section|sections|chorus|verse|analysis|analyze|profile|progression|harmony|harmonic)\b",
    re.IGNORECASE,
)
_PLAYABLE_CHORDS_RE = re.compile(
    r"\b(show|display|play|teach|visuali[sz]e|ver|mostrar|mostrame|ense[nñ]ar|ense[nñ]ame)\b.*"
    r"\b(chords?|acordes?|them|these|those|eso|esos|estas|estos)\b.*"
    r"\b(piano|keyboard|keys|guitar|guitarra)\b"
    r"|"
    r"\b(piano|keyboard|keys|guitar|guitarra)\b.*"
    r"\b(chords?|acordes?)\b",
    re.IGNORECASE,
)
_GUITAR_WORD_RE = re.compile(r"\b(guitar|guitarra)\b", re.IGNORECASE)
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
    r"transpon[eé]|pon[eé]le?|agreg[aá](?:le|me)?|a[ñn]ad[ií](?:le|r)?|"
    r"sum[aá](?:le|me)?|mete(?:le)?|replace|change|swap|remove|drop|raise|"
    r"lower|transpose|mute|add|insert)\b"
    r"|\b(convert[ií]|conviert[ea]|transform[aá]|volv[eé](?:le)?)\b"
    # "hace que X sea/sean Y", "haz que…" — imperative hacer only counts as
    # an edit when followed by "que" (bare "haceme una canción" composes).
    r"|\bha(?:c[eé](?:me)?|z)\s+que\b"
    r"|\bmake\s+(?:all|every|the|it|them)\b|\bturn\b[^.?!]*\binto\b"
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

        if intent == "playable_chords":
            assert profile is not None
            instrument: Literal["piano", "guitar"] = (
                "guitar" if _GUITAR_WORD_RE.search(message) else "piano"
            )
            playable = _build_playable_chords(profile, instrument)
            if playable is None:
                return ChatResponse(
                    intent="answer_reference",
                    reply="I do not have section chord evidence to show on an instrument yet.",
                    reference_id=profile.reference_id,
                )
            reply = (
                f"Here are the section chords from {profile.source.label} as simple piano shapes."
                if instrument == "piano"
                else (
                    f"Here are the section chords from {profile.source.label} as guitar chord names. "
                    "Ask for tab if you want a source-specific riff excerpt."
                )
            )
            return ChatResponse(
                intent="playable_chords",
                reply=reply,
                reference_id=profile.reference_id,
                playable_chords=playable,
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
        """General music Q&A — delegates to band_agent (which owns the LLM
        access; application/ must not import infrastructure/)."""
        from music_assistant.band_agent.tools.web_answer import answer_from_websearch

        answer = answer_from_websearch(message)
        if not answer:
            return ChatResponse(
                intent="song_question",
                reply=(
                    "No encontré resultados web para responder eso. Probá "
                    "reformular la pregunta con el nombre completo del artista "
                    "o la canción."
                ),
            )
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
            if _PLAYABLE_CHORDS_RE.search(message):
                return "playable_chords"
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
        # Ambiguous zone — no compose verb, no recognized question. The old
        # behaviour defaulted to compose, which orchestrated a whole band for
        # "quién es Freddy Mercury?". Let a small LLM decide; if it's down,
        # keep the old default.
        from music_assistant.band_agent.tools.intent_router import route_intent

        routed = route_intent(message, has_previous=has_previous)
        if routed in ("compose", "song_question", "edit_song", "clarify"):
            return routed  # type: ignore[return-value]
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


def _build_playable_chords(
    profile: ReferenceProfile,
    instrument: Literal["piano", "guitar"],
) -> PlayableChords | None:
    sections = _chord_sections(profile)
    if not sections:
        return None
    playable_sections = [
        PlayableChordSection(
            name=name,
            confidence=confidence,
            chords=[
                PlayableChord(
                    chord=chord,
                    notes=list(chord_tone_names(chord)),
                    midi_notes=_piano_midi_notes(chord) if instrument == "piano" else [],
                )
                for chord in chords
                if chord and chord.upper() != "N.C."
            ],
        )
        for name, chords, confidence in sections
    ]
    playable_sections = [section for section in playable_sections if section.chords]
    if not playable_sections:
        return None
    confidence = max(section.confidence for section in playable_sections)
    return PlayableChords(
        instrument=instrument,
        source_label=profile.source.label,
        confidence=confidence,
        sections=playable_sections[:8],
    )


def _chord_sections(profile: ReferenceProfile) -> list[tuple[str, list[str], float]]:
    audio = profile.audio
    if audio and audio.structure and audio.structure.sections:
        out = [
            (
                section.label,
                _dedupe_chords(section.main_progression),
                section.confidence,
            )
            for section in audio.structure.sections
            if section.main_progression
        ]
        if out:
            return out

    harmony = audio.harmony if audio else None
    if harmony and harmony.progressions:
        out = [
            (
                f"bars {progression.start_bar}-{progression.end_bar}",
                _dedupe_chords(progression.chords),
                progression.confidence,
            )
            for progression in harmony.progressions
            if progression.chords
        ]
        if out:
            return out

    if harmony and harmony.chord_spans:
        spans = [span for span in harmony.chord_spans if span.chosen is not None]
        if spans:
            return [
                (
                    "bar-level chords",
                    _dedupe_chords([span.chosen.label for span in spans if span.chosen]),
                    max((span.confidence for span in spans), default=0.0),
                )
            ]

    evidence_sections: list[tuple[str, list[str], float]] = []
    for item in profile.research_evidence:
        if item.claim_type != "chord_progression":
            continue
        chords = _chords_from_progression_text(item.value)
        if not chords:
            continue
        label = _section_label_from_evidence(item.value, item.snippet) or "song"
        evidence_sections.append((label, chords, item.confidence))
    return evidence_sections


def _dedupe_chords(chords: list[str]) -> list[str]:
    out: list[str] = []
    for chord in chords:
        clean = _clean_chord_token(chord)
        if clean and clean not in out:
            out.append(clean)
    return out


def _chords_from_progression_text(value: str) -> list[str]:
    raw = value.replace("|", " ").replace("-", " ")
    return _dedupe_chords(raw.split())


def _section_label_from_evidence(value: str, snippet: str) -> str:
    for text in (snippet, value):
        if ":" in text:
            before = text.split(":", 1)[0].strip()
            if 0 < len(before) <= 32 and not _looks_like_chord(before):
                return before
    return ""


_CHORD_TOKEN_RE = re.compile(
    r"^[A-G](?:#|b)?(?:m|min|maj|dim|aug|sus|add)?\d*(?:/[A-G](?:#|b)?)?$",
    re.IGNORECASE,
)


def _looks_like_chord(value: str) -> bool:
    return bool(_CHORD_TOKEN_RE.match(value.strip()))


def _clean_chord_token(value: str) -> str:
    token = value.strip().strip(".,;:()[]{}")
    return token if _looks_like_chord(token) else ""


_NOTE_TO_PC = {
    "C": 0,
    "C#": 1,
    "Db": 1,
    "D": 2,
    "D#": 3,
    "Eb": 3,
    "E": 4,
    "F": 5,
    "F#": 6,
    "Gb": 6,
    "G": 7,
    "G#": 8,
    "Ab": 8,
    "A": 9,
    "A#": 10,
    "Bb": 10,
    "B": 11,
}


def _piano_midi_notes(chord: str) -> list[int]:
    tones = chord_tone_names(chord)
    if not tones:
        return []
    pcs = [_NOTE_TO_PC.get(tone) for tone in tones]
    if any(pc is None for pc in pcs):
        return []
    root_pc = int(pcs[0])
    root = 48 + root_pc if root_pc >= 9 else 60 + root_pc
    notes = [root]
    previous = root
    for pc_value in pcs[1:]:
        pitch = 48 + int(pc_value)
        while pitch <= previous:
            pitch += 12
        notes.append(pitch)
        previous = pitch
    return notes
