"""Question-answering use case over compact reference profiles."""

from __future__ import annotations

import re
from typing import Any, Protocol

from pydantic import BaseModel, Field

from music_assistant.application.profile_queries import answer_from_profile, plain_music_text
from music_assistant.application.language import is_spanish
from music_assistant.domain.audio_profile import (
    ChordSpan,
    ExplanationAnswer,
    ReferenceProfile,
    confidence_label,
)
from music_assistant.ports.llm import ChatModel


class GroundedAnswer(BaseModel):
    answer: str = Field(min_length=1)


class MusicQuestionExplainer(Protocol):
    def answer(self, question: str, profile: ReferenceProfile) -> ExplanationAnswer:
        ...


class AnswerMusicQuestion:
    def __init__(self, explainer: MusicQuestionExplainer | None = None, *, songsterr_tab_store: Any | None = None):
        self.explainer = explainer or DeterministicMusicQuestionExplainer(songsterr_tab_store=songsterr_tab_store)

    def execute(self, question: str, profile: ReferenceProfile) -> ExplanationAnswer:
        answer = self.explainer.answer(question, profile)
        return answer.model_copy(update={"answer": plain_music_text(answer.answer)})


class LLMGroundedMusicQuestionExplainer:
    """Conversational synthesis over deterministic, source-backed evidence."""

    def __init__(self, chat_model: ChatModel, *, songsterr_tab_store: Any | None = None) -> None:
        self.chat_model = chat_model
        self.fallback = DeterministicMusicQuestionExplainer(songsterr_tab_store=songsterr_tab_store)

    def answer(self, question: str, profile: ReferenceProfile) -> ExplanationAnswer:
        evidence_answer = self.fallback.answer(question, profile)
        if not evidence_answer.evidence:
            return evidence_answer
        identity = profile.knowledge.identity if profile.knowledge is not None else None
        label = (
            " — ".join(part for part in [identity.title, identity.artist] if part)
            if identity is not None
            else profile.source.label
        )
        messages = [
            {
                "role": "system",
                "content": (
                    "You are LLMinem's user-facing musical responder. Answer naturally in the same language "
                    "as the user. Use only the supplied source-backed evidence. Do not mention internal profiles, "
                    "routing, missing fields, tools, or diagnostics. State uncertainty for estimated musical facts. "
                    "Be concise and directly answer the question. Never invent chords, keys, instruments, sections, "
                    "credits, or sources."
                ),
            },
            {"role": "system", "content": f"Current song: {label}"},
            {"role": "system", "content": "Evidence:\n" + "\n".join(evidence_answer.evidence[:12])},
            {"role": "system", "content": f"Deterministic evidence summary: {evidence_answer.answer}"},
            {"role": "user", "content": question},
        ]
        try:
            synthesized = self.chat_model.with_structured_output(GroundedAnswer).invoke(messages)
        except Exception:
            return evidence_answer
        return evidence_answer.model_copy(update={"answer": plain_music_text(synthesized.answer)})


