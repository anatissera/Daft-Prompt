"""Deep-listening features per stem: timbre, groove, and bar-aligned dynamics.

Implements the light half of plans/deep-music-analysis.md (Tracks 2, 4, 5 —
spectral timbre, per-stem dynamics with build/drop callouts, and swing/
syncopation groove). The heavy tracks (basic-pitch transcription, movement)
stay deferred; nothing here needs more than one librosa pass per stem.

Split follows the repo's MIR pattern: `extract_stem_listening` is the only
function that touches audio (injectable in tests via the `extractor` seam on
`analyze_stem_listening`), while `timbre_profile` / `dynamics_profile` /
`rhythm_profile` are pure functions over the compact `RawStemListening`
summary, so every musical decision is unit-testable without audio files.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from collections.abc import Callable

from music_assistant.domain.audio_profile import (
    DynamicsEvent,
    DynamicsPoint,
    RhythmProfile,
    StemDynamics,
    TimbreProfile,
)

# Timbre label thresholds (mean spectral centroid, Hz / spectral flatness).
BRIGHTNESS_DARK_HZ = 1_000.0
BRIGHTNESS_WARM_HZ = 2_200.0
FLATNESS_TONAL = 0.05
FLATNESS_MIXED = 0.30
BAND_HEAVY_FRACTION = 0.5

# Dynamics event detection over the 0..1 bar-level curve.
BUILD_MIN_BARS = 3
BUILD_MIN_RISE = 0.3
BUILD_DIP_TOLERANCE = 0.02
DROP_MIN_FALL = 0.4

# Groove thresholds.
DENSITY_SPARSE = 2.0   # onsets per bar
DENSITY_BUSY = 6.0
SWING_MIN_RATIO = 1.35
SWING_MIN_OFFBEATS = 4
OFFBEAT_PHASE_MARGIN = 0.25  # phase distance from any beat to count as offbeat

MAX_DYNAMICS_POINTS = 64


@dataclass
class RawStemListening:
    """Compact per-stem summary: the only thing the audio pass produces."""

    rms_by_bar: list[float] = field(default_factory=list)
    onset_times: list[float] = field(default_factory=list)  # seconds
    centroid_hz: float = 0.0
    flatness: float = 0.0
    band_split: list[float] = field(default_factory=list)  # low/mid/high fractions


@dataclass
class StemListening:
    timbre: TimbreProfile
    rhythm: RhythmProfile
    dynamics: StemDynamics


StemListeningExtractor = Callable[[str, list[float], float], RawStemListening]


def analyze_stem_listening(
    stem_paths: dict[str, str],
    bar_times: list[float],
    beat_times: list[float],
    end_seconds: float,
    *,
    extractor: StemListeningExtractor | None = None,
) -> dict[str, StemListening]:
    """Timbre + groove + dynamics per stem. Stems that fail extraction are
    skipped (never raised) so one bad stem can't sink the analysis run."""
    extract = extractor or extract_stem_listening
    out: dict[str, StemListening] = {}
    for name in ("vocals", "drums", "bass", "other"):
        path = stem_paths.get(name)
        if path is None:
            continue
        try:
            raw = extract(path, bar_times, end_seconds)
        except Exception:
            continue
        out[name] = StemListening(
            timbre=timbre_profile(raw),
            rhythm=rhythm_profile(raw.onset_times, beat_times, len(bar_times)),
            dynamics=dynamics_profile(raw.rms_by_bar),
        )
    return out


