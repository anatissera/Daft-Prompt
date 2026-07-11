"""Build a harmonic-analysis audio source from stems or an HPSS fallback.

Chord and key estimation work best on the harmonic content of a song. When
Demucs stems are available we mix ``bass + other`` (dropping drums and vocals,
which distort chroma). When stems are unavailable we fall back to a librosa HPSS
harmonic component of the mix, and lower confidence so downstream estimates stay
honest.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Literal

import numpy as np
from pydantic import BaseModel, Field

from music_assistant.domain.audio_profile import AnalysisNote
from music_assistant.infrastructure.mir.librosa_analyzer import _prepare_librosa_import
from music_assistant.ports.stem_separator import SeparatedStem


SAMPLE_RATE = 22_050

# (path, sample_rate) -> mono float32 samples
AudioLoader = Callable[[str, int], np.ndarray]
# (path, samples, sample_rate) -> None
AudioWriter = Callable[[str, np.ndarray, int], None]


class HarmonicSource(BaseModel):
    path: str
    source_kind: Literal["stems_bass_other", "hpss_harmonic", "mix"]
    confidence_adjustment: float = 0.0
    notes: list[AnalysisNote] = Field(default_factory=list)


def build_harmonic_source(
    stems: list[SeparatedStem],
    output_path: Path | str,
    *,
    sample_rate: int = SAMPLE_RATE,
    audio_loader: AudioLoader | None = None,
    audio_writer: AudioWriter | None = None,
) -> HarmonicSource:
    """Produce a harmonic-only audio file for key/chord estimation.

    Prefers ``bass + other`` stems; otherwise builds an HPSS harmonic component
    from the mix; otherwise falls back to the raw mix with low confidence.
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    load = audio_loader or _default_load
    write = audio_writer or _default_write

    by_name = {stem.name: stem for stem in stems}
    bass = by_name.get("bass")
    other = by_name.get("other")

    if bass is not None and other is not None:
        mixed = _sum_signals(
            [load(bass.path, sample_rate), load(other.path, sample_rate)]
        )
        write(str(output_path), mixed, sample_rate)
        return HarmonicSource(
            path=str(output_path),
            source_kind="stems_bass_other",
            confidence_adjustment=0.0,
        )

    mix = by_name.get("mix") or (stems[0] if stems else None)
    if mix is None:
        raise ValueError("No stems available to build a harmonic source")

    mix_audio = load(mix.path, sample_rate)
    try:
        harmonic = _hpss_harmonic(mix_audio)
    except Exception:
        write(str(output_path), mix_audio, sample_rate)
        return HarmonicSource(
            path=str(output_path),
            source_kind="mix",
            confidence_adjustment=-0.35,
            notes=[
                AnalysisNote(
                    code="harmonic_source_raw_mix",
                    message=(
                        "Could not isolate a harmonic source; analyzing the raw "
                        "mix. Harmony confidence is low."
                    ),
                    severity="warning",
                )
            ],
        )

    write(str(output_path), harmonic, sample_rate)
    return HarmonicSource(
        path=str(output_path),
        source_kind="hpss_harmonic",
        confidence_adjustment=-0.2,
        notes=[
            AnalysisNote(
                code="harmonic_source_hpss_fallback",
                message=(
                    "Separated bass/other stems were unavailable; used the HPSS "
                    "harmonic component of the mix. Harmony confidence is reduced."
                ),
                severity="warning",
            )
        ],
    )


def _sum_signals(signals: list[np.ndarray]) -> np.ndarray:
    length = max((len(signal) for signal in signals), default=0)
    accumulator = np.zeros(length, dtype=np.float32)
    for signal in signals:
        accumulator[: len(signal)] += signal.astype(np.float32)
    peak = float(np.max(np.abs(accumulator))) if accumulator.size else 0.0
    if peak > 1.0:
        accumulator = accumulator / peak
    return accumulator


def _hpss_harmonic(samples: np.ndarray) -> np.ndarray:
    _prepare_librosa_import()
    import librosa

    harmonic, _ = librosa.effects.hpss(samples)
    return harmonic.astype(np.float32)


def _default_load(path: str, sample_rate: int) -> np.ndarray:
    _prepare_librosa_import()
    import librosa

    samples, _ = librosa.load(path, sr=sample_rate, mono=True)
    return samples.astype(np.float32)


def _default_write(path: str, samples: np.ndarray, sample_rate: int) -> None:
    import soundfile as sf

    sf.write(path, samples, sample_rate)
