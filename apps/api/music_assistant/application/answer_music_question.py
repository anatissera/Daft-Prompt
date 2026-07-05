"""Question-answering use case over compact reference profiles."""

from __future__ import annotations

import re
from typing import Any, Protocol

from music_assistant.application.profile_queries import answer_from_profile
from music_assistant.domain.audio_profile import (
    ChordSpan,
    ExplanationAnswer,
    ReferenceProfile,
    confidence_label,
)


class MusicQuestionExplainer(Protocol):
    def answer(self, question: str, profile: ReferenceProfile) -> ExplanationAnswer:
        ...


class AnswerMusicQuestion:
    def __init__(self, explainer: MusicQuestionExplainer | None = None, *, songsterr_tab_store: Any | None = None):
        self.explainer = explainer or DeterministicMusicQuestionExplainer(songsterr_tab_store=songsterr_tab_store)

    def execute(self, question: str, profile: ReferenceProfile) -> ExplanationAnswer:
        return self.explainer.answer(question, profile)


class DeterministicMusicQuestionExplainer:
    def __init__(self, *, songsterr_tab_store: Any | None = None) -> None:
        self.songsterr_tab_store = songsterr_tab_store

    def answer(self, question: str, profile: ReferenceProfile) -> ExplanationAnswer:
        tab_answer = self._answer_from_songsterr_tabs(question, profile)
        if tab_answer is not None:
            return tab_answer

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
                answer="I do not have an audio profile for this reference yet.",
                evidence=[],
            )

        normalized = question.lower()
        if re.search(r"\b(key|tonality|tonal)\b", normalized):
            return _answer_key(profile)
        # "chorus"/"verse" are structural terms; keep them out of the chord branch
        # so "where is the chorus" routes to structure, not chord estimates.
        if re.search(r"\b(chord|chords|progression|harmony|harmonic)\b", normalized):
            return _answer_chords(profile)
        if re.search(r"\b(structure|form|section|sections|repeat|a/b/c|abc|verse|chorus)\b", normalized):
            return _answer_structure(profile)

        lead = (
            "The chord and structure evidence is weak here, so this is a rough "
            "sketch. "
            if _is_low_usefulness(profile)
            else ""
        )
        return ExplanationAnswer(
            reference_id=profile.reference_id,
            answer=(
                f"{lead}I can answer from the current analysis about likely key, "
                "probable chords, repeated progressions, and A/B/C structure."
            ),
            evidence=_general_evidence(profile),
        )

    def _answer_from_songsterr_tabs(self, question: str, profile: ReferenceProfile) -> ExplanationAnswer | None:
        if self.songsterr_tab_store is None:
            return None
        bundle = self.songsterr_tab_store.get(profile.reference_id)
        if bundle is None:
            return None
        normalized = question.lower()
        asks_tab = any(token in normalized for token in ["tab", "tabs", "tablature", "riff", "solo"])
        asks_instrument = any(
            token in normalized
            for token in ["bass", "drum", "guitar", "piano", "keyboard", "keys", "synth", "sax", "vocal", "voice"]
        )
        if not asks_tab and not asks_instrument:
            return None
        if "section" in normalized or "form" in normalized:
            sections = _songsterr_tab_sections(bundle)
            if not sections:
                return ExplanationAnswer(
                    reference_id=profile.reference_id,
                    answer="I do not have section markers from Songsterr for this song yet.",
                    evidence=[],
                )
            return ExplanationAnswer(
                reference_id=profile.reference_id,
                answer="Songsterr tab sections: " + ", ".join(sections) + ".",
                evidence=[f"songsterr:sections:{len(sections)}"],
            )
        instrument = _mentioned_tab_instrument(normalized)
        if instrument is None:
            return ExplanationAnswer(
                reference_id=profile.reference_id,
                answer="Songsterr tab data is loaded for: " + ", ".join(bundle.instrument_names) + ".",
                evidence=[f"songsterr:tracks:{len(bundle.tracks)}"],
            )
        tracks = bundle.tracks_for_instrument(instrument)
        if not tracks:
            return ExplanationAnswer(
                reference_id=profile.reference_id,
                answer=f"I do not have {instrument}-specific Songsterr tab data for this song yet.",
                evidence=[],
            )
        summaries = [_songsterr_track_summary(track) for track in tracks[:3]]
        return ExplanationAnswer(
            reference_id=profile.reference_id,
            answer=" ".join(summaries),
            evidence=[f"songsterr:part:{track.part_id}:measures={len(track.measures)}:notes={track.note_count}" for track in tracks[:3]],
        )