def extract_stem_listening(
    path: str, bar_times: list[float], end_seconds: float
) -> RawStemListening:
    """One librosa pass over a stem → compact summary. Same lazy-import
    pattern as the rest of the MIR package."""
    from music_assistant.infrastructure.mir.librosa_analyzer import (
        HOP_LENGTH,
        SAMPLE_RATE,
        _prepare_librosa_import,
    )

    _prepare_librosa_import()
    import librosa
    import numpy as np

    samples, sr = librosa.load(path, sr=SAMPLE_RATE, mono=True)
    stft = np.abs(librosa.stft(samples, hop_length=HOP_LENGTH))
    frame_times = librosa.frames_to_time(
        np.arange(stft.shape[1]), sr=sr, hop_length=HOP_LENGTH
    )
    rms = librosa.feature.rms(S=stft)[0]
    centroid = librosa.feature.spectral_centroid(S=stft, sr=sr)[0]
    flatness = librosa.feature.spectral_flatness(S=stft)[0]
    onsets = librosa.onset.onset_detect(
        y=samples, sr=sr, hop_length=HOP_LENGTH, units="time"
    )
    frequencies = librosa.fft_frequencies(sr=sr, n_fft=(stft.shape[0] - 1) * 2)

    # Energy-weighted timbre summary so silence doesn't drag the centroid down.
    weights = rms / max(float(np.sum(rms)), 1e-9)
    mean_centroid = float(np.sum(centroid * weights))
    mean_flatness = float(np.sum(flatness * weights))

    total = float(np.sum(stft))
    if total > 0.0:
        bands = [(0.0, 180.0), (180.0, 2_000.0), (2_000.0, float("inf"))]
        band_split = [
            float(np.sum(stft[(frequencies >= low) & (frequencies < high)])) / total
            for low, high in bands
        ]
    else:
        band_split = [0.0, 0.0, 0.0]

    rms_by_bar: list[float] = []
    for index, start in enumerate(bar_times):
        end = bar_times[index + 1] if index + 1 < len(bar_times) else end_seconds
        mask = (frame_times >= start) & (frame_times < end)
        bar = rms[mask]
        rms_by_bar.append(float(np.mean(bar)) if bar.size else 0.0)

    return RawStemListening(
        rms_by_bar=rms_by_bar,
        onset_times=[float(t) for t in onsets],
        centroid_hz=mean_centroid,
        flatness=mean_flatness,
        band_split=band_split,
    )


def analyze_mix_timbre(
    audio_path: str,
    bar_times: list[float],
    end_seconds: float,
    *,
    extractor: StemListeningExtractor | None = None,
) -> "TimbreProfile | None":
    """Mix-level timbre from the original audio (Track 2's 'and the mix').

    Returns None instead of raising so the analyzer can degrade gracefully."""
    extract = extractor or extract_stem_listening
    try:
        raw = extract(audio_path, bar_times, end_seconds)
    except Exception:
        return None
    profile = timbre_profile(raw)
    return profile if profile.confidence > 0.0 else None


# ---- Track 2: timbre --------------------------------------------------------


def timbre_profile(raw: RawStemListening) -> TimbreProfile:
    if raw.centroid_hz <= BRIGHTNESS_DARK_HZ:
        brightness = "dark"
    elif raw.centroid_hz <= BRIGHTNESS_WARM_HZ:
        brightness = "warm"
    else:
        brightness = "bright"

    if raw.flatness <= FLATNESS_TONAL:
        noisiness = "tonal"
    elif raw.flatness <= FLATNESS_MIXED:
        noisiness = "mixed"
    else:
        noisiness = "noisy"

    band_balance = "balanced"
    if len(raw.band_split) == 3 and max(raw.band_split) >= BAND_HEAVY_FRACTION:
        band_balance = ("low-heavy", "mid-heavy", "high-heavy")[
            raw.band_split.index(max(raw.band_split))
        ]

    interpretation = (
        f"Likely {brightness} and {noisiness}"
        + (f", {band_balance}" if band_balance != "balanced" else ", spectrally balanced")
        + " — heard from spectral centroid, flatness, and band energy."
    )
    return TimbreProfile(
        brightness=brightness,
        noisiness=noisiness,
        band_balance=band_balance,
        centroid_hz=round(raw.centroid_hz, 1),
        flatness=min(max(raw.flatness, 0.0), 1.0),
        band_split=[round(b, 3) for b in raw.band_split[:3]],
        interpretation=interpretation,
        confidence=0.6 if raw.centroid_hz > 0.0 else 0.0,
    )


# ---- Track 4: bar-aligned dynamics ------------------------------------------


