"""ProfileExplainer over legacy AudioProfile fields (tempo_bpm, key, chord_estimates, sections)."""

from __future__ import annotations

import pytest

from llm_band.application.answer_music_question import AnswerMusicQuestion
from llm_band.domain.audio_profile import (
    AudioProfile,
    ChordEstimate,
    ReferenceProfile,
    ReferenceSource,
    SectionProfile,
)
from llm_band.infrastructure.explainer.profile_explainer import ProfileExplainer


def _profile(audio: AudioProfile | None = None) -> ReferenceProfile:
    source = ReferenceSource(
        reference_id="ref_test",
        kind="upload",
        label="demo.wav",
        uri="local://demo.wav",
        authorized=True,
    )
    return ReferenceProfile(reference_id="ref_test", source=source, audio=audio)


def _audio_with_everything() -> AudioProfile:
    return AudioProfile(
        duration_seconds=124.0,
        tempo_bpm=118.3,
        tempo_confidence=0.84,
        key="C major",
        key_confidence=0.72,
        confidence=0.9,
        overall_confidence=0.9,
        chord_estimates=[
            ChordEstimate(start_seconds=0.0, end_seconds=12.0, chords=["Am", "F", "C", "G"], confidence=0.66),
            ChordEstimate(start_seconds=12.0, end_seconds=24.0, chords=["F", "C", "G", "Am"], confidence=0.6),
        ],
        sections=[
            SectionProfile(name="verse", start_seconds=0.0, end_seconds=30.0, energy=0.4, energy_confidence=0.8),
            SectionProfile(name="chorus", start_seconds=30.0, end_seconds=60.0, energy=0.85, energy_confidence=0.83),
        ],
    )


@pytest.fixture()
def explainer_use_case() -> AnswerMusicQuestion:
    return AnswerMusicQuestion(ProfileExplainer())


def test_chord_question_cites_probable_progression(explainer_use_case: AnswerMusicQuestion):
    answer = explainer_use_case.execute("what chords does the chorus use?", _profile(_audio_with_everything()))
    assert "Probably" in answer.answer
    assert "Am" in answer.answer
    assert any(item.startswith("chord:") for item in answer.evidence)


def test_tempo_question_cites_bpm_and_confidence(explainer_use_case: AnswerMusicQuestion):
    answer = explainer_use_case.execute("what is the tempo?", _profile(_audio_with_everything()))
    assert "118 BPM" in answer.answer
    assert "high" in answer.answer or "medium" in answer.answer
    assert any(item.startswith("tempo:118") for item in answer.evidence)


def test_key_question_uses_probably_language(explainer_use_case: AnswerMusicQuestion):
    answer = explainer_use_case.execute("what key is this in?", _profile(_audio_with_everything()))
    assert "probably C major" in answer.answer
    assert any(item.startswith("key:C major") for item in answer.evidence)


def test_section_question_cites_energy_per_section(explainer_use_case: AnswerMusicQuestion):
    answer = explainer_use_case.execute("which section lifts the energy?", _profile(_audio_with_everything()))
    assert "verse" in answer.answer
    assert "chorus" in answer.answer
    assert any(item.startswith("section:chorus") for item in answer.evidence)


def test_summary_fallback_when_question_is_generic(explainer_use_case: AnswerMusicQuestion):
    answer = explainer_use_case.execute("tell me about it", _profile(_audio_with_everything()))
    assert "probable chords" in answer.answer
    assert any(item.startswith("tempo:") for item in answer.evidence)


def test_no_audio_profile_returns_clear_message(explainer_use_case: AnswerMusicQuestion):
    answer = explainer_use_case.execute("what chords?", _profile(None))
    assert "no audio profile" in answer.answer.lower() or "do not have" in answer.answer.lower()
    assert answer.evidence == []


def test_missing_tempo_returns_no_reliable_estimate(explainer_use_case: AnswerMusicQuestion):
    audio = _audio_with_everything().model_copy(update={"tempo_bpm": None, "tempo_confidence": 0.0})
    answer = explainer_use_case.execute("how fast is it?", _profile(audio))
    assert "do not have a reliable tempo" in answer.answer
