"""Reference resolution and analysis use cases."""

from __future__ import annotations

from typing import Protocol

from music_assistant.application.audio_enrichment import enrich_profile_with_audio
from music_assistant.application.melody_profile import melody_profile_from_notes
from music_assistant.domain.audio_profile import AnalysisNote, ReferenceProfile, ReferenceSource
from music_assistant.ports.audio_analyzer import AudioAnalyzer
from music_assistant.ports.transcription import Transcriber


class ReferenceResolver(Protocol):
    def resolve(self, query: str) -> ReferenceSource:
        ...


class ResolveReference:
    def __init__(self, resolver: ReferenceResolver):
        self.resolver = resolver

    def execute(self, query: str) -> ReferenceSource:
        return self.resolver.resolve(query)


class AnalyzeReference:
    def __init__(self, analyzer: AudioAnalyzer, *, transcriber: Transcriber | None = None):
        self.analyzer = analyzer
        self.transcriber = transcriber

    def execute(self, source: ReferenceSource) -> ReferenceProfile:
        if not source.authorized:
            return ReferenceProfile(reference_id=source.reference_id, source=source)
        profile = self.analyzer.analyze(source)
        return enrich_profile_with_transcription(profile, source, self.transcriber)


def enrich_profile_with_transcription(
    profile: ReferenceProfile,
    source: ReferenceSource,
    transcriber: Transcriber | None,
) -> ReferenceProfile:
    """Add optional transcription evidence without making analysis depend on it."""
    if transcriber is None or profile.audio is None:
        return enrich_profile_with_audio(profile)

    try:
        notes = transcriber.transcribe_melody(source)
    except (OSError, RuntimeError) as exc:
        audio = profile.audio.model_copy(
            update={
                "analysis_notes": [
                    *profile.audio.analysis_notes,
                    AnalysisNote(
                        code="melody_transcription_unavailable",
                        message=f"Melody transcription was unavailable; core audio analysis is still ready: {exc}",
                        severity="info",
                    ),
                ]
            }
        )
        return enrich_profile_with_audio(profile.model_copy(update={"audio": audio}))

    melody = melody_profile_from_notes(notes)
    audio = profile.audio.model_copy(update={"melody": melody})
    return enrich_profile_with_audio(profile.model_copy(update={"audio": audio}))
