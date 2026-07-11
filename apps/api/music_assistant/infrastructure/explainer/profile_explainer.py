"""Deterministic explainer over a ReferenceProfile.

Used as the default MVP explainer so questions work without an LLM key. Mirrors
the JS helper used by the frontend so behavior is consistent across both layers.
Answers always cite tempo/key/section/chord evidence from the profile itself and
phrase uncertain chords as "probably".
"""

from __future__ import annotations

import re

from music_assistant.domain.audio_profile import (
    AudioProfile,
    ExplanationAnswer,
    ReferenceProfile,
    confidence_label,
)

_CHORD_RE = re.compile(r"\b(chord|chords|chorus|harmony|harmonic|progression)\b")
_TEMPO_RE = re.compile(r"\b(tempo|bpm|speed|fast|slow)\b")
_KEY_RE = re.compile(r"\b(key|tonality|tonal|scale)\b")
_SECTION_RE = re.compile(r"\b(energy|section|sections|lift|bigger|contrast|verse|chorus|bridge|intro|outro)\b")


def _percent(value: float) -> str:
    clamped = max(0.0, min(1.0, value))
    return f"{round(clamped * 100)}%"


def _format_seconds(seconds: float) -> str:
    safe = max(0, round(seconds))
    minutes, remaining = divmod(safe, 60)
    return f"{minutes}:{remaining:02d}"


def _confidence_phrase(value: float) -> str:
    return f"{confidence_label(value)} ({_percent(value)})"


class ProfileExplainer:
    """Implements ``MusicQuestionExplainer`` deterministically."""

    def answer(self, question: str, profile: ReferenceProfile) -> ExplanationAnswer:
        audio = profile.audio
        if audio is None:
            return ExplanationAnswer(
                reference_id=profile.reference_id,
                answer="I do not have an audio profile for this reference yet.",
                evidence=[],
            )

        normalized = question.lower()

        if _CHORD_RE.search(normalized):
            return self._answer_chords(profile, audio)
        if _TEMPO_RE.search(normalized):
            return self._answer_tempo(profile, audio)
        if _KEY_RE.search(normalized):
            return self._answer_key(profile, audio)
        if _SECTION_RE.search(normalized):
            return self._answer_sections(profile, audio)

        return self._answer_summary(profile, audio)

    def _answer_chords(self, profile: ReferenceProfile, audio: AudioProfile) -> ExplanationAnswer:
        estimates = audio.chord_estimates[:4]
        if not estimates:
            return ExplanationAnswer(
                reference_id=profile.reference_id,
                answer="I do not have probable chord estimates for this reference yet.",
                evidence=[],
            )
        pieces = []
        evidence = []
        for estimate in estimates:
            range_label = f"{_format_seconds(estimate.start_seconds)}-{_format_seconds(estimate.end_seconds)}"
            pieces.append(
                f"{estimate.label} from {range_label} with {_confidence_phrase(estimate.confidence)} confidence"
            )
            evidence.append(f"chord:{range_label}:{','.join(estimate.chords) or 'unknown'}:{estimate.confidence:.2f}")
        return ExplanationAnswer(
            reference_id=profile.reference_id,
            answer="The chords are estimated. The strongest matches are: " + "; ".join(pieces) + ".",
            evidence=evidence,
        )

    def _answer_tempo(self, profile: ReferenceProfile, audio: AudioProfile) -> ExplanationAnswer:
        if audio.tempo_bpm is None:
            return ExplanationAnswer(
                reference_id=profile.reference_id,
                answer="I do not have a reliable tempo estimate for this reference yet.",
                evidence=[],
            )
        bpm = round(audio.tempo_bpm)
        return ExplanationAnswer(
            reference_id=profile.reference_id,
            answer=f"The tempo is likely {bpm} BPM with {_confidence_phrase(audio.tempo_confidence)} confidence.",
            evidence=[f"tempo:{bpm}:{audio.tempo_confidence:.2f}"],
        )

    def _answer_key(self, profile: ReferenceProfile, audio: AudioProfile) -> ExplanationAnswer:
        if not audio.key:
            return ExplanationAnswer(
                reference_id=profile.reference_id,
                answer="I do not have a reliable key estimate for this reference yet.",
                evidence=[],
            )
        return ExplanationAnswer(
            reference_id=profile.reference_id,
            answer=f"The key is probably {audio.key} with {_confidence_phrase(audio.key_confidence)} confidence.",
            evidence=[f"key:{audio.key}:{audio.key_confidence:.2f}"],
        )

    def _answer_sections(self, profile: ReferenceProfile, audio: AudioProfile) -> ExplanationAnswer:
        if not audio.sections:
            return ExplanationAnswer(
                reference_id=profile.reference_id,
                answer="I do not have section-level energy estimates for this reference yet.",
                evidence=[],
            )
        pieces = []
        evidence = []
        for section in audio.sections[:3]:
            energy_text = (
                f"{round((section.energy or 0) * 100)}% energy"
                if section.energy is not None
                else "unknown energy"
            )
            range_label = f"{_format_seconds(section.start_seconds)}-{_format_seconds(section.end_seconds)}"
            pieces.append(f"{section.name} at {energy_text} from {range_label}")
            evidence.append(f"section:{section.name}:{range_label}:{section.energy_confidence:.2f}")
        return ExplanationAnswer(
            reference_id=profile.reference_id,
            answer="The section energy estimate is " + ", then ".join(pieces) + ".",
            evidence=evidence,
        )

    def _answer_summary(self, profile: ReferenceProfile, audio: AudioProfile) -> ExplanationAnswer:
        rows: list[str] = []
        evidence: list[str] = []
        rows.append(f"duration around {_format_seconds(audio.duration_seconds)}")
        if audio.tempo_bpm is not None:
            rows.append(f"likely {round(audio.tempo_bpm)} BPM ({_confidence_phrase(audio.tempo_confidence)})")
            evidence.append(f"tempo:{round(audio.tempo_bpm)}:{audio.tempo_confidence:.2f}")
        if audio.key:
            rows.append(f"probably in {audio.key} ({_confidence_phrase(audio.key_confidence)})")
            evidence.append(f"key:{audio.key}:{audio.key_confidence:.2f}")
        if audio.chord_estimates:
            top = audio.chord_estimates[0]
            rows.append(f"probable chords like {top.label}")
            evidence.append(f"chord:{','.join(top.chords) or 'unknown'}:{top.confidence:.2f}")
        return ExplanationAnswer(
            reference_id=profile.reference_id,
            answer=(
                "I can answer from the current analysis about likely tempo, key, energy or sections, "
                "and probable chords. Summary: " + ", ".join(rows) + "."
            ),
            evidence=evidence,
        )