def dynamics_profile(rms_by_bar: list[float]) -> StemDynamics:
    """Bars are 1-based in the output, matching ChordSpan / StructuralSection."""
    if not rms_by_bar:
        return StemDynamics(interpretation="No loudness curve available.", confidence=0.0)

    peak = max(rms_by_bar)
    levels = [value / peak if peak > 0.0 else 0.0 for value in rms_by_bar]
    events = _detect_dynamics_events(levels)

    stride = max(1, math.ceil(len(levels) / MAX_DYNAMICS_POINTS))
    points = [
        DynamicsPoint(bar=index + 1, level=round(level, 3))
        for index, level in enumerate(levels)
        if index % stride == 0
    ]

    if events:
        fragments = [
            (
                f"builds through bars {e.start_bar}-{e.end_bar}"
                if e.kind == "build"
                else f"drops at bar {e.end_bar}"
            )
            for e in events[:4]
        ]
        interpretation = "Loudness " + "; ".join(fragments) + " (bar-aligned estimate)."
    else:
        interpretation = "Loudness stays fairly steady across the song (bar-aligned estimate)."

    return StemDynamics(
        points=points,
        events=events[:12],
        interpretation=interpretation,
        confidence=min(1.0, len(levels) / 8.0) * 0.7,
    )


def _detect_dynamics_events(levels: list[float]) -> list[DynamicsEvent]:
    """Detection runs on 0-based list indexes; emitted bars are 1-based."""
    events: list[DynamicsEvent] = []
    start = 0
    for index in range(1, len(levels) + 1):
        rising = (
            index < len(levels)
            and levels[index] >= levels[index - 1] - BUILD_DIP_TOLERANCE
        )
        if rising:
            continue
        length = index - start
        rise = levels[index - 1] - levels[start]
        if length >= BUILD_MIN_BARS and rise >= BUILD_MIN_RISE:
            events.append(DynamicsEvent(kind="build", start_bar=start + 1, end_bar=index))
        start = index
    for index in range(1, len(levels)):
        if levels[index - 1] - levels[index] >= DROP_MIN_FALL:
            events.append(DynamicsEvent(kind="drop", start_bar=index, end_bar=index + 1))
    events.sort(key=lambda e: (e.start_bar, e.end_bar))
    return events


# ---- Track 5: groove --------------------------------------------------------


def rhythm_profile(
    onset_times: list[float], beat_times: list[float], num_bars: int
) -> RhythmProfile:
    if len(beat_times) < 2 or not onset_times:
        return RhythmProfile(interpretation="Not enough onsets for a groove read.", confidence=0.0)

    phases = _onset_beat_phases(onset_times, beat_times)
    if not phases:
        return RhythmProfile(interpretation="Not enough onsets for a groove read.", confidence=0.0)

    offbeat_phases = [p for p in phases if min(p, 1.0 - p) > OFFBEAT_PHASE_MARGIN]
    syncopation = len(offbeat_phases) / len(phases)

    swing_ratio = None
    feel = "straight"
    if len(offbeat_phases) >= SWING_MIN_OFFBEATS:
        mean_off = sum(offbeat_phases) / len(offbeat_phases)
        mean_off = min(max(mean_off, 0.2), 0.8)
        swing_ratio = round(mean_off / (1.0 - mean_off), 2)
        if swing_ratio >= SWING_MIN_RATIO:
            feel = "swung"

    onsets_per_bar = len(onset_times) / max(num_bars, 1)
    if onsets_per_bar < DENSITY_SPARSE:
        density = "sparse"
    elif onsets_per_bar < DENSITY_BUSY:
        density = "moderate"
    else:
        density = "busy"

    fragments = [feel, density]
    if syncopation >= 0.35:
        fragments.append("syncopated")
    interpretation = (
        "Feels " + ", ".join(fragments)
        + f" — {onsets_per_bar:.1f} onsets/bar against the beat grid."
    )
    return RhythmProfile(
        feel=feel,
        swing_ratio=swing_ratio,
        syncopation=round(syncopation, 3),
        density=density,
        onsets_per_bar=round(onsets_per_bar, 2),
        interpretation=interpretation,
        confidence=min(1.0, len(onset_times) / 16.0) * 0.8,
    )


def _onset_beat_phases(onset_times: list[float], beat_times: list[float]) -> list[float]:
    """Position of each onset within its beat, 0.0 = on the beat."""
    phases: list[float] = []
    for onset in onset_times:
        if onset < beat_times[0] or onset >= beat_times[-1]:
            continue
        for index in range(len(beat_times) - 1):
            start, end = beat_times[index], beat_times[index + 1]
            if start <= onset < end and end > start:
                phases.append((onset - start) / (end - start))
                break
    return phases