class DeterministicMusicQuestionExplainer:
    def __init__(self, *, songsterr_tab_store: Any | None = None) -> None:
        self.songsterr_tab_store = songsterr_tab_store

    def answer(self, question: str, profile: ReferenceProfile) -> ExplanationAnswer:
        spanish = is_spanish(question)
        tab_answer = self._answer_from_songsterr_tabs(question, profile, spanish=spanish)
        if tab_answer is not None:
            return tab_answer

        normalized = question.lower()
        # Knowledge-profile answers normally take precedence, but audio
        # transcription is the direct evidence for a local melody/riff query.
        if re.search(r"\b(melody|melodic|riff|solo|lead|melod[ií]a|fraseo)\b", normalized):
            return _answer_melody(profile, spanish=spanish)

        if profile.knowledge is not None:
            answer = answer_from_profile(question, profile.knowledge)
            return ExplanationAnswer(
                reference_id=profile.reference_id,
                answer=answer.answer,
                evidence=answer.evidence,
            )

        audio = profile.audio
        if audio is None:
            return ExplanationAnswer(
                reference_id=profile.reference_id,
                answer=("Todavía no tengo un perfil de audio para esta referencia." if spanish
                        else "I do not have an audio profile for this reference yet."),
                evidence=[],
            )

        normalized = question.lower()
        if re.search(r"\b(key|tonality|tonal|tonalidad|tono)\b", normalized):
            return _answer_key(profile, spanish=spanish)
        # "chorus"/"verse" are structural terms; keep them out of the chord branch
        # so "where is the chorus" routes to structure, not chord estimates.
        if re.search(r"\b(chord|chords|progression|harmony|harmonic|acorde|acordes|progresi[oó]n|armon[ií]a)\b", normalized):
            return _answer_chords(profile, spanish=spanish)
        if re.search(r"\b(structure|form|section|sections|repeat|a/b/c|abc|verse|chorus|estructura|secci[oó]n|secciones|estrofa|coro)\b", normalized):
            return _answer_structure(profile, spanish=spanish)

        lead = (
            ("La evidencia de acordes y estructura es débil, así que esto es solo un boceto. " if spanish
             else "The chord and structure evidence is weak here, so this is a rough sketch. ")
            if _is_low_usefulness(profile)
            else ""
        )
        return ExplanationAnswer(
            reference_id=profile.reference_id,
            answer=(
                f"{lead}" + (
                    "Puedo responder a partir del análisis actual sobre tonalidad probable, "
                    "acordes estimados, progresiones repetidas y estructura A/B/C."
                    if spanish
                    else "I can answer from the current analysis about likely key, probable chords, "
                    "repeated progressions, and A/B/C structure."
                )
            ),
            evidence=_general_evidence(profile),
        )

    def _answer_from_songsterr_tabs(
        self, question: str, profile: ReferenceProfile, *, spanish: bool
    ) -> ExplanationAnswer | None:
        if self.songsterr_tab_store is None:
            return None
        bundle = self.songsterr_tab_store.get(profile.reference_id)
        if bundle is None:
            return None
        normalized = question.lower()
        asks_tab = any(token in normalized for token in ["tab", "tabs", "tablature", "riff", "solo", "tablatura"])
        asks_instrument = any(
            token in normalized
            for token in ["bass", "drum", "guitar", "piano", "keyboard", "keys", "synth", "sax", "vocal", "voice", "bajo", "batería", "bateria", "guitarra"]
        )
        if not asks_tab and not asks_instrument:
            return None
        if any(token in normalized for token in ["section", "form", "sección", "seccion", "estructura"]):
            sections = _songsterr_tab_sections(bundle)
            if not sections:
                return ExplanationAnswer(
                    reference_id=profile.reference_id,
                    answer=("Todavía no tengo marcadores de sección de Songsterr para esta canción."
                            if spanish else "I do not have section markers from Songsterr for this song yet."),
                    evidence=[],
                )
            return ExplanationAnswer(
                reference_id=profile.reference_id,
                answer=("Secciones de la tablatura de Songsterr: " if spanish else "Songsterr tab sections: ")
                + ", ".join(sections) + ".",
                evidence=[f"songsterr:sections:{len(sections)}"],
            )
        instrument = _mentioned_tab_instrument(normalized)
        if instrument is None:
            return ExplanationAnswer(
                reference_id=profile.reference_id,
                answer=("Hay datos de tablatura de Songsterr para: " if spanish else "Songsterr tab data is loaded for: ")
                + ", ".join(bundle.instrument_names) + ".",
                evidence=[f"songsterr:tracks:{len(bundle.tracks)}"],
            )
        tracks = bundle.tracks_for_instrument(instrument)
        if not tracks:
            return ExplanationAnswer(
                reference_id=profile.reference_id,
                answer=(f"Todavía no tengo datos de Songsterr específicos para {instrument} en esta canción."
                        if spanish else f"I do not have {instrument}-specific Songsterr tab data for this song yet."),
                evidence=[],
            )
        summaries = [_songsterr_track_summary(track) for track in tracks[:3]]
        return ExplanationAnswer(
            reference_id=profile.reference_id,
            answer=" ".join(summaries),
            evidence=[f"songsterr:part:{track.part_id}:measures={len(track.measures)}:notes={track.note_count}" for track in tracks[:3]],
        )