def _answer_key(profile: ReferenceProfile) -> ExplanationAnswer:
    audio = profile.audio
    key_profile = audio.harmony.key if audio and audio.harmony else None
    primary = key_profile.primary if key_profile else None
    if primary is None:
        return ExplanationAnswer(
            reference_id=profile.reference_id,
            answer="I do not have a reliable key estimate for this reference yet.",
            evidence=[],
        )

    alternatives = [
        f"{candidate.key} ({_percent(candidate.confidence)})"
        for candidate in key_profile.candidates[1:4]
    ]
    alternative_labels = [candidate.key for candidate in key_profile.candidates[1:4]]
    suffix = f" Close alternatives: {', '.join(alternatives)}." if alternatives else ""
    ambiguity = " There is relative-key ambiguity." if key_profile.relative_key_ambiguity else ""
    if confidence_label(key_profile.confidence) == "low" or key_profile.relative_key_ambiguity:
        candidates = [primary.key, *alternative_labels]
        confidence_sentence = (
            f"Low confidence ({_percent(key_profile.confidence)})."
            if confidence_label(key_profile.confidence) == "low"
            else f"Confidence {_percent(key_profile.confidence)}."
        )
        return ExplanationAnswer(
            reference_id=profile.reference_id,
            answer=(
                "Tonal center is ambiguous; close candidates include "
                f"{', '.join(candidates)}. {confidence_sentence}"
                f"{suffix}{ambiguity}"
            ),
            evidence=[
                f"Primary key candidate: {primary.key}, confidence {_percent(primary.confidence)}.",
                *[f"Alternative key candidate: {candidate}." for candidate in alternatives],
            ],
        )
    confidence_text = (
        f"low confidence ({_percent(key_profile.confidence)})"
        if confidence_label(key_profile.confidence) == "low"
        else f"{_percent(key_profile.confidence)} confidence"
    )
    return ExplanationAnswer(
        reference_id=profile.reference_id,
        answer=(
            f"The key is likely {primary.key} with {confidence_text}."
            f"{suffix}{ambiguity}"
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
        ("bass", "bass"),
        ("guitar", "guitar"),
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


def _answer_chords(profile: ReferenceProfile) -> ExplanationAnswer:
    audio = profile.audio
    harmony = audio.harmony if audio else None
    if harmony is None:
        return ExplanationAnswer(
            reference_id=profile.reference_id,
            answer="I do not have probable chord estimates for this reference yet.",
            evidence=[],
        )

    main = next((progression for progression in harmony.progressions if progression.chords), None)
    if main is not None:
        progression = " - ".join(main.chords)
        if main.confidence < 0.5:
            return ExplanationAnswer(
                reference_id=profile.reference_id,
                answer=(
                    f"Weak chord loop candidate: {progression} across bars "
                    f"{main.start_bar}-{main.end_bar}, with {_percent(main.confidence)} confidence."
                ),
                evidence=[
                    f"Progression bars {main.start_bar}-{main.end_bar}: {progression}, confidence {_percent(main.confidence)}.",
                    f"Detected repetitions: {main.repetitions}.",
                ],
            )
        return ExplanationAnswer(
            reference_id=profile.reference_id,
            answer=(
                f"The main progression is probably {progression} across bars "
                f"{main.start_bar}-{main.end_bar}, with {_percent(main.confidence)} confidence."
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
            answer="I do not have probable chord estimates for this reference yet.",
            evidence=[],
        )
    summary = " - ".join(span.chosen.label for span in chosen[:8] if span.chosen)
    return ExplanationAnswer(
        reference_id=profile.reference_id,
        answer=f"The strongest bar-level chord estimates are probably {summary}.",
        evidence=[_span_evidence(span) for span in chosen[:8]],
    )


def _answer_structure(profile: ReferenceProfile) -> ExplanationAnswer:
    audio = profile.audio
    structure = audio.structure if audio else None
    if structure is None or not structure.sections:
        return ExplanationAnswer(
            reference_id=profile.reference_id,
            answer="I do not have an A/B/C structure estimate for this reference yet.",
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
                f"The structure is unclear; an approximate low confidence "
                f"A/B/C read is {form}."
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
        answer=f"The structure appears to repeat as {form}.",
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
