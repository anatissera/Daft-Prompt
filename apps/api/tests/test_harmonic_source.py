"""Tests for the harmonic-source builder."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from music_assistant.infrastructure.mir.harmonic_source import build_harmonic_source
from music_assistant.ports.stem_separator import SeparatedStem


def _stem(name: str, role: str, path: str) -> SeparatedStem:
    return SeparatedStem(name=name, role=role, path=path, confidence=1.0)


def test_prefers_bass_and_other_stems_when_available(tmp_path):
    signals = {
        "/fake/drums.wav": np.full(4, 0.9, dtype=np.float32),
        "/fake/bass.wav": np.array([0.1, 0.2, 0.3, 0.4], dtype=np.float32),
        "/fake/vocals.wav": np.full(4, 0.7, dtype=np.float32),
        "/fake/other.wav": np.array([0.05, 0.05, 0.05, 0.05], dtype=np.float32),
    }
    written: dict[str, np.ndarray] = {}

    def loader(path: str, sample_rate: int) -> np.ndarray:
        return signals[path]

    def writer(path: str, samples: np.ndarray, sample_rate: int) -> None:
        written[path] = samples

    stems = [
        _stem("drums", "percussion", "/fake/drums.wav"),
        _stem("bass", "bass", "/fake/bass.wav"),
        _stem("vocals", "vocal", "/fake/vocals.wav"),
        _stem("other", "harmony", "/fake/other.wav"),
    ]
    output = tmp_path / "harmonic.wav"

    result = build_harmonic_source(
        stems, output, audio_loader=loader, audio_writer=writer
    )

    assert result.source_kind == "stems_bass_other"
    assert result.confidence_adjustment == 0.0
    assert result.notes == []
    # Only bass + other are summed; drums and vocals are excluded.
    expected = signals["/fake/bass.wav"] + signals["/fake/other.wav"]
    np.testing.assert_allclose(written[str(output)], expected)


def test_hpss_fallback_emits_note_and_lowers_confidence(tmp_path):
    sample_rate = 22_050
    time = np.linspace(0.0, 1.0, sample_rate, endpoint=False)
    harmonic = 0.4 * np.sin(2 * np.pi * 220 * time)
    percussive = np.zeros_like(harmonic)
    percussive[::1000] = 0.8  # sparse clicks
    mix = (harmonic + percussive).astype(np.float32)

    def loader(path: str, sr: int) -> np.ndarray:
        return mix

    stems = [_stem("mix", "mix", "/fake/mix.wav")]
    output = tmp_path / "harmonic.wav"

    result = build_harmonic_source(stems, output, audio_loader=loader)

    assert result.source_kind == "hpss_harmonic"
    assert result.confidence_adjustment < 0.0
    assert len(result.notes) == 1
    assert result.notes[0].severity == "warning"
    assert Path(result.path).exists()


def test_missing_other_stem_falls_back_to_hpss(tmp_path):
    sample_rate = 22_050
    time = np.linspace(0.0, 1.0, sample_rate, endpoint=False)
    mix = (0.4 * np.sin(2 * np.pi * 196 * time)).astype(np.float32)

    stems = [
        _stem("bass", "bass", "/fake/bass.wav"),
        _stem("mix", "mix", "/fake/mix.wav"),
    ]
    output = tmp_path / "harmonic.wav"

    result = build_harmonic_source(
        stems, output, audio_loader=lambda path, sr: mix
    )

    # bass alone is not enough (other is required); HPSS fallback used instead.
    assert result.source_kind == "hpss_harmonic"


def test_raises_when_no_stems(tmp_path):
    with pytest.raises(ValueError, match="No stems"):
        build_harmonic_source([], tmp_path / "harmonic.wav")
