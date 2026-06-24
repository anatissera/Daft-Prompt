"""HTTP API tests for local reference analysis uploads."""

from __future__ import annotations

import math
import wave
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient

import llm_band.interfaces.api as api


def _write_synthetic_chord_loop(path: Path, duration_seconds: float = 4.0) -> bytes:
    sample_rate = 22_050
    total_samples = int(sample_rate * duration_seconds)
    samples = np.zeros(total_samples, dtype=np.float32)
    chord_frequencies = [
        (261.63, 329.63, 392.00),
        (220.00, 261.63, 329.63),
        (174.61, 220.00, 261.63),
        (196.00, 246.94, 293.66),
    ]

    for index in range(total_samples):
        t = index / sample_rate
        chord = chord_frequencies[int(t // 1.0) % len(chord_frequencies)]
        tone = sum(math.sin(2.0 * math.pi * frequency * t) for frequency in chord)
        samples[index] = 0.12 * tone

    pcm = (np.clip(samples, -1.0, 1.0) * 32767).astype(np.int16)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes(pcm.tobytes())
    return path.read_bytes()


def test_analyze_reference_upload_returns_reference_profile(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(api, "REFERENCE_UPLOADS", tmp_path / "uploads")
    audio_bytes = _write_synthetic_chord_loop(tmp_path / "loop.wav")
    client = TestClient(api.app)

    response = client.post(
        "/references/analyze",
        files={"file": ("loop.wav", audio_bytes, "audio/wav")},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["reference_id"].startswith("ref_")
    assert body["source"]["kind"] == "upload"
    assert body["source"]["label"] == "loop.wav"
    assert body["source"]["authorized"] is True
    assert body["audio"]["duration_seconds"] == pytest.approx(4.0, abs=0.25)
    assert body["audio"]["chord_estimates"]
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
    client = TestClient(api.app)

    response = client.post(
        "/references/analyze",
        files={"file": ("broken.wav", b"not really a wav", "audio/wav")},
    )

    assert response.status_code == 422
    assert "analyze" in response.json()["detail"].lower()
