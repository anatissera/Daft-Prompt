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
from contextlib import contextmanager
import json
import logging
from pathlib import Path
import time

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
from llm_band.infrastructure.mir.bar_energy import per_bar_energy, per_stem_activity_by_bar
from llm_band.infrastructure.mir.bar_phase import select_bar_phase_offset
from llm_band.infrastructure.mir.chord_features import (
    apply_key_context,
    estimate_bass_roots,
    estimate_chords,
)
from llm_band.infrastructure.mir.demucs_separator import DemucsSeparator
from llm_band.infrastructure.mir.harmonic_source import build_harmonic_source
from llm_band.infrastructure.mir.key_features import estimate_key, estimate_tuning_deviation
from llm_band.infrastructure.mir.librosa_analyzer import _clamp, _prepare_librosa_import
from llm_band.infrastructure.mir.multimodal_features import (
    MultimodalBarFeatures,
    extract_multimodal_features,
)
from llm_band.infrastructure.mir.section_features import (
    detect_multimodal_sections,
    detect_multimodal_sections_with_audit,
    detect_sections_from_bar_signals,
)
from llm_band.infrastructure.mir.structure_features import detect_structure
from llm_band.infrastructure.mir.tempo_grid import estimate_tempo_grid


WEAK_BAR_GRID_CONFIDENCE = 0.4
SIGNIFICANT_TUNING_DEVIATION = 0.2
# When key, chord, grid, and structure confidence are all below this, the
# analysis is too weak to lead with candidate claims; the summary says so first.
LOW_USEFULNESS_THRESHOLD = 0.5
# A bar-phase offset must clear this confidence before we trust it enough to
# shift the bar grid; below it, the downbeat is ambiguous and we keep offset 0.
BAR_PHASE_MIN_CONFIDENCE = 0.15
AMBIGUOUS_PHASE_GRID_PENALTY = 0.85
ProgressCallback = Callable[..., None]
logger = logging.getLogger(__name__)


