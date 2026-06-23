"""Ports for reference-analysis use cases.

Adapters in later phases can implement these protocols with Gemini audio, MIR
libraries, search providers, or object storage. Tests use fakes only.
"""

from __future__ import annotations

from typing import Protocol

from .models import ExplanationAnswer, ReferenceProfile, ReferenceSource


class ReferenceResolver(Protocol):
    def resolve(self, query: str) -> ReferenceSource:
        ...


class AudioAnalyzer(Protocol):
    def analyze(self, source: ReferenceSource) -> ReferenceProfile:
        ...


class MusicQuestionExplainer(Protocol):
    def answer(self, question: str, profile: ReferenceProfile) -> ExplanationAnswer:
        ...