def _answer_key(profile: ReferenceProfile, *, spanish: bool = False) -> ExplanationAnswer:
    audio = profile.audio
    key_profile = audio.harmony.key if audio and audio.harmony else None
    primary = key_profile.primary if key_profile else None
    if primary is None:
        return ExplanationAnswer(
            reference_id=profile.reference_id,
            answer=("Todavía no tengo una estimación tonal confiable para esta referencia."
                    if spanish else "I do not have a reliable key estimate for this reference yet."),
            evidence=[],
        )

    alternatives = [
        f"{candidate.key} ({_percent(candidate.confidence)})"
        for candidate in key_profile.candidates[1:4]
    ]
    alternative_labels = [candidate.key for candidate in key_profile.candidates[1:4]]
    suffix = ((f" Alternativas cercanas: {', '.join(alternatives)}.") if spanish else f" Close alternatives: {', '.join(alternatives)}.") if alternatives else ""
    ambiguity = (" Hay ambigüedad de tonalidad relativa." if spanish else " There is relative-key ambiguity.") if key_profile.relative_key_ambiguity else ""
    if confidence_label(key_profile.confidence) == "low" or key_profile.relative_key_ambiguity:
        candidates = [primary.key, *alternative_labels]
        confidence_sentence = (
            (f"Confianza baja ({_percent(key_profile.confidence)})." if spanish else f"Low confidence ({_percent(key_profile.confidence)}).")
            if confidence_label(key_profile.confidence) == "low"
            else (f"Confianza {_percent(key_profile.confidence)}." if spanish else f"Confidence {_percent(key_profile.confidence)}.")
        )
        return ExplanationAnswer(
            reference_id=profile.reference_id,
            answer=(
                ("El centro tonal es ambiguo; los candidatos cercanos incluyen " if spanish else "Tonal center is ambiguous; close candidates include ")
                + f"{', '.join(candidates)}. {confidence_sentence}"
                f"{suffix}{ambiguity}"
            ),
            evidence=[
                f"Primary key candidate: {primary.key}, confidence {_percent(primary.confidence)}.",
                *[f"Alternative key candidate: {candidate}." for candidate in alternatives],
            ],
        )
    confidence_text = (
        (f"confianza baja ({_percent(key_profile.confidence)})" if spanish else f"low confidence ({_percent(key_profile.confidence)})")
        if confidence_label(key_profile.confidence) == "low"
        else (f"confianza de {_percent(key_profile.confidence)}" if spanish else f"{_percent(key_profile.confidence)} confidence")
    )
    return ExplanationAnswer(
        reference_id=profile.reference_id,
        answer=(
            (f"La tonalidad probablemente es {primary.key}, con {confidence_text}." if spanish
             else f"The key is likely {primary.key} with {confidence_text}.")
            + f"{suffix}{ambiguity}"
        ),
        evidence=[
            f"Primary key candidate: {primary.key}, confidence {_percent(primary.confidence)}.",
            *[f"Alternative key candidate: {candidate}." for candidate in alternatives],
        ],
    )


def _mentioned_tab_instrument(normalized_question: str) -> str | None:
    aliases = [
        ("drums", "drums"),
        ("drum", "drums"),
        ("batería", "drums"),
        ("bateria", "drums"),
        ("bass", "bass"),
        ("bajo", "bass"),
        ("guitar", "guitar"),
        ("guitarra", "guitar"),
        ("piano", "piano"),
        ("keyboard", "piano"),
        ("keys", "piano"),
        ("synth", "piano"),
        ("sax", "sax"),
        ("vocal", "vocal"),
        ("voice", "vocal"),
    ]
    for token, instrument in aliases:
        if token in normalized_question:
            return instrument
    return None


def _songsterr_tab_sections(bundle) -> list[str]:
    sections: list[str] = []
    for track in bundle.tracks:
        for measure in track.measures:
            if measure.marker and measure.marker not in sections:
                sections.append(measure.marker)
    return sections


