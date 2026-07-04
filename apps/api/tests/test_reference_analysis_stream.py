"""SSE tests for local reference analysis progress."""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import music_assistant.interfaces.api as api
from music_assistant.domain.audio_profile import (
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


def _parse_sse(text: str) -> list[dict]:
    events = []
    for chunk in text.strip().split("\n\n"):
        for line in chunk.splitlines():
            if line.startswith("data:"):
                events.append(json.loads(line.removeprefix("data:").strip()))
    return events


def _profile(source: ReferenceSource) -> ReferenceProfile:
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
            ChordEstimate(start_seconds=0.0, end_seconds=2.0, chords=["Am"], confidence=0.8)
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
                StructuralSection(
                    label="A",
                    start_bar=1,
                    end_bar=4,
                    start_seconds=0.0,
                    end_seconds=8.0,
                    confidence=0.8,
                    main_progression=["Am", "F", "C", "G"],
                )
            ],
            confidence=0.8,
        ),
    )
    return ReferenceProfile(reference_id=source.reference_id, source=source, audio=audio, summary="Analysis ready.")


class _ProgressAnalyzer:
    def analyze(self, source: ReferenceSource, *, progress=None) -> ReferenceProfile:
        assert progress is not None
        for stage in [
            "separating_stems",
            "building_harmonic_source",
            "estimating_tempo_grid",
            "estimating_key",
            "estimating_chords",
            "detecting_structure",
        ]:
            progress(stage, f"{stage} started", status="started")
            progress(
                stage,
                f"{stage} completed",
                status="completed",
                elapsed_seconds=1.25,
                cache_hit=stage == "separating_stems",
            )
        return _profile(source)


class _FailingProgressAnalyzer:
    def analyze(self, source: ReferenceSource, *, progress=None) -> ReferenceProfile:
        if progress is not None:
            progress("separating_stems", "Separating stems.")
        raise RuntimeError("decoder exploded")


class _SlowAnalyzer:
    def analyze(self, source: ReferenceSource, *, progress=None) -> ReferenceProfile:
        time.sleep(0.05)
        return _profile(source)


def test_analyze_reference_stream_emits_progress_and_done(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(api, "REFERENCE_UPLOADS", tmp_path / "uploads")
    monkeypatch.setattr(api, "_reference_analyzer", lambda: _ProgressAnalyzer())
    client = TestClient(api.app)

    response = client.post(
        "/references/analyze/stream",
        files={"file": ("loop.wav", b"fake audio bytes", "audio/wav")},
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    events = _parse_sse(response.text)
    assert events[0]["type"] == "accepted"
    assert events[0]["status"] == "started"
    assert events[-1]["type"] == "done"
    stage_events = events[1:-1]
    assert [event["status"] for event in stage_events] == [
        status
        for _stage in range(6)
        for status in ("started", "completed")
    ]
    assert stage_events[1]["elapsed_seconds"] == 1.25
    assert stage_events[1]["cache_hit"] is True
    assert events[-1]["profile"]["audio"]["harmony"]["key"]["primary"]["key"] == "A minor"
    assert events[-1]["profile"]["audio"]["structure"]["sections"][0]["label"] == "A"


def test_analyze_reference_stream_emits_error_event(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(api, "REFERENCE_UPLOADS", tmp_path / "uploads")
    monkeypatch.setattr(api, "_reference_analyzer", lambda: _FailingProgressAnalyzer())
    client = TestClient(api.app)

    response = client.post(
        "/references/analyze/stream",
        files={"file": ("broken.wav", b"fake audio bytes", "audio/wav")},
    )

    assert response.status_code == 200
    events = _parse_sse(response.text)
    assert [event["type"] for event in events] == ["accepted", "separating_stems", "error"]
    assert "decoder exploded" in events[-1]["message"]


def test_analyze_reference_stream_emits_keepalive_during_long_idle_stage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(api, "REFERENCE_UPLOADS", tmp_path / "uploads")
    monkeypatch.setattr(api, "_reference_analyzer", lambda: _SlowAnalyzer())
    monkeypatch.setattr(api, "ANALYSIS_KEEPALIVE_SECONDS", 0.01)
    client = TestClient(api.app)

    response = client.post(
        "/references/analyze/stream",
        files={"file": ("slow.wav", b"fake audio bytes", "audio/wav")},
    )

    assert response.status_code == 200
    events = _parse_sse(response.text)
    event_types = [event["type"] for event in events]
    assert event_types[0] == "accepted"
    assert "analysis_keepalive" in event_types
    assert event_types[-1] == "done"
