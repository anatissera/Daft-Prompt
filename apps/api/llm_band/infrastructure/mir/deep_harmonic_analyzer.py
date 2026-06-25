"""Deep harmonic analyzer: the default ``AudioAnalyzer`` for uploads.

Orchestrates stem separation, harmonic-source building, tempo/bar grid, key
candidates, per-bar triad chords, and A/B/C structure into a compact
``ReferenceProfile``. Each stage is injectable so the orchestration can be tested
with fakes; the defaults wire the real feature modules. Failures degrade
gracefully (mix/HPSS fallback, lowered confidence, analysis notes) rather than
raising.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from llm_band.domain.audio_profile import (
    AnalysisNote,
    AudioProfile,
    ChordEstimate,
    HarmonicProfile,
    ReferenceProfile,
    ReferenceSource,
    SectionProfile,
    StemProfile,
)
from llm_band.infrastructure.mir.chord_features import estimate_chords
from llm_band.infrastructure.mir.demucs_separator import DemucsSeparator
from llm_band.infrastructure.mir.harmonic_source import build_harmonic_source
from llm_band.infrastructure.mir.key_features import estimate_key
from llm_band.infrastructure.mir.librosa_analyzer import _clamp, _prepare_librosa_import
from llm_band.infrastructure.mir.structure_features import detect_structure
from llm_band.infrastructure.mir.tempo_grid import estimate_tempo_grid


WEAK_BAR_GRID_CONFIDENCE = 0.4


class DeepHarmonicAnalyzer:
    def __init__(
        self,
        output_root: Path | str,
        *,
        separator=None,
        harmonic_source_builder: Callable = build_harmonic_source,
        tempo_estimator: Callable = estimate_tempo_grid,
        key_estimator: Callable = estimate_key,
        chord_estimator: Callable = estimate_chords,
        structure_detector: Callable = detect_structure,
        duration_provider: Callable[[Path], float] | None = None,
    ) -> None:
        self.output_root = Path(output_root)
        self.separator = separator or DemucsSeparator(output_root=self.output_root)
        self.harmonic_source_builder = harmonic_source_builder
        self.tempo_estimator = tempo_estimator
        self.key_estimator = key_estimator
        self.chord_estimator = chord_estimator
        self.structure_detector = structure_detector
        self.duration_provider = duration_provider or _audio_duration

    def analyze(self, source: ReferenceSource) -> ReferenceProfile:
        audio_path = DemucsSeparator._resolve_local_path(source)
        duration = self.duration_provider(audio_path)
        analysis_dir = self.output_root / source.reference_id
        analysis_dir.mkdir(parents=True, exist_ok=True)

        notes: list[AnalysisNote] = []
        stems = self.separator.separate(source)
        if {stem.name for stem in stems} == {"mix"}:
            notes.append(
                AnalysisNote(
                    code="separation_unavailable",
                    message="Stem separation was unavailable; analyzed the mix directly.",
                    severity="warning",
                )
            )

        harmonic = self.harmonic_source_builder(stems, analysis_dir / "harmonic.wav")
        notes.extend(harmonic.notes)

        drum_path = next((stem.path for stem in stems if stem.name == "drums"), None)
        grid = self.tempo_estimator(str(audio_path), drum_path=drum_path)

        key_profile = self.key_estimator(
            harmonic.path, confidence_adjustment=harmonic.confidence_adjustment
        )

        chord_spans = self.chord_estimator(harmonic.path, grid.bar_times, duration)

        grid_confidence = grid.tempo.bar_grid_confidence
        if grid_confidence < WEAK_BAR_GRID_CONFIDENCE and chord_spans:
            notes.append(
                AnalysisNote(
                    code="weak_bar_grid",
                    message=(
                        "The bar grid was unstable; chord and structure estimates "
                        "are less reliable."
                    ),
                    severity="info",
                )
            )

        structure, progressions = self.structure_detector(chord_spans)

        harmony = HarmonicProfile(
            key=key_profile,
            chord_spans=chord_spans,
            progressions=progressions,
            harmonic_rhythm_label=_harmonic_rhythm_label(chord_spans),
            confidence=_harmony_confidence(key_profile, chord_spans, grid_confidence),
        )

        audio = AudioProfile(
            duration_seconds=duration,
            tempo_bpm=grid.tempo.primary_bpm,
            tempo_confidence=grid.tempo.confidence,
            key=key_profile.primary.key if key_profile.primary else None,
            key_confidence=key_profile.confidence,
            confidence=harmony.confidence,
            overall_confidence=harmony.confidence,
            chord_estimates=_legacy_chord_estimates(chord_spans),
            sections=_legacy_sections(structure),
            stems=[_stem_profile(stem) for stem in stems],
            tempo=grid.tempo,
            meter=grid.meter,
            harmony=harmony,
            structure=structure,
            analysis_notes=notes,
        )
        return ReferenceProfile(
            reference_id=source.reference_id,
            source=source,
            audio=audio,
            summary=_summarize(audio),
        )


def _legacy_chord_estimates(chord_spans) -> list[ChordEstimate]:
    estimates: list[ChordEstimate] = []
    for span in chord_spans:
        if span.chosen is None:
            continue
        estimates.append(
            ChordEstimate(
                start_seconds=span.start_seconds,
                end_seconds=span.end_seconds,
                chords=[span.chosen.label],
                confidence=span.chosen.confidence,
                is_probable=True,
            )
        )
    return estimates


def _legacy_sections(structure) -> list[SectionProfile]:
    return [
        SectionProfile(
            name=section.label,
            start_seconds=section.start_seconds,
            end_seconds=section.end_seconds,
            confidence=section.confidence,
        )
        for section in structure.sections
    ]


def _stem_profile(stem) -> StemProfile:
    return StemProfile(
        name=stem.name,
        role=stem.role,
        artifact_uri=stem.path,
        available=stem.name in {"drums", "bass", "vocals", "other"},
        confidence=stem.confidence,
    )


def _harmonic_rhythm_label(chord_spans) -> str:
    chosen = [span.chosen.label for span in chord_spans if span.chosen]
    if not chosen:
        return ""
    changes = 1 + sum(1 for left, right in zip(chosen, chosen[1:]) if left != right)
    rate = changes / max(1, len(chosen))
    if rate >= 0.85:
        return "fast — about one chord per bar"
    if rate >= 0.4:
        return "moderate"
    return "slow — chords held across bars"


def _harmony_confidence(key_profile, chord_spans, grid_confidence: float) -> float:
    chord_confidences = [span.chosen.confidence for span in chord_spans if span.chosen]
    chord_mean = sum(chord_confidences) / len(chord_confidences) if chord_confidences else 0.0
    combined = 0.5 * chord_mean + 0.3 * key_profile.confidence + 0.2 * grid_confidence
    return round(_clamp(combined), 3)


def _summarize(audio: AudioProfile) -> str:
    parts = [f"Analyzed about {audio.duration_seconds:.1f}s of audio."]
    if audio.tempo_bpm:
        parts.append(f"Tempo is around {audio.tempo_bpm:.0f} BPM.")
    if audio.key:
        parts.append(f"The key is likely {audio.key}.")
    if audio.harmony and audio.harmony.progressions and audio.harmony.progressions[0].chords:
        progression = " - ".join(audio.harmony.progressions[0].chords[:4])
        parts.append(f"The main progression is probably {progression}.")
    if audio.structure and audio.structure.sections:
        form = " / ".join(section.label for section in audio.structure.sections)
        parts.append(f"The structure looks like {form}.")
    return " ".join(parts)


def _audio_duration(audio_path: Path) -> float:
    try:
        import soundfile as sf

        info = sf.info(str(audio_path))
        if info.samplerate:
            return float(info.frames) / float(info.samplerate)
    except Exception:
        pass
    _prepare_librosa_import()
    import librosa

    return float(librosa.get_duration(path=str(audio_path)))
