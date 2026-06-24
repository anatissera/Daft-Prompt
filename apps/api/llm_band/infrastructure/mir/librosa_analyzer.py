"""Local audio analyzer powered by librosa."""

from __future__ import annotations

from pathlib import Path
from urllib.parse import unquote, urlparse

import numpy as np

from llm_band.domain.audio_profile import (
    AudioProfile,
    ChordEstimate,
    EnergyPoint,
    ReferenceProfile,
    ReferenceSource,
    SectionProfile,
)


SAMPLE_RATE = 22_050
HOP_LENGTH = 512
MAJOR_KEY_PROFILE = np.array(
    [6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88]
)
MINOR_KEY_PROFILE = np.array(
    [6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17]
)
NOTE_NAMES = ["C", "C#", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B"]


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _cosine_similarity(left: np.ndarray, right: np.ndarray) -> float:
    denominator = float(np.linalg.norm(left) * np.linalg.norm(right))
    if denominator == 0.0:
        return 0.0
    return float(np.dot(left, right) / denominator)


def _resolve_local_path(uri: str) -> Path:
    parsed = urlparse(uri)
    if parsed.scheme == "":
        return Path(uri).expanduser()
    if parsed.scheme == "file":
        return Path(unquote(parsed.path)).expanduser()
    raise ValueError("LibrosaAnalyzer requires a local audio path or file:// URI")


def _label_chord(root_index: int, quality: str) -> str:
    root = NOTE_NAMES[root_index]
    return root if quality == "major" else f"{root}m"


def _estimate_chord(chroma_vector: np.ndarray) -> tuple[str, float]:
    if not np.any(chroma_vector):
        return "unknown", 0.0

    scores: list[tuple[float, int, str]] = []
    for root_index in range(12):
        major_template = np.zeros(12)
        major_template[[root_index, (root_index + 4) % 12, (root_index + 7) % 12]] = 1.0
        minor_template = np.zeros(12)
        minor_template[[root_index, (root_index + 3) % 12, (root_index + 7) % 12]] = 1.0
        scores.append((_cosine_similarity(chroma_vector, major_template), root_index, "major"))
        scores.append((_cosine_similarity(chroma_vector, minor_template), root_index, "minor"))

    scores.sort(reverse=True)
    best_score, root_index, quality = scores[0]
    second_score = scores[1][0] if len(scores) > 1 else 0.0
    confidence = _clamp(0.25 + (best_score - second_score) * 1.5 + best_score * 0.35)
    return _label_chord(root_index, quality), min(confidence, 0.86)


def _estimate_key(chroma_vector: np.ndarray) -> tuple[str | None, float]:
    if not np.any(chroma_vector):
        return None, 0.0

    scores: list[tuple[float, int, str]] = []
    for tonic_index in range(12):
        scores.append(
            (
                _cosine_similarity(chroma_vector, np.roll(MAJOR_KEY_PROFILE, tonic_index)),
                tonic_index,
                "major",
            )
        )
        scores.append(
            (
                _cosine_similarity(chroma_vector, np.roll(MINOR_KEY_PROFILE, tonic_index)),
                tonic_index,
                "minor",
            )
        )

    scores.sort(reverse=True)
    best_score, tonic_index, mode = scores[0]
    second_score = scores[1][0] if len(scores) > 1 else 0.0
    confidence = _clamp(0.25 + (best_score - second_score) * 2.0 + best_score * 0.25)
    return f"{NOTE_NAMES[tonic_index]} {mode}", min(confidence, 0.92)


def _frame_range(start_seconds: float, end_seconds: float, frame_times: np.ndarray) -> np.ndarray:
    mask = (frame_times >= start_seconds) & (frame_times < end_seconds)
    if not np.any(mask):
        nearest = np.argmin(np.abs(frame_times - start_seconds))
        mask = np.zeros_like(frame_times, dtype=bool)
        mask[nearest] = True
    return mask


def _prepare_librosa_import() -> None:
    """Avoid numba cache writes that can fail in sandboxed/local Python installs."""
    try:
        import numba
    except ImportError:
        return

    if getattr(numba, "_llminem_cache_patch", False):
        return

    original_jit = numba.jit
    original_vectorize = numba.vectorize
    original_guvectorize = numba.guvectorize

    def drop_cache(kwargs: dict) -> dict:
        kwargs.pop("cache", None)
        return kwargs

    def jit_without_cache(*args, **kwargs):
        return original_jit(*args, **drop_cache(kwargs))

    def vectorize_without_cache(*args, **kwargs):
        return original_vectorize(*args, **drop_cache(kwargs))

    def guvectorize_without_cache(*args, **kwargs):
        return original_guvectorize(*args, **drop_cache(kwargs))

    numba.jit = jit_without_cache
    numba.vectorize = vectorize_without_cache
    numba.guvectorize = guvectorize_without_cache
    numba._llminem_cache_patch = True


class LibrosaAnalyzer:
    def analyze(self, source: ReferenceSource) -> ReferenceProfile:
        audio_path = _resolve_local_path(source.uri)
        _prepare_librosa_import()
        import librosa

        y, sr = librosa.load(audio_path, sr=SAMPLE_RATE, mono=True)
        duration_seconds = float(librosa.get_duration(y=y, sr=sr))

        tempo_bpm, tempo_confidence = self._estimate_tempo(librosa, y, sr)
        rms = librosa.feature.rms(y=y, frame_length=2048, hop_length=HOP_LENGTH)[0]
        frame_times = librosa.frames_to_time(
            np.arange(len(rms)), sr=sr, hop_length=HOP_LENGTH
        )
        normalized_energy = self._normalize_energy(rms)
        energy_curve = self._build_energy_curve(frame_times, normalized_energy)
        chroma = librosa.feature.chroma_stft(y=y, sr=sr, hop_length=HOP_LENGTH)
        chroma_vector = np.mean(chroma, axis=1) if chroma.size else np.zeros(12)
        key, key_confidence = _estimate_key(chroma_vector)
        sections = self._build_sections(duration_seconds, frame_times, normalized_energy)
        chord_estimates = self._build_chord_estimates(chroma, frame_times, sections)
        sections = [
            section.model_copy(
                update={
                    "chord_estimates": [
                        chord
                        for chord in chord_estimates
                        if chord.end_seconds > section.start_seconds
                        and chord.start_seconds < section.end_seconds
                    ]
                }
            )
            for section in sections
        ]
        confidence_values = [
            value
            for value in [
                tempo_confidence,
                key_confidence,
                *(point.confidence for point in energy_curve),
                *(chord.confidence for chord in chord_estimates),
            ]
            if value > 0.0
        ]
        overall_confidence = (
            float(np.mean(confidence_values)) if confidence_values else 0.0
        )
        audio = AudioProfile(
            duration_seconds=duration_seconds,
            tempo_bpm=tempo_bpm,
            tempo_confidence=tempo_confidence,
            key=key,
            key_confidence=key_confidence,
            confidence=overall_confidence,
            overall_confidence=overall_confidence,
            energy_curve=energy_curve,
            chord_estimates=chord_estimates,
            sections=sections,
        )
        return ReferenceProfile(
            reference_id=source.reference_id,
            source=source,
            audio=audio,
            summary=self._summarize(audio),
        )

    def _estimate_tempo(self, librosa, y: np.ndarray, sr: int) -> tuple[float | None, float]:
        tempo, beat_times = librosa.beat.beat_track(
            y=y, sr=sr, hop_length=HOP_LENGTH, units="time"
        )
        tempo_value = float(np.asarray(tempo).reshape(-1)[0]) if np.size(tempo) else 0.0
        if tempo_value <= 0.0:
            tempo_value = 120.0
            confidence = 0.15
        elif len(beat_times) >= 4:
            intervals = np.diff(beat_times)
            mean_interval = float(np.mean(intervals))
            variation = float(np.std(intervals) / mean_interval) if mean_interval else 1.0
            confidence = _clamp(0.9 - variation)
        else:
            confidence = 0.35
        return round(tempo_value, 2), confidence

    def _normalize_energy(self, rms: np.ndarray) -> np.ndarray:
        if rms.size == 0:
            return np.array([0.0])
        maximum = float(np.max(rms))
        if maximum == 0.0:
            return np.zeros_like(rms)
        return np.clip(rms / maximum, 0.0, 1.0)

    def _build_energy_curve(
        self, frame_times: np.ndarray, normalized_energy: np.ndarray
    ) -> list[EnergyPoint]:
        if normalized_energy.size == 0:
            return [EnergyPoint(time_seconds=0.0, energy=0.0, confidence=0.5)]

        target_points = min(32, max(1, normalized_energy.size))
        indexes = np.linspace(0, normalized_energy.size - 1, target_points, dtype=int)
        return [
            EnergyPoint(
                time_seconds=round(float(frame_times[index]), 3),
                energy=round(float(normalized_energy[index]), 4),
                confidence=0.75,
            )
            for index in indexes
        ]

    def _build_sections(
        self,
        duration_seconds: float,
        frame_times: np.ndarray,
        normalized_energy: np.ndarray,
    ) -> list[SectionProfile]:
        if duration_seconds <= 0.0:
            return [
                SectionProfile(
                    name="loop",
                    start_seconds=0.0,
                    end_seconds=0.0,
                    confidence=0.3,
                    energy=0.0,
                    energy_confidence=0.3,
                )
            ]
        if duration_seconds < 6.0 or normalized_energy.size < 4:
            return [
                SectionProfile(
                    name="loop",
                    start_seconds=0.0,
                    end_seconds=duration_seconds,
                    confidence=0.65,
                    energy=round(float(np.mean(normalized_energy)), 4),
                    energy_confidence=0.7,
                )
            ]

        half_index = len(normalized_energy) // 2
        first_energy = float(np.mean(normalized_energy[:half_index]))
        second_energy = float(np.mean(normalized_energy[half_index:]))
        if abs(second_energy - first_energy) < 0.12:
            return [
                SectionProfile(
                    name="loop",
                    start_seconds=0.0,
                    end_seconds=duration_seconds,
                    confidence=0.6,
                    energy=round(float(np.mean(normalized_energy)), 4),
                    energy_confidence=0.7,
                )
            ]

        boundary = float(frame_times[half_index]) if frame_times.size else duration_seconds / 2.0
        return [
            SectionProfile(
                name="section_a",
                start_seconds=0.0,
                end_seconds=boundary,
                confidence=0.55,
                energy=round(first_energy, 4),
                energy_confidence=0.7,
            ),
            SectionProfile(
                name="section_b",
                start_seconds=boundary,
                end_seconds=duration_seconds,
                confidence=0.55,
                energy=round(second_energy, 4),
                energy_confidence=0.7,
            ),
        ]

    def _build_chord_estimates(
        self,
        chroma: np.ndarray,
        frame_times: np.ndarray,
        sections: list[SectionProfile],
    ) -> list[ChordEstimate]:
        if chroma.size == 0 or not sections:
            return []

        estimates: list[ChordEstimate] = []
        for section in sections:
            mask = _frame_range(section.start_seconds, section.end_seconds, frame_times)
            chroma_vector = np.mean(chroma[:, mask], axis=1)
            chord, confidence = _estimate_chord(chroma_vector)
            if chord == "unknown":
                continue
            estimates.append(
                ChordEstimate(
                    start_seconds=round(section.start_seconds, 3),
                    end_seconds=round(section.end_seconds, 3),
                    chords=[chord],
                    confidence=confidence,
                    is_probable=True,
                )
            )
        return estimates

    def _summarize(self, audio: AudioProfile) -> str:
        pieces = [f"Analyzed about {audio.duration_seconds:.1f}s of local audio."]
        if audio.tempo_bpm is not None:
            pieces.append(f"Estimated tempo is around {audio.tempo_bpm:.0f} BPM.")
        if audio.key is not None:
            pieces.append(f"The key is probably {audio.key}.")
        if audio.chord_estimates:
            pieces.append(f"{audio.chord_estimates[0].label} in the first detected section.")
        return " ".join(pieces)
