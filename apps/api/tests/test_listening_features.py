"""Deep-listening features (plans/deep-music-analysis.md Tracks 2/4/5):
timbre, bar-aligned dynamics with build/drop events, and groove. Pure-function
tests run on synthetic summaries; one end-to-end test exercises the real
librosa pass on generated audio."""

from __future__ import annotations

import numpy as np
import pytest

from music_assistant.infrastructure.mir.listening_features import (
    RawStemListening,
    analyze_stem_listening,
    dynamics_profile,
    extract_stem_listening,
    rhythm_profile,
    timbre_profile,
)


# ---- Track 2: timbre ---------------------------------------------------------


def test_low_centroid_low_flatness_reads_dark_and_tonal():
    raw = RawStemListening(centroid_hz=400.0, flatness=0.01, band_split=[0.7, 0.2, 0.1])
    timbre = timbre_profile(raw)
    assert timbre.brightness == "dark"
    assert timbre.noisiness == "tonal"
    assert timbre.band_balance == "low-heavy"
    assert "dark" in timbre.interpretation
    assert timbre.confidence > 0.0


def test_high_centroid_high_flatness_reads_bright_and_noisy():
    raw = RawStemListening(centroid_hz=5_000.0, flatness=0.6, band_split=[0.1, 0.3, 0.6])
    timbre = timbre_profile(raw)
    assert timbre.brightness == "bright"
    assert timbre.noisiness == "noisy"
    assert timbre.band_balance == "high-heavy"


def test_even_band_split_reads_balanced():
    raw = RawStemListening(centroid_hz=1_500.0, flatness=0.1, band_split=[0.34, 0.33, 0.33])
    assert timbre_profile(raw).band_balance == "balanced"


def test_silent_stem_gets_zero_timbre_confidence():
    assert timbre_profile(RawStemListening()).confidence == 0.0


# ---- Track 4: dynamics -------------------------------------------------------


def test_sustained_rise_is_detected_as_build():
    levels = [0.1, 0.2, 0.35, 0.5, 0.7, 0.9, 0.9, 0.9]
    dynamics = dynamics_profile(levels)
    builds = [e for e in dynamics.events if e.kind == "build"]
    assert builds and builds[0].start_bar == 1  # bars are 1-based like ChordSpan
    assert "builds" in dynamics.interpretation


def test_sudden_fall_is_detected_as_drop():
    levels = [0.9, 0.95, 1.0, 0.2, 0.25, 0.3]
    dynamics = dynamics_profile(levels)
    drops = [e for e in dynamics.events if e.kind == "drop"]
    assert drops and drops[0].end_bar == 4  # the fall lands on 1-based bar 4
    assert "drops" in dynamics.interpretation


def test_dynamics_points_are_one_based():
    dynamics = dynamics_profile([0.5, 0.6, 0.7])
    assert [p.bar for p in dynamics.points] == [1, 2, 3]


def test_steady_curve_has_no_events():
    dynamics = dynamics_profile([0.5, 0.52, 0.48, 0.5, 0.51, 0.49, 0.5, 0.5])
    assert dynamics.events == []
    assert "steady" in dynamics.interpretation


def test_levels_are_normalized_to_the_peak():
    dynamics = dynamics_profile([1.0, 2.0, 4.0])
    assert max(p.level for p in dynamics.points) == 1.0


def test_long_songs_downsample_to_the_point_budget():
    dynamics = dynamics_profile([0.5] * 200)
    assert len(dynamics.points) <= 64


def test_empty_curve_is_harmless():
    dynamics = dynamics_profile([])
    assert dynamics.points == []
    assert dynamics.confidence == 0.0


# ---- Track 5: groove ---------------------------------------------------------

BEATS = [float(i) * 0.5 for i in range(17)]  # 120 BPM, 8 seconds, 4 bars of 4/4


def test_onsets_on_the_beat_read_straight_and_unsyncopated():
    onsets = [b for b in BEATS[:-1]]
    rhythm = rhythm_profile(onsets, BEATS, num_bars=4)
    assert rhythm.feel == "straight"
    assert rhythm.syncopation == 0.0


def test_triplet_offbeats_read_swung():
    onsets = []
    for beat in BEATS[:-1]:
        onsets.append(beat)          # on the beat
        onsets.append(beat + 0.33)   # ~2:1 triplet swing position
    rhythm = rhythm_profile(onsets, BEATS, num_bars=4)
    assert rhythm.feel == "swung"
    assert rhythm.swing_ratio is not None and rhythm.swing_ratio >= 1.35
    assert rhythm.syncopation > 0.3