def _songsterr_track_summary(track) -> str:
    sections = []
    for measure in track.measures:
        if measure.marker and measure.marker not in sections:
            sections.append(measure.marker)
    section_text = ", ".join(sections[:6]) if sections else "no section markers"
    return (
        f"{track.instrument_family.title()} tab loaded from Songsterr: {track.name} "
        f"({len(track.measures)} measures, {track.note_count} note events). "
        f"Sections: {section_text}."
    )


def _answer_melody(profile: ReferenceProfile, *, spanish: bool = False) -> ExplanationAnswer:
    melody = profile.audio.melody if profile.audio else None
    if melody is None or not melody.note_count:
        return ExplanationAnswer(
            reference_id=profile.reference_id,
            answer=(
                "Todavía no tengo una transcripción melódica para esta referencia. "
                "Podés activar la transcripción local opcional y volver a analizar el audio."
                if spanish
                else "I do not have a melodic transcription for this reference yet. "
                "Enable optional local transcription and analyze the audio again."
            ),
            evidence=[],
        )
    register = (
        f"MIDI {melody.pitch_low}-{melody.pitch_high}"
        if melody.pitch_low is not None and melody.pitch_high is not None
        else ("registro no disponible" if spanish else "an unavailable register")
    )
    event_count = len(melody.representative_events)
    answer = (
        f"La transcripción local encontró {melody.note_count} notas melódicas, con un registro de {register} "
        f"y un contorno {melody.contour}. Eso sugiere una frase que "
        f"{'sube' if melody.contour == 'rising' else 'baja' if melody.contour == 'falling' else 'se mueve en ambas direcciones' if melody.contour == 'mixed' else 'se mantiene relativamente estable'}. "
        f"Tomalo como una guía provisional: la transcripción tiene {_percent(melody.confidence)} de confianza y no identifica por sí sola el instrumento."
        if spanish
        else f"Local transcription found {melody.note_count} melodic notes in {register} with a {melody.contour} contour. "
        f"That suggests a phrase that "
        f"{'climbs' if melody.contour == 'rising' else 'falls' if melody.contour == 'falling' else 'moves in both directions' if melody.contour == 'mixed' else 'stays relatively level'}. "
        f"Treat it as a provisional playing guide: transcription confidence is {_percent(melody.confidence)} and it does not identify the instrument by itself."
    )
    return ExplanationAnswer(
        reference_id=profile.reference_id,
        answer=answer,
        evidence=[
            f"Provisional audio transcription: {melody.note_count} notes, {register}, {melody.contour} contour.",
            f"Representative symbolic events retained: {event_count}.",
        ],
    )


def _answer_chords(profile: ReferenceProfile, *, spanish: bool = False) -> ExplanationAnswer:
    audio = profile.audio
    harmony = audio.harmony if audio else None
    if harmony is None:
        return ExplanationAnswer(
            reference_id=profile.reference_id,
            answer=("Todavía no tengo estimaciones de acordes probables para esta referencia."
                    if spanish else "I do not have probable chord estimates for this reference yet."),
            evidence=[],
        )

    main = next((progression for progression in harmony.progressions if progression.chords), None)
    if main is not None:
        progression = " - ".join(main.chords)
        if main.confidence < 0.5:
            return ExplanationAnswer(
                reference_id=profile.reference_id,
                answer=(
                    (f"Candidato débil de ciclo armónico: {progression} entre los compases " if spanish
                     else f"Weak chord loop candidate: {progression} across bars ")
                    + f"{main.start_bar}-{main.end_bar}, "
                    + (f"con {_percent(main.confidence)} de confianza." if spanish else f"with {_percent(main.confidence)} confidence.")
                ),
                evidence=[
                    f"Progression bars {main.start_bar}-{main.end_bar}: {progression}, confidence {_percent(main.confidence)}.",
                    f"Detected repetitions: {main.repetitions}.",
                ],
            )
        return ExplanationAnswer(
            reference_id=profile.reference_id,
            answer=(
                (f"La progresión principal probablemente es {progression} entre los compases " if spanish
                 else f"The main progression is probably {progression} across bars ")
                + f"{main.start_bar}-{main.end_bar}, "
                + (f"con {_percent(main.confidence)} de confianza." if spanish else f"with {_percent(main.confidence)} confidence.")
            ),
            evidence=[
                f"Progression bars {main.start_bar}-{main.end_bar}: {progression}, confidence {_percent(main.confidence)}.",
                f"Detected repetitions: {main.repetitions}.",
            ],
        )

    chosen = [span for span in harmony.chord_spans if span.chosen is not None]
    if not chosen:
        return ExplanationAnswer(
            reference_id=profile.reference_id,
            answer=("Todavía no tengo estimaciones de acordes probables para esta referencia."
                    if spanish else "I do not have probable chord estimates for this reference yet."),
            evidence=[],
        )
    summary = " - ".join(span.chosen.label for span in chosen[:8] if span.chosen)
    return ExplanationAnswer(
        reference_id=profile.reference_id,
        answer=(f"Las estimaciones de acordes más sólidas por compás probablemente son {summary}."
                if spanish else f"The strongest bar-level chord estimates are probably {summary}."),
        evidence=[_span_evidence(span) for span in chosen[:8]],
    )


