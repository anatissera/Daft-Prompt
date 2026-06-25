"""Question-answering use case over compact reference profiles."""

from __future__ import annotations

import re
from typing import Protocol

from llm_band.domain.audio_profile import ChordSpan, ExplanationAnswer, ReferenceProfile


class MusicQuestionExplainer(Protocol):
    def answer(self, question: str, profile: ReferenceProfile) -> ExplanationAnswer:
        ...


class AnswerMusicQuestion:
    def __init__(self, explainer: MusicQuestionExplainer | None = None):
        self.explainer = explainer or DeterministicMusicQuestionExplainer()

    def execute(self, question: str, profile: ReferenceProfile) -> ExplanationAnswer:
        return self.explainer.answer(question, profile)


class DeterministicMusicQuestionExplainer:
    def answer(self, question: str, profile: ReferenceProfile) -> ExplanationAnswer:
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
        if re.search(r"\b(chord|chords|progression|harmony|harmonic|chorus)\b", normalized):
            return _answer_chords(profile)
        if re.search(r"\b(structure|form|section|sections|repeat|a/b/c|abc|verse|chorus)\b", normalized):
            return _answer_structure(profile)

        return ExplanationAnswer(
            reference_id=profile.reference_id,
            answer=(
                "I can answer from the current analysis about likely key, "
                "probable chords, repeated progressions, and A/B/C structure."
            ),
            evidence=_general_evidence(profile),
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
    suffix = f" Closest alternatives: {', '.join(alternatives)}." if alternatives else ""
    ambiguity = " There is relative-key ambiguity." if key_profile.relative_key_ambiguity else ""
    return ExplanationAnswer(
        reference_id=profile.reference_id,
        answer=(
            f"The key is likely {primary.key} with {_percent(key_profile.confidence)} "
            f"confidence.{suffix}{ambiguity}"
        ),
        evidence=[
            f"Primary key candidate: {primary.key}, confidence {_percent(primary.confidence)}.",
            *[f"Alternative key candidate: {candidate}." for candidate in alternatives],
        ],
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


def _percent(value: float) -> str:
    return f"{round(max(0.0, min(1.0, value)) * 100)}%"
