"""Architecture boundary for future listening/reference analysis.

This does not test real audio analysis. It verifies that the bounded context can
be exercised with fakes and that composition stays decoupled from listening
internals.
"""

from __future__ import annotations

import ast
from pathlib import Path

from llm_band.reference_analysis.adapters.fake import (
    FakeAudioAnalyzer,
    FakeExplainer,
    FakeReferenceResolver,
)
from llm_band.reference_analysis.models import (
    AudioProfile,
    ReferenceProfile,
    ReferenceSource,
    SectionProfile,
)
from llm_band.reference_analysis.use_cases import (
    AnalyzeReference,
    AnswerMusicQuestion,
    ResolveReference,
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
            key="C major",
            confidence=0.91,
            sections=[SectionProfile(name="loop", start_seconds=0.0, end_seconds=12.0)],
        ),
    )
    analyzer = FakeAudioAnalyzer({"ref_demo": profile})
    analyzed = AnalyzeReference(analyzer).execute(resolved)

    assert analyzed.audio is not None
    assert analyzed.audio.tempo_bpm == 118.0

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
            if any(name.startswith("llm_band.reference_analysis") or name.startswith("reference_analysis") for name in names):
                forbidden.append((path.name, names))

    assert forbidden == []
