"""Deterministic music Q&A over harmonic and structure profiles."""

from __future__ import annotations

from music_assistant.application.answer_music_question import AnswerMusicQuestion
from music_assistant.domain.audio_profile import (
    AnalysisNote,
    AudioProfile,
    ChordCandidate,
    ChordSpan,
    HarmonicProfile,
    KeyCandidate,
    KeyProfile,
    ProgressionEstimate,
    ReferenceProfile,
    ReferenceSource,
    StructuralSection,
    StructureProfile,
)


def _profile() -> ReferenceProfile:
    chosen_am = ChordCandidate(root="A", quality="minor", label="Am", confidence=0.82)
    chosen_f = ChordCandidate(root="F", quality="major", label="F", confidence=0.78)
    return ReferenceProfile(
        reference_id="ref_demo",
        source=ReferenceSource(
            reference_id="ref_demo",
            kind="upload",
            label="demo.wav",
            uri="/tmp/demo.wav",
            authorized=True,
        ),
        audio=AudioProfile(
            duration_seconds=32.0,
            confidence=0.75,
            overall_confidence=0.75,
            harmony=HarmonicProfile(
                key=KeyProfile(
                    primary=KeyCandidate(key="A minor", mode="minor", confidence=0.72),
                    candidates=[
                        KeyCandidate(key="A minor", mode="minor", confidence=0.72),
                        KeyCandidate(key="C major", mode="major", confidence=0.66),
                    ],
                    relative_key_ambiguity=True,
                    confidence=0.72,
                ),
                chord_spans=[
                    ChordSpan(
                        start_bar=1,
                        end_bar=1,
                        start_seconds=0.0,
                        end_seconds=2.0,
                        candidates=[chosen_am],
                        chosen=chosen_am,
                        confidence=0.82,
                    ),
                    ChordSpan(
                        start_bar=2,
                        end_bar=2,
                        start_seconds=2.0,
                        end_seconds=4.0,
                        candidates=[chosen_f],
                        chosen=chosen_f,
                        confidence=0.78,
                    ),
                ],
                progressions=[
                    ProgressionEstimate(
                        start_bar=1,
                        end_bar=4,
                        chords=["Am", "F", "C", "G"],
                        confidence=0.79,
                        repetitions=2,
                    )
                ],
                harmonic_rhythm_label="moderate",
                confidence=0.76,
            ),
            structure=StructureProfile(
                sections=[
                    StructuralSection(
                        label="A",
                        start_bar=1,
                        end_bar=4,
                        start_seconds=0.0,
                        end_seconds=8.0,
                        confidence=0.8,
                        main_progression=["Am", "F", "C", "G"],
                    ),
                    StructuralSection(
                        label="B",
                        start_bar=5,
                        end_bar=8,
                        start_seconds=8.0,
                        end_seconds=16.0,
                        confidence=0.74,
                        main_progression=["F", "C", "G", "Am"],
                    ),
                    StructuralSection(
                        label="A",
                        start_bar=9,
                        end_bar=12,
                        start_seconds=16.0,
                        end_seconds=24.0,
                        confidence=0.79,
                        main_progression=["Am", "F", "C", "G"],
                    ),
                ],
                confidence=0.78,
            ),
        ),
    )


def _low_usefulness_profile() -> ReferenceProfile:
    return ReferenceProfile(
        reference_id="ref_weak",
        source=ReferenceSource(
            reference_id="ref_weak",
            kind="upload",
            label="weak.wav",
            uri="/tmp/weak.wav",
            authorized=True,
        ),
        audio=AudioProfile(
            duration_seconds=10.0,
            analysis_notes=[
                AnalysisNote(
                    code="low_usefulness",
                    message="Key, chord, and structure evidence are all weak.",
                    severity="warning",
                )
            ],
        ),
    )


def test_chorus_question_routes_to_structure_not_chords():
    answer = AnswerMusicQuestion().execute("Where is the chorus?", _profile())

    assert answer.answer.startswith("The structure appears to repeat as")


def test_general_answer_leads_with_limitation_when_usefulness_is_low():
    answer = AnswerMusicQuestion().execute("Give me an overview.", _low_usefulness_profile())

    assert answer.answer.startswith("The chord and structure evidence is weak here")


