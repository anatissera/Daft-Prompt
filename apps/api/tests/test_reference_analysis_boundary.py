"""Application boundary for future listening/reference analysis.

This does not test real audio analysis. It verifies that the bounded context can
be exercised through ports and that composition stays decoupled from listening
internals and MIR adapters.
"""

from __future__ import annotations

import ast
from pathlib import Path

from llm_band.application.analyze_reference import AnalyzeReference, ResolveReference
from llm_band.application.answer_music_question import AnswerMusicQuestion
from llm_band.domain.audio_profile import (
    AudioProfile,
    ChordEstimate,
    EnergyPoint,
    ExplanationAnswer,
    ReferenceProfile,
    ReferenceSource,
    SectionProfile,
)


class FakeReferenceResolver:
    def __init__(self, sources: dict[str, ReferenceSource]):
        self.sources = sources

    def resolve(self, query: str) -> ReferenceSource:
        source = self.sources[query]
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
        return ExplanationAnswer(
            reference_id=profile.reference_id,
            answer=f"Answer for {profile.reference_id}: {question}",
            evidence=["fake evidence"],
        )


def test_reference_analysis_use_cases_run_with_fakes_and_no_audio_or_network():
    source = ReferenceSource(
        reference_id="ref_demo",
        kind="upload",
        label="permitted demo clip",
        uri="local://demo.wav",
        authorized=True,
    )
    resolver = FakeReferenceResolver({"demo": source})
    resolved = ResolveReference(resolver).execute("demo")

    assert resolved.reference_id == "ref_demo"
    assert resolved.authorized is True

    profile = ReferenceProfile(
        reference_id="ref_demo",
        source=resolved,
        audio=AudioProfile(
            duration_seconds=12.0,
            tempo_bpm=118.0,
            tempo_confidence=0.86,
            key="C major",
            key_confidence=0.73,
            confidence=0.91,
            overall_confidence=0.91,
            energy_curve=[
                EnergyPoint(time_seconds=0.0, energy=0.35, confidence=0.8),
                EnergyPoint(time_seconds=6.0, energy=0.82, confidence=0.84),
            ],
            chord_estimates=[
                ChordEstimate(
                    start_seconds=0.0,
                    end_seconds=12.0,
                    chords=["Am", "F", "C", "G"],
                    confidence=0.66,
                )
            ],
            sections=[
                SectionProfile(
                    name="loop",
                    start_seconds=0.0,
                    end_seconds=12.0,
                    energy=0.78,
                    energy_confidence=0.81,
                    chord_estimates=[
                        ChordEstimate(
                            start_seconds=0.0,
                            end_seconds=12.0,
                            chords=["Am", "F", "C", "G"],
                            confidence=0.66,
                        )
                    ],
                )
            ],
        ),
    )
    analyzer = FakeAudioAnalyzer({"ref_demo": profile})
    analyzed = AnalyzeReference(analyzer).execute(resolved)

    assert analyzed.audio is not None
    assert analyzed.audio.tempo_bpm == 118.0
    assert analyzed.audio.tempo_confidence == 0.86
    assert analyzed.audio.key_confidence == 0.73
    assert analyzed.audio.overall_confidence == 0.91
    assert analyzed.audio.energy_curve[1].energy == 0.82
    assert analyzed.audio.chord_estimates[0].is_probable is True
    assert analyzed.audio.chord_estimates[0].label == "Probably Am - F - C - G"
    assert analyzed.audio.sections[0].energy == 0.78
    assert analyzed.audio.sections[0].chord_estimates[0].confidence_label == "medium"
    dumped_chord = analyzed.model_dump(mode="json")["audio"]["chord_estimates"][0]
    assert dumped_chord["label"] == "Probably Am - F - C - G"
    assert dumped_chord["confidence_label"] == "medium"

    answer = AnswerMusicQuestion(FakeExplainer()).execute(
        "why does the chorus lift?", analyzed
    )
    assert answer.reference_id == "ref_demo"
    assert "ref_demo" in answer.answer
    assert answer.evidence


def test_unauthorized_reference_fails_before_analysis():
    source = ReferenceSource(
        reference_id="ref_blocked",
        kind="youtube",
        label="commercial song",
        uri="https://youtube.example/watch?v=blocked",
        authorized=False,
    )
    resolver = FakeReferenceResolver({"song": source})

    resolved = ResolveReference(resolver).execute("song")

    assert resolved.authorized is False
    assert resolved.permission_error is not None


def test_composition_modules_do_not_import_reference_analysis_internals():
    root = Path(__file__).resolve().parents[1] / "llm_band"
    checked = [
        root / "application" / "compose_song.py",
        root / "graph.py",
        *(root / "agents").glob("*.py"),
        *(root / "music").glob("*.py"),
    ]
    forbidden = []
    for path in checked:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            else:
                continue
            if any(
                name.startswith("llm_band.ports.audio_analyzer")
                or name.startswith("llm_band.ports.stem_separator")
                or name.startswith("llm_band.ports.transcription")
                or name.startswith("llm_band.infrastructure.mir")
                for name in names
            ):
                forbidden.append((path.name, names))

    assert forbidden == []