def _answer_structure(profile: ReferenceProfile, *, spanish: bool = False) -> ExplanationAnswer:
    audio = profile.audio
    structure = audio.structure if audio else None
    if structure is None or not structure.sections:
        return ExplanationAnswer(
            reference_id=profile.reference_id,
            answer=("Todavía no tengo una estimación de estructura A/B/C para esta referencia."
                    if spanish else "I do not have an A/B/C structure estimate for this reference yet."),
            evidence=[],
        )

    form = " / ".join(
        f"{section.label} bars {section.start_bar}-{section.end_bar}"
        for section in structure.sections
    )
    if structure.confidence < 0.4:
        return ExplanationAnswer(
            reference_id=profile.reference_id,
            answer=(
                (f"La estructura no es clara; una lectura A/B/C aproximada y de baja confianza es {form}."
                 if spanish else f"The structure is unclear; an approximate low confidence A/B/C read is {form}.")
            ),
            evidence=[
                (
                    f"Section {section.label}: bars {section.start_bar}-{section.end_bar}, "
                    f"confidence {_percent(section.confidence)}."
                )
                for section in structure.sections
            ],
        )
    return ExplanationAnswer(
        reference_id=profile.reference_id,
        answer=(f"La estructura parece repetirse como {form}." if spanish
                else f"The structure appears to repeat as {form}."),
        evidence=[
            (
                f"Section {section.label}: bars {section.start_bar}-{section.end_bar}, "
                f"confidence {_percent(section.confidence)}."
            )
            for section in structure.sections
        ],
    )


def _general_evidence(profile: ReferenceProfile) -> list[str]:
    evidence: list[str] = []
    audio = profile.audio
    if audio is None:
        return evidence
    if audio.harmony and audio.harmony.key.primary:
        evidence.append(
            f"Likely key: {audio.harmony.key.primary.key}, confidence {_percent(audio.harmony.key.confidence)}."
        )
    if audio.harmony and audio.harmony.progressions:
        progression = audio.harmony.progressions[0]
        evidence.append(
            f"Main progression bars {progression.start_bar}-{progression.end_bar}: {' - '.join(progression.chords)}."
        )
    if audio.structure and audio.structure.sections:
        labels = " / ".join(section.label for section in audio.structure.sections)
        evidence.append(f"A/B/C labels: {labels}.")
    return evidence


def _span_evidence(span: ChordSpan) -> str:
    chosen = span.chosen
    if chosen is None:
        return f"Bars {span.start_bar}-{span.end_bar}: unknown chord."
    return (
        f"Bars {span.start_bar}-{span.end_bar}: {chosen.label}, "
        f"confidence {_percent(chosen.confidence)}."
    )


def _is_low_usefulness(profile: ReferenceProfile) -> bool:
    audio = profile.audio
    if audio is None:
        return False
    return any(note.code == "low_usefulness" for note in audio.analysis_notes)


def _percent(value: float) -> str:
    return f"{round(max(0.0, min(1.0, value)) * 100)}%"
