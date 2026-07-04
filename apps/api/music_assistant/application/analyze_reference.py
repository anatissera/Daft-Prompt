"""Reference resolution and analysis use cases."""

from __future__ import annotations

from typing import Protocol

from music_assistant.application.audio_enrichment import enrich_profile_with_audio
from music_assistant.domain.audio_profile import ReferenceProfile, ReferenceSource
from music_assistant.ports.audio_analyzer import AudioAnalyzer


class ReferenceResolver(Protocol):
    def resolve(self, query: str) -> ReferenceSource:
        ...


class ResolveReference:
    def __init__(self, resolver: ReferenceResolver):
        self.resolver = resolver

    def execute(self, query: str) -> ReferenceSource:
        return self.resolver.resolve(query)


class AnalyzeReference:
    def __init__(self, analyzer: AudioAnalyzer):
        self.analyzer = analyzer

    def execute(self, source: ReferenceSource) -> ReferenceProfile:
        if not source.authorized:
            return ReferenceProfile(reference_id=source.reference_id, source=source)
        return enrich_profile_with_audio(self.analyzer.analyze(source))
