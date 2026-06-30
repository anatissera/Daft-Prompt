"""Tests for the local librosa-based audio analyzer."""

from __future__ import annotations

import math
import wave
from pathlib import Path

import numpy as np
import pytest

from music_assistant.domain.audio_profile import ReferenceSource
from music_assistant.infrastructure.mir.librosa_analyzer import LibrosaAnalyzer


def _write_synthetic_chord_loop(path: Path, duration_seconds: float = 8.0) -> None:
    sample_rate = 22_050
    total_samples = int(sample_rate * duration_seconds)
    samples = np.zeros(total_samples, dtype=np.float32)
    chord_frequencies = [
        (261.63, 329.63, 392.00),  # C
        (220.00, 261.63, 329.63),  # Am
        (174.61, 220.00, 261.63),  # F
        (196.00, 246.94, 293.66),  # G
    ]
    beat_interval = 0.5

    for index in range(total_samples):
        t = index / sample_rate
        chord = chord_frequencies[int(t // 2.0) % len(chord_frequencies)]
        tone = sum(math.sin(2.0 * math.pi * frequency * t) for frequency in chord)
        beat_position = t % beat_interval
        pulse = 1.0 if beat_position < 0.08 else 0.55
        section_gain = 0.45 if t < duration_seconds / 2.0 else 0.85
        samples[index] = 0.12 * tone * pulse * section_gain

    clipped = np.clip(samples, -1.0, 1.0)
    pcm = (clipped * 32767).astype(np.int16)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes(pcm.tobytes())


def test_analyze_local_audio_returns_compact_reference_profile(tmp_path: Path):
    audio_path = tmp_path / "synthetic_loop.wav"
    _write_synthetic_chord_loop(audio_path)
    source = ReferenceSource(
        reference_id="ref_synthetic",
        kind="local",
        label="synthetic safe test loop",
        uri=str(audio_path),
        authorized=True,
    )

    profile = LibrosaAnalyzer().analyze(source)

    assert profile.reference_id == "ref_synthetic"
    assert profile.source == source
    assert profile.audio is not None
    assert profile.audio.duration_seconds == pytest.approx(8.0, abs=0.2)
    assert profile.audio.tempo_bpm is not None
    assert 0.0 <= profile.audio.tempo_confidence <= 1.0
    assert profile.audio.key is not None
    assert 0.0 <= profile.audio.key_confidence <= 1.0
    assert 0.0 <= profile.audio.overall_confidence <= 1.0
    assert profile.audio.energy_curve
    assert all(0.0 <= point.energy <= 1.0 for point in profile.audio.energy_curve)
    assert profile.audio.sections
    assert profile.audio.chord_estimates
    assert len(profile.audio.chord_estimates) >= 4
    assert len({tuple(chord.chords) for chord in profile.audio.chord_estimates}) > 1
    assert all(chord.is_probable for chord in profile.audio.chord_estimates)
    assert {
        chord.confidence_label for chord in profile.audio.chord_estimates
    } <= {"low", "medium", "high"}
    assert "Probably" in profile.audio.chord_estimates[0].label
    assert "probably" in profile.summary.lower()


def test_analyze_accepts_file_uri(tmp_path: Path):
    audio_path = tmp_path / "synthetic_loop.wav"
    _write_synthetic_chord_loop(audio_path, duration_seconds=4.0)
    source = ReferenceSource(
        reference_id="ref_file_uri",
        kind="local",
        label="synthetic file uri",
        uri=audio_path.as_uri(),
        authorized=True,
    )

    profile = LibrosaAnalyzer().analyze(source)

    assert profile.reference_id == "ref_file_uri"
    assert profile.audio is not None
    assert profile.audio.duration_seconds == pytest.approx(4.0, abs=0.2)


def test_analyze_rejects_non_local_sources():
    source = ReferenceSource(
        reference_id="ref_remote",
        kind="direct_url",
        label="remote audio",
        uri="https://example.com/song.wav",
        authorized=True,
    )

    with pytest.raises(ValueError, match="local audio path or file:// URI"):
        LibrosaAnalyzer().analyze(source)
