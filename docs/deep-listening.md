# Deep Listening — per-stem timbre, groove, dynamics, and the arrangement view

Implements the light tracks of [`plans/deep-music-analysis.md`](../plans/deep-music-analysis.md)
(Tracks 2, 4, 5, the arrangement half of Track 6, and the explanation part of
Track 7). Everything runs on librosa/numpy — no GPU, no new heavy dependencies.
The heavy tracks (basic-pitch transcription, movement/voice-leading, MERT
embeddings) stay deferred; see "Deferred" below.

## What the listener hears now

After Demucs separation and the harmonic pass, each stem (drums/bass/vocals/
other) gets one extra librosa pass that produces three compact profiles:

| Profile | Fields | How it's computed |
| --- | --- | --- |
| `TimbreProfile` | brightness (dark/warm/bright), noisiness (tonal/mixed/noisy), band balance (low/mid/high-heavy/balanced), centroid Hz, flatness, band split | Energy-weighted spectral centroid + flatness over the whole stem, plus a 3-band energy split (0–180 Hz, 180 Hz–2 kHz, 2 kHz+) |
| `RhythmProfile` | feel (straight/swung), swing ratio, syncopation 0–1, density (sparse/moderate/busy), onsets per bar | Onset times are phased against the beat grid; offbeat onsets past a 0.25 phase margin count as syncopated, and the mean offbeat phase yields the swing ratio (0.5 phase → 1.0 straight, ~0.66 → ~2.0 triplet swing) |
| `StemDynamics` | bar-keyed loudness points (0–1, max 64), build/drop events, interpretation | Per-bar RMS normalized to the stem's peak; a build is a ≥3-bar quasi-monotonic rise of ≥0.3, a drop is a bar-to-bar fall of ≥0.4 |

The original (unseparated) audio also gets a **mix-level `TimbreProfile`**
(`AudioProfile.mix_timbre`).

**Bar convention:** all bars in listening output are **1-based inclusive**,
matching `ChordSpan` and `StructuralSection`.

## The arrangement view (Track 6, ensemble half)

`EnsembleProfile` (`AudioProfile.ensemble`) is built purely from ingredients
above — no extra audio pass:

- **columns**: one per structural section (A/B/C…), each holding per-stem
  cells with `activity` (fraction of audible bars) and `level`
  (silent/low/medium/high from the mean section loudness).
- **callouts**: section-to-section changes — `"vocals enters in B (bar 5)"`,
  `"bass drops out in B (bar 5)"`, `"drums pushes high in B (bar 5)"`.

The voice-leading half of Track 6 needs per-stem transcription (Track 1) and
is deferred with it.

## Code map

| Piece | Where |
| --- | --- |
| Audio pass + pure derivations | `apps/api/music_assistant/infrastructure/mir/listening_features.py` (`extract_stem_listening`, `timbre_profile`, `rhythm_profile`, `dynamics_profile`, `analyze_stem_listening`, `analyze_mix_timbre`) |
| Ensemble builder (pure) | `apps/api/music_assistant/infrastructure/mir/ensemble_features.py` (`build_ensemble_profile`) |
| Domain models | `apps/api/music_assistant/domain/audio_profile.py` (`TimbreProfile`, `RhythmProfile`, `StemDynamics`, `ArrangementCell/Column`, `EnsembleProfile`; `StemProfile.timbre/rhythm/dynamics`, `AudioProfile.mix_timbre/ensemble`) |
| Analyzer wiring | `DeepHarmonicAnalyzer` seams `stem_listening_provider`, `mix_timbre_provider`, `ensemble_builder` — all injectable, all degrade to `None` + an `stem_listening_unavailable` analysis note |
| Evidence claims | `apps/api/music_assistant/application/audio_enrichment.py` — timbre claims (`"mix: warm, mixed, mid-heavy"`), groove claims (`"drums: swung, busy, syncopated"`), build/drop `audio_estimate` claims, arrangement-callout `instrumentation` claims; all marked `approximate` |
| Chat answers | `apps/api/music_assistant/application/profile_queries.py` — `groove` / `timbre` / `dynamics_and_arrangement` tools, routed from swing/groove/feel, timbre/bright/sound, and build/drop/arrangement questions |
| UI | `apps/web/components/AnalysisResultBlock.tsx` — "Deep listening" chips panel (with a leading mix row) and the "Arrangement" stems × sections grid; view logic in `apps/web/lib/referenceProfileView.mjs` (`getStemListening`, `getArrangement`) |

## Design rules honored

- **Interpretation-first, bounded models** — no raw arrays leak into
  `ReferenceProfile`; every profile carries an interpretation string and a
  confidence, phrased probabilistically.
- **Graceful degradation** — a failing stem is skipped, a failing pass yields
  `None` plus an analysis note; the run never dies on listening features.
- **Injectable seams** — every audio-touching function has a provider/extractor
  parameter so the entire feature is unit-testable without audio files.
- **Evidence, not truth** — chat answers cite claims sourced to
  `local-audio://<reference_id>` with `approximate` notes.

## Tests

- `apps/api/tests/test_listening_features.py` — label thresholds, build/drop
  detection, swing/syncopation math, seams, plus one end-to-end librosa pass
  on generated audio (a 220 Hz sine must read dark/tonal/mid-band).
- `apps/api/tests/test_ensemble_features.py` — grid levels, entry/exit/push
  callouts, missing-ingredient behavior.
- `apps/api/tests/test_deep_harmonic_analyzer.py` — profiles attach to stems,
  mix timbre and ensemble land on `AudioProfile`, notes on degradation.
- `apps/api/tests/test_audio_enrichment.py` — claims produced (and not
  produced without listening data).
- `apps/api/tests/test_profile_query_tools.py` — question routing and honest
  no-evidence answers.
- `apps/web/lib/referenceProfileView.test.mjs` — chips, mix row, arrangement
  grid transposition.

## Deferred (and why)

- **Track 1 (basic-pitch transcription) + Track 3 (movement)** — TensorFlow/GPU
  dependency; revisit when a GPU deploy target exists.
- **Track 6 voice-leading** — depends on Track 1's notes.
- **`plans/mert-stem-harmony-analysis.md`** — MERT embeddings require GPU and a
  fail-loud contract that contradicts both this codebase's degrade-gracefully
  rule and the product decision that audio evidence complements web evidence.
