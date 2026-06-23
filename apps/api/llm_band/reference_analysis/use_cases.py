"""Application use cases for the reference-analysis bounded context."""

from __future__ import annotations

from .models import ExplanationAnswer, ReferenceProfile, ReferenceSource
from .ports import AudioAnalyzer, MusicQuestionExplainer, ReferenceResolver


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
        return self.analyzer.analyze(source)


class AnswerMusicQuestion:
    def __init__(self, explainer: MusicQuestionExplainer):
        self.explainer = explainer

    def execute(self, question: str, profile: ReferenceProfile) -> ExplanationAnswer:
        return self.explainer.answer(question, profile)


class UseReferenceForComposition:
    """Return the compact profile future composition code may consume."""

    def execute(self, profile: ReferenceProfile) -> ReferenceProfile:
        return profile