def test_answers_key_questions_from_key_profile():
    answer = AnswerMusicQuestion().execute("What key is this in?", _profile())

    assert answer.reference_id == "ref_demo"
    assert answer.answer == (
        "Tonal center is ambiguous; close candidates include A minor, C major. "
        "Confidence 72%. Close alternatives: C major (66%). "
        "There is relative-key ambiguity."
    )
    assert "Primary key candidate: A minor" in answer.evidence[0]


def test_spanish_key_question_uses_spanish_explanation_and_keeps_evidence():
    answer = AnswerMusicQuestion().execute("¿Cuál es la tonalidad de esta canción?", _profile())

    assert answer.answer.startswith("El centro tonal es ambiguo")
    assert "A minor" in answer.answer
    assert "Primary key candidate: A minor" in answer.evidence[0]


def test_spanish_chord_and_structure_questions_are_recognized():
    explainer = AnswerMusicQuestion()

    chords = explainer.execute("¿Qué acordes tiene la progresión?", _profile())
    structure = explainer.execute("¿Cuál es la estructura y dónde está el coro?", _profile())

    assert chords.answer.startswith("La progresión principal probablemente es")
    assert "Am - F - C - G" in chords.answer
    assert structure.answer.startswith("La estructura parece repetirse como")


def test_answers_chord_questions_from_progression_estimates():
    answer = AnswerMusicQuestion().execute("What chords are probably in the chorus?", _profile())

    assert answer.answer == (
        "The main progression is probably Am - F - C - G across bars 1-4, "
        "with 79% confidence."
    )
    assert "Progression bars 1-4" in answer.evidence[0]
    assert "Detected repetitions: 2." in answer.evidence


def test_answers_chord_questions_with_weak_loop_candidate_before_triads():
    profile = _profile()
    profile.audio.harmony.progressions = [
        ProgressionEstimate(
            start_bar=1,
            end_bar=4,
            chords=["Am", "F", "C", "G"],
            confidence=0.38,
            repetitions=3,
        )
    ]

    answer = AnswerMusicQuestion().execute("what chords repeat?", profile)

    assert answer.answer == (
        "Weak chord loop candidate: Am - F - C - G across bars 1-4, "
        "with 38% confidence."
    )


def test_answers_structure_questions_from_structure_profile():
    answer = AnswerMusicQuestion().execute("What is the form?", _profile())

    assert answer.answer == "The structure appears to repeat as A bars 1-4 / B bars 5-8 / A bars 9-12."
    assert answer.evidence == [
        "Section A: bars 1-4, confidence 80%.",
        "Section B: bars 5-8, confidence 74%.",
        "Section A: bars 9-12, confidence 79%.",
    ]


def test_key_answer_mentions_close_alternatives_when_confidence_is_low():
    profile = _profile()
    key_profile = profile.audio.harmony.key
    key_profile.primary = KeyCandidate(key="Ab major", mode="major", confidence=0.44)
    key_profile.candidates = [
        KeyCandidate(key="Ab major", mode="major", confidence=0.44),
        KeyCandidate(key="F minor", mode="minor", confidence=0.42),
        KeyCandidate(key="C# minor", mode="minor", confidence=0.38),
    ]
    key_profile.relative_key_ambiguity = True
    key_profile.confidence = 0.44

    answer = AnswerMusicQuestion().execute("what key is this in?", profile)

    assert answer.answer.startswith("Tonal center is ambiguous")
    assert "probably" not in answer.answer.lower()
    assert "likely" not in answer.answer.lower()
    assert "low confidence" in answer.answer.lower()
    assert "close alternatives" in answer.answer.lower()
    assert "F minor" in answer.answer


def test_structure_answer_mentions_uncertainty_when_confidence_is_low():
    profile = _profile()
    profile.audio.structure.confidence = 0.25
    for section in profile.audio.structure.sections:
        section.confidence = 0.25

    answer = AnswerMusicQuestion().execute("what is the form?", profile)

    assert "unclear" in answer.answer.lower() or "approximate" in answer.answer.lower()
    assert "low confidence" in answer.answer.lower()


def test_falls_back_when_profile_has_no_audio():
    profile = ReferenceProfile(
        reference_id="ref_empty",
        source=ReferenceSource(
            reference_id="ref_empty",
            kind="upload",
            label="empty.wav",
            uri="/tmp/empty.wav",
            authorized=True,
        ),
    )

    answer = AnswerMusicQuestion().execute("What key is it?", profile)

    assert answer.answer == "I do not have an audio profile for this reference yet."
    assert answer.evidence == []
