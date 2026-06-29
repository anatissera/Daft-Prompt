"""HTTP API tests for local reference analysis uploads.

The heavy DSP pipeline (Demucs + librosa) is covered by the feature-module and
orchestrator unit tests. Here we fake the analyzer so the route plumbing stays
fast and deterministic while still asserting the response carries both the new
harmony/structure fields and the legacy compatibility fields.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import llm_band.interfaces.api as api
from llm_band.domain.audio_profile import (
    AudioProfile,
    ChordCandidate,
    ChordEstimate,
    ChordSpan,
    HarmonicProfile,
    KeyCandidate,
    KeyProfile,
    MeterProfile,
    ProgressionEstimate,
    ReferenceProfile,
    ReferenceSource,
    SectionProfile,
    StemProfile,
    StructuralSection,
    StructureProfile,
    TempoProfile,
)


def _deterministic_profile(source: ReferenceSource) -> ReferenceProfile:
    chosen = ChordCandidate(root="A", quality="minor", label="Am", confidence=0.8)
    audio = AudioProfile(
        duration_seconds=8.0,
        tempo_bpm=120.0,
        tempo_confidence=0.8,
        key="A minor",
        key_confidence=0.7,
        confidence=0.75,
        overall_confidence=0.75,
        chord_estimates=[
            ChordEstimate(start_seconds=0.0, end_seconds=2.0, chords=["Am"], confidence=0.8, is_probable=True)
        ],
        sections=[SectionProfile(name="A", start_seconds=0.0, end_seconds=8.0, confidence=0.8)],
        stems=[StemProfile(name="bass", role="bass", artifact_uri="/fake/bass.wav", confidence=1.0)],
        tempo=TempoProfile(primary_bpm=120.0, confidence=0.8, beat_grid_confidence=0.8, bar_grid_confidence=0.8),
        meter=MeterProfile(),
        harmony=HarmonicProfile(
            key=KeyProfile(
                primary=KeyCandidate(key="A minor", mode="minor", confidence=0.7),
                candidates=[KeyCandidate(key="A minor", mode="minor", confidence=0.7)],
                confidence=0.7,
            ),
            chord_spans=[
                ChordSpan(
                    start_bar=1,
                    end_bar=1,
                    start_seconds=0.0,
                    end_seconds=2.0,
                    candidates=[chosen],
                    chosen=chosen,
                    confidence=0.8,
                )
            ],
            progressions=[ProgressionEstimate(start_bar=1, end_bar=4, chords=["Am", "F", "C", "G"], confidence=0.8)],
            harmonic_rhythm_label="moderate",
            confidence=0.75,
        ),
        structure=StructureProfile(
            sections=[
                StructuralSection(label="A", start_bar=1, end_bar=4, start_seconds=0.0, end_seconds=8.0, confidence=0.8)
            ],
            confidence=0.8,
        ),
    )
    return ReferenceProfile(
        reference_id=source.reference_id,
        source=source,
        audio=audio,
        summary="The key is likely A minor. The main progression is probably Am - F - C - G.",
    )


class _FakeAnalyzer:
    def analyze(self, source: ReferenceSource) -> ReferenceProfile:
        return _deterministic_profile(source)


class _FailingAnalyzer:
    def analyze(self, source: ReferenceSource) -> ReferenceProfile:
        raise RuntimeError("could not decode audio")


def test_analyze_reference_upload_returns_reference_profile(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(api, "REFERENCE_UPLOADS", tmp_path / "uploads")
    monkeypatch.setattr(api, "_reference_analyzer", lambda: _FakeAnalyzer())
    client = TestClient(api.app)

    response = client.post(
        "/references/analyze",
        files={"file": ("loop.wav", b"fake audio bytes", "audio/wav")},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["reference_id"].startswith("ref_")
    assert body["source"]["kind"] == "upload"
    assert body["source"]["label"] == "loop.wav"
    # New harmony/structure fields are present.
    assert body["audio"]["harmony"]["key"]["primary"]["key"] == "A minor"
    assert body["audio"]["harmony"]["chord_spans"][0]["chosen"]["label"] == "Am"
    assert [s["label"] for s in body["audio"]["structure"]["sections"]] == ["A"]
    assert body["audio"]["tempo"]["primary_bpm"] == 120.0
    assert body["audio"]["meter"]["time_signature"] == [4, 4]
    # Legacy compatibility fields are still populated.
    assert body["audio"]["key"] == "A minor"
    assert body["audio"]["chord_estimates"][0]["is_probable"] is True
    assert "Probably" in body["audio"]["chord_estimates"][0]["label"]
    assert "probably" in body["summary"].lower()


def test_analyze_reference_rejects_unsupported_extension(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(api, "REFERENCE_UPLOADS", tmp_path / "uploads")
    client = TestClient(api.app)

    response = client.post(
        "/references/analyze",
        files={"file": ("notes.txt", b"not audio", "text/plain")},
    )

    assert response.status_code == 415
    assert "unsupported" in response.json()["detail"].lower()


def test_analyze_reference_rejects_empty_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(api, "REFERENCE_UPLOADS", tmp_path / "uploads")
    client = TestClient(api.app)

    response = client.post(
        "/references/analyze",
        files={"file": ("empty.wav", b"", "audio/wav")},
    )

    assert response.status_code == 400
    assert "empty" in response.json()["detail"].lower()


def test_analyze_reference_rejects_missing_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(api, "REFERENCE_UPLOADS", tmp_path / "uploads")
    client = TestClient(api.app)

    response = client.post("/references/analyze", files={})

    assert response.status_code == 400
    assert "file" in response.json()["detail"].lower()


def test_analyze_reference_rejects_too_large_upload(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    class _TinyUploadSettings:
        llm_configured = False
        reference_upload_max_bytes = 4

    monkeypatch.setattr(api, "REFERENCE_UPLOADS", tmp_path / "uploads")
    monkeypatch.setattr(api, "get_settings", lambda: _TinyUploadSettings())
    client = TestClient(api.app)

    response = client.post(
        "/references/analyze",
        files={"file": ("loop.wav", b"too large", "audio/wav")},
    )

    assert response.status_code == 413
    assert "too large" in response.json()["detail"].lower()


def test_analyze_reference_reports_analyzer_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(api, "REFERENCE_UPLOADS", tmp_path / "uploads")
    monkeypatch.setattr(api, "_reference_analyzer", lambda: _FailingAnalyzer())
    client = TestClient(api.app)

    response = client.post(
        "/references/analyze",
        files={"file": ("broken.wav", b"not really a wav", "audio/wav")},
    )

    assert response.status_code == 422
    assert "analyze" in response.json()["detail"].lower()


def test_reference_analyzer_wires_development_stem_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(
        api,
        "get_settings",
        lambda: SimpleNamespace(
            reference_upload_dir=str(tmp_path / "uploads"),
            reference_upload_max_bytes=1024,
            reference_stem_cache_enabled=True,
            reference_stem_cache_dir=str(tmp_path / "stem-cache"),
        ),
    )

    analyzer = api._reference_analyzer()

    assert analyzer.separator.cache_enabled is True
    assert analyzer.separator.cache_root == tmp_path / "stem-cache"