class DeepHarmonicAnalyzer:
    def __init__(
        self,
        output_root: Path | str,
        *,
        separator=None,
        harmonic_source_builder: Callable = build_harmonic_source,
        tempo_estimator: Callable = estimate_tempo_grid,
        bar_phase_provider: Callable | None = select_bar_phase_offset,
        key_estimator: Callable = estimate_key,
        chord_estimator: Callable = estimate_chords,
        bass_root_provider: Callable | None = estimate_bass_roots,
        structure_detector: Callable = detect_structure,
        section_detector: Callable | None = detect_sections_from_bar_signals,
        multimodal_feature_provider: Callable | None = extract_multimodal_features,
        multimodal_section_detector: Callable | None = detect_multimodal_sections,
        energy_provider: Callable | None = per_bar_energy,
        stem_activity_provider: Callable | None = per_stem_activity_by_bar,
        tuning_deviation_provider: Callable[[str], float | None] | None = estimate_tuning_deviation,
        duration_provider: Callable[[Path], float] | None = None,
        clock: Callable[[], float] = time.perf_counter,
        audit_writer: Callable[[Path, dict], None] | None = None,
    ) -> None:
        self.output_root = Path(output_root)
        self.separator = separator or DemucsSeparator(output_root=self.output_root)
        self.harmonic_source_builder = harmonic_source_builder
        self.tempo_estimator = tempo_estimator
        self.bar_phase_provider = bar_phase_provider
        self.key_estimator = key_estimator
        self.chord_estimator = chord_estimator
        self.bass_root_provider = bass_root_provider
        self.structure_detector = structure_detector
        self.section_detector = section_detector
        self.multimodal_feature_provider = multimodal_feature_provider
        self.multimodal_section_detector = multimodal_section_detector
        self.energy_provider = energy_provider
        self.stem_activity_provider = stem_activity_provider
        self.tuning_deviation_provider = tuning_deviation_provider
        self.duration_provider = duration_provider or _audio_duration
        self.clock = clock
        self.audit_writer = audit_writer or _write_json

    def analyze(
        self,
        source: ReferenceSource,
        *,
        progress: ProgressCallback | None = None,
    ) -> ReferenceProfile:
        # Real-time streaming is an interface concern: the API runs analyze() on a
        # worker thread and turns this progress callback into SSE events (see
        # api._reference_analysis_stream_events). The analyzer stays HTTP-agnostic.
        return self._analyze(source, progress=progress)

    def _analyze(
        self,
        source: ReferenceSource,
        *,
        progress: ProgressCallback | None = None,
    ) -> ReferenceProfile:
        audio_path = DemucsSeparator._resolve_local_path(source)
        duration = self.duration_provider(audio_path)
        analysis_dir = self.output_root / source.reference_id
        analysis_dir.mkdir(parents=True, exist_ok=True)

        notes: list[AnalysisNote] = []
        with _timed_stage(
            progress,
            self.clock,
            "separating_stems",
            "Separating stems for harmonic analysis.",
        ) as stage_details:
            stems = self.separator.separate(source)
            stage_details["cache_hit"] = bool(
                getattr(self.separator, "last_cache_hit", False)
            )
        if {stem.name for stem in stems} == {"mix"}:
            notes.append(
                AnalysisNote(
                    code="separation_unavailable",
                    message="Stem separation was unavailable; analyzed the mix directly.",
                    severity="warning",
                )
            )

        with _timed_stage(
            progress,
            self.clock,
            "building_harmonic_source",
            "Building the harmonic source.",
        ):
            harmonic = self.harmonic_source_builder(stems, analysis_dir / "harmonic.wav")
        notes.extend(harmonic.notes)

        with _timed_stage(
            progress,
            self.clock,
            "estimating_tempo_grid",
            "Estimating tempo, beats, and bars.",
        ):
            drum_path = next((stem.path for stem in stems if stem.name == "drums"), None)
            grid = self.tempo_estimator(str(audio_path), drum_path=drum_path)
            bar_times = _apply_bar_phase(self.bar_phase_provider, harmonic.path, grid, notes)

        with _timed_stage(
            progress,
            self.clock,
            "estimating_key",
            "Estimating likely key candidates.",
        ):
            tuning_deviation = _safe_tuning_deviation(self.tuning_deviation_provider, harmonic.path)
            if tuning_deviation is not None and abs(tuning_deviation) >= SIGNIFICANT_TUNING_DEVIATION:
                notes.append(
                    AnalysisNote(
                        code="possible_detuning",
                        message=(
                            "Labels assume A=440; recording may be slightly detuned."
                        ),
                        severity="info",
                    )
                )
            key_profile = self.key_estimator(
                harmonic.path, confidence_adjustment=harmonic.confidence_adjustment
            )
        if key_profile.primary and key_profile.relative_key_ambiguity:
            alternatives = [
                candidate.key for candidate in key_profile.candidates[1:4]
            ]
            suffix = (
                f" Close alternatives include {', '.join(alternatives)}."
                if alternatives
                else ""
            )
            notes.append(
                AnalysisNote(
                    code="ambiguous_key",
                    message=(
                        f"Key is ambiguous around {key_profile.primary.key}."
                        f"{suffix}"
                    ),
                    severity="info",
                )
            )

        with _timed_stage(
            progress,
            self.clock,
            "estimating_chords",
            "Estimating probable triads by bar.",
        ):
            bass_path = next((stem.path for stem in stems if stem.name == "bass"), None)
            bass_roots = _safe_bass_roots(
                self.bass_root_provider, bass_path, bar_times, duration
            )
            chord_spans = self.chord_estimator(
                harmonic.path, bar_times, duration, bass_roots=bass_roots or None
            )
            chord_spans = apply_key_context(
                chord_spans, key_profile.primary.key if key_profile.primary else None
            )

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

        with _timed_stage(
            progress,
            self.clock,
            "extracting_stem_features",
            "Extracting bar-aligned stem features.",
        ):
            multimodal_features = _safe_multimodal_features(
                self.multimodal_feature_provider, stems, bar_times, duration
            )

        with _timed_stage(
            progress,
            self.clock,
            "detecting_structure",
            "Detecting repeated progressions and A/B/C structure.",
        ):
            boundary_audit: list[dict] = []
            structure_source = "harmonic"
            structure, progressions = self.structure_detector(chord_spans)
            if self.multimodal_section_detector is not None and multimodal_features.by_stem:
                if self.multimodal_section_detector is detect_multimodal_sections:
                    multimodal_structure, boundary_audit = detect_multimodal_sections_with_audit(
                        chord_spans, multimodal_features
                    )
                else:
                    multimodal_structure = self.multimodal_section_detector(
                        chord_spans, multimodal_features
                    )
                if (
                    len(multimodal_structure.sections) > 1
                    and multimodal_structure.confidence >= 0.4
                ):
                    structure = multimodal_structure
                    structure_source = "multimodal"
                    notes.append(
                        AnalysisNote(
                            code="multimodal_sections",
                            message=(
                                "Sections use sustained vocal, rhythmic, bass, and "
                                "arrangement changes aligned to bars."
                            ),
                            severity="info",
                        )
                    )
            if (
                structure.confidence < 0.4
                and self.section_detector is not None
            ):
                energy_by_bar = _safe_bar_energy(
                    self.energy_provider, str(audio_path), bar_times, duration
                )
                stem_activity_by_bar = _safe_stem_activity(
                    self.stem_activity_provider, stems, bar_times, duration
                )
                approximate_structure = self.section_detector(
                    chord_spans,
                    energy_by_bar=energy_by_bar or None,
                    stem_activity_by_bar=stem_activity_by_bar or None,
                )
                if (
                    approximate_structure.sections
                    and approximate_structure.confidence > structure.confidence
                ):
                    structure = approximate_structure
                    structure_source = "fallback"
                    notes.append(
                        AnalysisNote(
                            code="approximate_sections",
                            message=(
                                "Sections are approximate; boundaries use bar-aligned "
                                "novelty signals rather than exact harmonic repetition."
                            ),
                            severity="info",
                        )
                    )
        if structure.sections and structure.confidence < 0.4:
            notes.append(
                AnalysisNote(
                    code="unclear_structure",
                    message=(
                        "Structure is unclear from harmonic repetition; "
                        "sections are approximate."
                    ),
                    severity="info",
                )
            )

        if _is_low_usefulness(
            key_profile.confidence,
            _chord_mean_confidence(chord_spans),
            grid_confidence,
            structure.confidence,
        ):
            notes.append(
                AnalysisNote(
                    code="low_usefulness",
                    message=(
                        "Key, chord, and structure evidence are all weak in this "
                        "recording; treat the harmonic read as a rough sketch."
                    ),
                    severity="warning",
                )
            )

        harmony = HarmonicProfile(
            key=key_profile,
            chord_spans=chord_spans,
            progressions=progressions,
            harmonic_rhythm_label=_harmonic_rhythm_label(chord_spans),
            confidence=_harmony_confidence(key_profile, chord_spans, grid_confidence),
        )
        audit_path = analysis_dir / "section_audit.json"
        try:
            self.audit_writer(
                audit_path,
                _section_audit_payload(
                    source=source,
                    duration=duration,
                    grid=grid,
                    key_profile=key_profile,
                    harmony=harmony,
                    boundary_audit=boundary_audit,
                    structure=structure,
                    structure_source=structure_source,
                ),
            )
            logger.info(
                "section audit written for %s at %s",
                source.reference_id,
                audit_path,
            )
        except Exception as exc:
            logger.warning(
                "could not write section audit for %s at %s: %s",
                source.reference_id,
                audit_path,
                exc,
            )
            notes.append(
                AnalysisNote(
                    code="section_audit_unavailable",
                    message="Section decision audit could not be written.",
                    severity="warning",
                )
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


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


@contextmanager
def _timed_stage(
    progress: ProgressCallback | None,
    clock: Callable[[], float],
    stage: str,
    message: str,
):
    details: dict[str, bool] = {}
    started = clock()
    if progress is not None:
        progress(stage, message, status="started")
    try:
        yield details
    finally:
        elapsed = round(max(0.0, clock() - started), 3)
        if progress is not None:
            progress(
                stage,
                message,
                status="completed",
                elapsed_seconds=elapsed,
                cache_hit=details.get("cache_hit"),
            )


def _safe_tuning_deviation(
    provider: Callable[[str], float | None] | None, path: str
) -> float | None:
    if provider is None:
        return None
    try:
        return provider(path)
    except Exception:
        return None


def _apply_bar_phase(provider: Callable | None, harmonic_path: str, grid, notes) -> list[float]:
    """Realign bar starts to the estimated downbeat phase; returns corrected bar times.

    When the chosen offset is confident and nonzero, bars are shifted and a note is
    added. When no offset is clearly better, the downbeat is ambiguous, so the bar
    grid is left at offset 0 but its confidence is reduced.
    """
    bar_times = list(grid.bar_times)
    if provider is None or len(grid.beat_times) < grid.beats_per_bar:
        return bar_times
    try:
        offset, phase_confidence = provider(harmonic_path, grid.beat_times)
    except Exception:
        return bar_times

    if phase_confidence < BAR_PHASE_MIN_CONFIDENCE:
        grid.tempo = grid.tempo.model_copy(
            update={
                "bar_grid_confidence": round(
                    grid.tempo.bar_grid_confidence * AMBIGUOUS_PHASE_GRID_PENALTY, 3
                )
            }
        )
        return bar_times

    if offset > 0:
        shifted = grid.beat_times[offset :: grid.beats_per_bar]
        if shifted:
            notes.append(
                AnalysisNote(
                    code="bar_phase_corrected",
                    message="Adjusted the downbeat phase so bars align to chord changes.",
                    severity="info",
                )
            )
            return shifted
    return bar_times


def _safe_bass_roots(
    provider: Callable | None, bass_path: str | None, bar_times, duration: float
) -> list[int | None]:
    if provider is None or bass_path is None or not bar_times:
        return []
    try:
        return provider(bass_path, bar_times, duration)
    except Exception:
        return []


def _safe_bar_energy(
    provider: Callable | None, audio_path: str, bar_times, duration: float
) -> list[float]:
    if provider is None or not bar_times:
        return []
    try:
        return provider(audio_path, bar_times, duration)
    except Exception:
        return []


def _safe_stem_activity(
    provider: Callable | None, stems, bar_times, duration: float
) -> list[dict[str, float]]:
    if provider is None or not bar_times:
        return []
    stem_paths = {
        stem.name: stem.path
        for stem in stems
        if stem.name in {"drums", "bass", "vocals", "other"}
    }
    if not stem_paths:
        return []
    try:
        return provider(stem_paths, bar_times, duration)
    except Exception:
        return []


def _safe_multimodal_features(
    provider: Callable | None, stems, bar_times, duration: float
) -> MultimodalBarFeatures:
    if provider is None or not bar_times:
        return MultimodalBarFeatures()
    stem_paths = {
        stem.name: stem.path
        for stem in stems
        if stem.name in {"drums", "bass", "vocals", "other"}
    }
    if not stem_paths:
        return MultimodalBarFeatures()
    try:
        return provider(stem_paths, bar_times, duration)
    except Exception:
        return MultimodalBarFeatures()


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


def _section_audit_payload(
    *,
    source: ReferenceSource,
    duration: float,
    grid,
    key_profile,
    harmony: HarmonicProfile,
    boundary_audit: list[dict],
    structure,
    structure_source: str,
) -> dict:
    main_progression = (
        harmony.progressions[0].chords
        if harmony.progressions and harmony.progressions[0].chords
        else []
    )
    return {
        "metadata": {
            "reference_id": source.reference_id,
            "label": source.label,
            "duration_seconds": round(duration, 3),
            "tempo_bpm": grid.tempo.primary_bpm,
            "bar_count": len(grid.bar_times),
            "bar_grid_confidence": grid.tempo.bar_grid_confidence,
        },
        "harmony": {
            "key_candidates": [
                {
                    "key": candidate.key,
                    "mode": candidate.mode,
                    "confidence": candidate.confidence,
                }
                for candidate in key_profile.candidates[:4]
            ],
            "key_confidence": key_profile.confidence,
            "main_progression": main_progression,
            "harmony_confidence": harmony.confidence,
        },
        "boundary_candidates": boundary_audit,
        "final_sections": [
            {
                "label": section.label,
                "start_bar": section.start_bar,
                "end_bar": section.end_bar,
                "start_seconds": section.start_seconds,
                "end_seconds": section.end_seconds,
                "confidence": section.confidence,
                "main_progression": section.main_progression,
                "source": structure_source,
            }
            for section in structure.sections
        ],
    }


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


def _chord_mean_confidence(chord_spans) -> float:
    chord_confidences = [span.chosen.confidence for span in chord_spans if span.chosen]
    return sum(chord_confidences) / len(chord_confidences) if chord_confidences else 0.0


def _harmony_confidence(key_profile, chord_spans, grid_confidence: float) -> float:
    chord_mean = _chord_mean_confidence(chord_spans)
    combined = 0.5 * chord_mean + 0.3 * key_profile.confidence + 0.2 * grid_confidence
    return round(_clamp(combined), 3)


def _is_low_usefulness(
    key_confidence: float,
    chord_confidence: float,
    grid_confidence: float,
    structure_confidence: float,
) -> bool:
    return (
        key_confidence < LOW_USEFULNESS_THRESHOLD
        and chord_confidence < LOW_USEFULNESS_THRESHOLD
        and grid_confidence < LOW_USEFULNESS_THRESHOLD
        and structure_confidence < LOW_USEFULNESS_THRESHOLD
    )


def _summarize(audio: AudioProfile) -> str:
    parts = [f"Analyzed about {audio.duration_seconds:.1f}s of audio."]
    if audio.tempo_bpm:
        parts.append(f"Tempo is around {audio.tempo_bpm:.0f} BPM.")
    if any(note.code == "low_usefulness" for note in audio.analysis_notes):
        parts.append(
            "The chord and structure evidence is weak in this recording, so treat "
            "the harmonic read below as a rough sketch."
        )
    key_profile = audio.harmony.key if audio.harmony else None
    key_is_uncertain = bool(
        key_profile
        and (key_profile.confidence < 0.5 or key_profile.relative_key_ambiguity)
    )
    if key_profile and key_profile.primary and key_is_uncertain:
        candidates = [candidate.key for candidate in key_profile.candidates[:3]]
        parts.append(
            f"Tonal center is ambiguous; close candidates include {', '.join(candidates)}."
        )
    elif audio.key:
        parts.append(f"The key is likely {audio.key}.")
    if audio.harmony and audio.harmony.progressions and audio.harmony.progressions[0].chords:
        progression = " - ".join(audio.harmony.progressions[0].chords[:4])
        progression_confidence = audio.harmony.progressions[0].confidence
        if progression_confidence < 0.5:
            parts.append(f"Weak chord loop candidate: {progression}.")
        else:
            parts.append(f"The main progression is probably {progression}.")
    if audio.structure and audio.structure.sections:
        if audio.structure.confidence < 0.4:
            parts.append("Structure is approximate/unclear.")
        else:
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
