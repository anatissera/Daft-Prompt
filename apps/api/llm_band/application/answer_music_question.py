"""Question-answering use case over compact reference profiles."""

from __future__ import annotations

from typing import Protocol

from llm_band.domain.audio_profile import ExplanationAnswer, ReferenceProfile


class MusicQuestionExplainer(Protocol):
    def answer(self, question: str, profile: ReferenceProfile) -> ExplanationAnswer:
        ...


class AnswerMusicQuestion:
    def __init__(self, explainer: MusicQuestionExplainer):
        self.explainer = explainer

    def execute(self, question: str, profile: ReferenceProfile) -> ExplanationAnswer:
        return self.explainer.answer(question, profile)
