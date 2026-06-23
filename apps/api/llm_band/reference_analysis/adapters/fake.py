"""Fake adapters for architecture tests.

They do not access the network, decode audio, or call any model provider.
"""

from __future__ import annotations

from ..models import ExplanationAnswer, ReferenceProfile, ReferenceSource


class FakeReferenceResolver:
    def __init__(self, sources: dict[str, ReferenceSource]):
        self.sources = sources

    def resolve(self, query: str) -> ReferenceSource:
        source = self.sources.get(
            query,
            ReferenceSource(
                reference_id=f"missing_{query}",
                kind="metadata",
                label=query,
                uri="",
                authorized=False,
                permission_error="reference not found or not authorized",
            ),
        )
        if not source.authorized and source.permission_error is None:
            return source.model_copy(update={"permission_error": "reference is not authorized for analysis"})
        return source


class FakeAudioAnalyzer:
    def __init__(self, profiles: dict[str, ReferenceProfile]):
        self.profiles = profiles

    def analyze(self, source: ReferenceSource) -> ReferenceProfile:
        return self.profiles[source.reference_id]


class FakeExplainer:
    def answer(self, question: str, profile: ReferenceProfile) -> ExplanationAnswer:
        evidence = []
        if profile.audio and profile.audio.tempo_bpm is not None:
            evidence.append(f"tempo={profile.audio.tempo_bpm}")
        if profile.audio and profile.audio.sections:
            section = profile.audio.sections[0]
            evidence.append(f"{section.name}@{section.start_seconds}-{section.end_seconds}s")
        return ExplanationAnswer(
            reference_id=profile.reference_id,
            answer=f"Answer for {profile.reference_id}: {question}",
            evidence=evidence,
        )
