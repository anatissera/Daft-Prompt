from __future__ import annotations

from music_assistant.application.analyze_reference import AnalyzeReference
from music_assistant.application.answer_music_question import AnswerMusicQuestion
from music_assistant.application.melody_profile import melody_profile_from_notes
from music_assistant.domain.audio_profile import AudioProfile, ReferenceProfile, ReferenceSource
from music_assistant.domain.song_state import Note


def _source() -> ReferenceSource:
    return ReferenceSource(
        reference_id="ref_melody",
        kind="upload",
        label="melody.wav",
        uri="local://melody.wav",
        authorized=True,
    )


class _Analyzer:
    def analyze(self, source: ReferenceSource) -> ReferenceProfile:
        return ReferenceProfile(
            reference_id=source.reference_id,
            source=source,
            audio=AudioProfile(duration_seconds=8.0),
        )


class _Transcriber:
    def transcribe_melody(self, source: ReferenceSource) -> list[Note]:
        return [
            Note(bar=0, start_beat=0, pitch=60, dur=0.5),
            Note(bar=0, start_beat=1, pitch=64, dur=0.5),
            Note(bar=0, start_beat=2, pitch=62, dur=1.0),
            Note(bar=1, start_beat=0, pitch=67, dur=1.0),
        ]


class _UnavailableTranscriber:
    def transcribe_melody(self, source: ReferenceSource) -> list[Note]:
        raise RuntimeError("install optional runtime")


def test_melody_profile_is_bounded_symbolic_summary():
    notes = [Note(bar=index // 4, start_beat=float(index % 4), pitch=60 + index, dur=0.5) for index in range(40)]

    profile = melody_profile_from_notes(notes)

    assert profile.note_count == 40
    assert (profile.pitch_low, profile.pitch_high) == (60, 99)
    assert profile.contour == "rising"
    assert len(profile.representative_events) == 32
    assert profile.representative_events[0].pitch == 60
    assert profile.representative_events[-1].pitch == 99
    assert profile.confidence == 0.4


def test_analysis_adds_optional_transcription_and_explains_riff():
    analyzed = AnalyzeReference(_Analyzer(), transcriber=_Transcriber()).execute(_source())

    assert analyzed.audio is not None
    assert analyzed.audio.melody is not None
    assert analyzed.audio.melody.contour == "mixed"
    assert any("provisional transcription" in claim.notes for claim in analyzed.knowledge.evidence_claims)

    answer = AnswerMusicQuestion().execute("How do I play this riff?", analyzed)

    assert "4 melodic notes" in answer.answer
    assert "MIDI 60-67" in answer.answer
    assert answer.evidence


def test_transcription_failure_keeps_core_analysis_and_surfaces_a_note():
    analyzed = AnalyzeReference(_Analyzer(), transcriber=_UnavailableTranscriber()).execute(_source())

    assert analyzed.audio is not None
    assert analyzed.audio.melody is None
    assert any(note.code == "melody_transcription_unavailable" for note in analyzed.audio.analysis_notes)