def test_straight_eighths_have_swing_ratio_near_one():
    onsets = []
    for beat in BEATS[:-1]:
        onsets.append(beat)
        onsets.append(beat + 0.25)   # exact straight eighth
    rhythm = rhythm_profile(onsets, BEATS, num_bars=4)
    assert rhythm.feel == "straight"
    assert rhythm.swing_ratio is not None and rhythm.swing_ratio == pytest.approx(1.0, abs=0.15)


def test_density_labels():
    sparse = rhythm_profile([0.1, 2.1], BEATS, num_bars=4)
    busy = rhythm_profile([i * 0.1 for i in range(79)], BEATS, num_bars=4)
    assert sparse.density == "sparse"
    assert busy.density == "busy"


def test_no_onsets_is_harmless():
    rhythm = rhythm_profile([], BEATS, num_bars=4)
    assert rhythm.confidence == 0.0


# ---- Orchestration seam ------------------------------------------------------


def test_analyze_stem_listening_uses_injected_extractor_and_skips_failures():
    def extractor(path, bar_times, end_seconds):
        if "bass" in path:
            raise RuntimeError("corrupt stem")
        return RawStemListening(
            rms_by_bar=[0.1, 0.5, 0.9, 1.0],
            onset_times=[0.0, 0.5, 1.0],
            centroid_hz=900.0,
            flatness=0.02,
            band_split=[0.6, 0.3, 0.1],
        )

    result = analyze_stem_listening(
        {"drums": "/tmp/drums.wav", "bass": "/tmp/bass.wav"},
        bar_times=[0.0, 2.0, 4.0, 6.0],
        beat_times=BEATS,
        end_seconds=8.0,
        extractor=extractor,
    )
    assert set(result) == {"drums"}  # bass failed and was skipped, not raised
    listening = result["drums"]
    assert listening.timbre.brightness == "dark"
    assert listening.dynamics.points
    assert listening.rhythm.onsets_per_bar is not None


# ---- End-to-end librosa pass on synthetic audio -------------------------------


def test_extract_stem_listening_on_synthetic_audio(tmp_path):
    soundfile = pytest.importorskip("soundfile")
    sr = 22_050
    time = np.linspace(0.0, 4.0, 4 * sr, endpoint=False)
    tone = (0.4 * np.sin(2 * np.pi * 220.0 * time)).astype(np.float32)
    tone[: sr // 2] *= 0.05  # quiet first half-bar so the curve moves
    path = tmp_path / "tone.wav"
    soundfile.write(path, tone, sr)

    raw = extract_stem_listening(str(path), bar_times=[0.0, 2.0], end_seconds=4.0)

    assert len(raw.rms_by_bar) == 2
    assert raw.centroid_hz < 1_000.0  # pure low tone reads dark
    assert raw.flatness < 0.05  # and tonal
    assert len(raw.band_split) == 3 and raw.band_split[1] > 0.5  # 220 Hz sits in the mid band

    timbre = timbre_profile(raw)
    assert timbre.brightness == "dark"
    assert timbre.noisiness == "tonal"


# ---- Mix-level timbre ----------------------------------------------------------


def test_analyze_mix_timbre_uses_injected_extractor():
    from music_assistant.infrastructure.mir.listening_features import analyze_mix_timbre

    raw = RawStemListening(centroid_hz=3_000.0, flatness=0.4, band_split=[0.2, 0.3, 0.5])
    timbre = analyze_mix_timbre(
        "/tmp/mix.wav", [0.0, 2.0], 4.0, extractor=lambda path, bars, end: raw
    )
    assert timbre is not None
    assert timbre.brightness == "bright"
    assert timbre.noisiness == "noisy"


def test_analyze_mix_timbre_returns_none_on_failure_or_silence():
    from music_assistant.infrastructure.mir.listening_features import analyze_mix_timbre

    def broken(path, bars, end):
        raise RuntimeError("unreadable")

    assert analyze_mix_timbre("/tmp/mix.wav", [0.0], 2.0, extractor=broken) is None
    silent = lambda path, bars, end: RawStemListening()  # centroid 0 → zero confidence
    assert analyze_mix_timbre("/tmp/mix.wav", [0.0], 2.0, extractor=silent) is None
