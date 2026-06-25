# Deep Music Analysis Plan — Per-Instrument & Compositional Listening

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn LLMinem's reference analysis from a single mono-mix profile into a deep, per-instrument + ensemble musical analysis: isolate instruments (source separation), transcribe each one, and extract spectral ("Fourier"), melodic-movement / voice-leading, dynamic, and harmonic-rhythm features — all mapped to plain music-theory interpretation and surfaced in the chat UI.

**Why this fits the current codebase:** The clean-architecture refactor on `develop` already left the exact seams this needs:
- `ports/stem_separator.py` (`StemSeparator.separate`) — stub `DemucsSeparator`.
- `ports/transcription.py` (`Transcriber.transcribe_melody`) — stub `BasicPitchTranscriber`.
- `ports/audio_analyzer.py` (`AudioAnalyzer.analyze`) — real `LibrosaAnalyzer`, stub `EssentiaAnalyzer`.
- `domain/audio_profile.py` already has `StemProfile` and `AudioProfile.stems` (currently unused).

This plan fills those stubs and extends the domain contract — it does **not** rearchitect.

**Runtime target:** Container on a Google GPU. Heavy dependencies (Demucs/torch, basic-pitch/tensorflow) are acceptable. Analysis runs server-side; the UI only renders compact results.

**Tech stack:** FastAPI, Pydantic v2, librosa, **Demucs (torch)**, **basic-pitch (Spotify)**, music21, NumPy, Next.js/React/TypeScript, Docker (CUDA base image).

---

## Source Documents

- `PRODUCT.md` — product behavior and MVP scope (evidence-based, probabilistic, chat-first).
- `DESIGN.md` — UX direction (contextual details, not dashboard-first).
- `docs/architecture.md` — boundaries; **composition code must not import MIR adapters**, only compact domain summaries.
- `docs/chat-api-direction.md` — current endpoints and the future `/chat` router.
- `plans/chat-musical-mvp.md` — the active MVP plan this extends (its Phase 3 = the current `LibrosaAnalyzer`).
- `docs/architecture-refactor-status.md` — "Next" already lists "Improve the local MIR/audio profiling quality."

---

## Design Principles (carried from PRODUCT/DESIGN)

1. **Evidence + uncertainty.** Every derived musical claim carries a confidence and is phrased probabilistically ("probably", "likely"). No estimate is presented as ground truth.
2. **Compact domain, no raw arrays.** The profile must not leak FFT bins, full chroma matrices, or torch tensors. Time series are downsampled to bounded point lists (like the existing 32-point `energy_curve`).
3. **Engine-agnostic contract.** Analysis consumers depend on the domain models, never on Demucs/basic-pitch internals. Swapping the separator must not change the profile shape.
4. **Graceful degradation.** If separation or transcription fails (corrupt audio, OOM, unsupported file), fall back to whole-mix analysis and lower confidence — never hard-fail the whole request.
5. **Chat-first surfacing.** Results render as compact, expandable analysis blocks, not a permanent dashboard.

---

## The Ideas — What We Can Extract, and What Each Buys Musically

This section is the "research + analysis" backing the phases. Each idea names the **technique**, the **musical question it answers**, and how it is **surfaced**.

### A. Source separation (instrument isolation) — *Demucs*
- **Technique:** Demucs `htdemucs` model → 4 stems (drums, bass, vocals, other) written as audio artifacts.
- **Buys:** Everything downstream becomes per-instrument. Lets us analyze bass harmony without vocal/cymbal interference, drum groove without pitched content, melody contour from the vocal/lead stem, etc. Also enables "solo this stem" playback.
- **Surfacing:** A roster of detected stems with per-stem play/solo and a one-line role description.

### B. Per-stem transcription → notes — *basic-pitch* (pitched stems) + onset detection (drums)
- **Technique:** basic-pitch on bass/vocals/other → MIDI-like `Note` lists (reuses `domain/song_state.Note`: MIDI pitch, bar, start_beat, duration). Drums get onset-only events bucketed into a coarse kit (kick/snare/hat) by spectral band.
- **Buys:** Symbolic representation per instrument → the foundation for melodic, voice-leading, and rhythmic analysis. Closes the loop with the **composition engine**, which already speaks `SongState`/`Note` — a transcribed reference can later seed `notes_summary`.
- **Surfacing:** Per-stem note count, register (lowest/highest), and optional piano-roll thumbnail behind a detail toggle.

### C. Spectral / "Fourier" features — *librosa STFT family*, per stem + mix
- **Technique:** STFT-derived features summarized over time: spectral centroid (brightness), bandwidth, rolloff, flatness (noisiness/tonalness), spectral contrast, zero-crossing rate, and a low/mid/high band-energy split. MFCC summary for timbre fingerprinting.
- **Buys:** Objective timbre/tone descriptors ("bright and thin" vs "dark and full"), which instrument occupies which frequency band (mix balance), and noisiness (distortion/percussiveness). This is the literal "Fourier" layer the user asked for, made musically legible.
- **Surfacing:** Per-stem "timbre" chips (e.g. *bright • mid-heavy • sustained*) + a mix frequency-balance bar.

### D. Melodic movement / voice-leading — *over transcribed notes*
- **Technique (per melodic stem):** contour (up/down/static sequence), interval histogram, stepwise-vs-leap ratio, range/tessitura, average note duration, rhythmic density over time.
  **Technique (between stems):** bass↔lead voice-leading — for each harmonic window, the motion type (parallel/contrary/oblique/similar) and average voice spacing; harmonic interval between bass root and melody.
- **Buys:** Directly answers "movimiento melódico / conducción de voces". Distinguishes a smooth stepwise melody from an angular leaping one; flags when bass and melody move in parallel vs independent. Strong, teachable music-theory output.
- **Surfacing:** A "movement" mini-summary per melodic stem + a bass/melody relationship line ("mostly contrary motion, ~stepwise melody").

### E. Dynamics / energy over time — *RMS + per-stem loudness envelopes*
- **Technique:** Reuse the existing normalized RMS curve, but compute it **per stem** and as a stacked picture (who is loud when). Add crescendo/diminuendo detection (sustained slope) and per-section energy already present.
- **Buys:** "Why does this section feel bigger?" answered concretely: *the drums and 'other' enter and the bass loudness doubles at 0:48*. Maps energy to arrangement events, not just a single global curve.
- **Surfacing:** Stacked per-stem energy curve aligned to the section timeline + textual "build/drop" callouts.

### F. Harmonic rhythm + harmony (improved) — *chroma on the harmonic stems*
- **Technique:** Estimate chords from `bass + other` chroma (cleaner than full mix), and measure **harmonic rhythm** = chord-change rate (changes per bar / per section). Improve key estimation by voting across stems and the existing Krumhansl profiles. Optionally label Roman-numeral function relative to the detected key using music21.
- **Buys:** "How fast does the harmony move?" (one chord per bar vs four), cleaner chord estimates, and functional context (tonic/subdominant/dominant feel). Major upgrade over current full-mix template matching.
- **Surfacing:** Chords-per-section with confidence (already exists) + a harmonic-rhythm descriptor ("~1 chord/bar, slow harmonic rhythm") + optional Roman numerals behind detail.

### G. Rhythm / groove — *onsets + beat grid*
- **Technique:** From drums + global beat grid: swing/straight feel (off-beat onset timing), syncopation score (onsets off the strong beats), and per-stem rhythmic density. Reuse existing `beat_track`.
- **Buys:** "Groove" descriptors — straight vs swung, busy vs sparse, syncopated vs on-grid. Ties rhythm to feel.
- **Surfacing:** Groove chips (*straight • syncopated • busy hats*).

### H. Cross-stem ensemble / arrangement view — *the "together" analysis*
- **Technique:** Combine B–G into an arrangement timeline: which instruments are active per section, their register/role, and how they interact (call-and-response detection via alternating energy, density layering).
- **Buys:** The "en conjunto" view the user asked for — not just isolated stems but how they compose together. This is the bridge to the composition engine's `notes_summary` peer-context idea.
- **Surfacing:** An arrangement strip: rows = stems, columns = sections, cells = active/role/energy.

> **Mapping ideas → music theory** is the connective tissue: every numeric feature ships with a short, generic interpretation string so the LLM explainer (`answer_music_question.py`) can ground answers in evidence rather than re-deriving from raw numbers.

---

## File Map

New and modified files, by layer:

**Domain (`apps/api/llm_band/domain/audio_profile.py`)** — extend the contract:
- `StemProfile`: add `role`, `note_count`, `pitch_low`/`pitch_high`, `timbre` (`TimbreProfile`), `movement` (`MovementProfile`), `energy_curve` (per-stem points), `rhythm` (`RhythmProfile`).
- New models: `TimbreProfile` (spectral summary + interpretation), `MovementProfile` (contour/intervals/voice-leading summary), `RhythmProfile` (density/swing/syncopation), `HarmonyProfile` (chords + harmonic_rhythm + roman numerals), `EnsembleProfile` (arrangement timeline + voice-leading between stems), `AnalysisFeature` (generic `{name, value, confidence, interpretation}`).
- `AudioProfile`: add `harmony: HarmonyProfile`, `ensemble: EnsembleProfile`, keep `stems: list[StemProfile]`.

**Ports** (already exist — implement, do not change signatures unless noted):
- `ports/stem_separator.py`, `ports/transcription.py`, `ports/audio_analyzer.py`.
- Possibly add `ports/feature_extractor.py` if spectral/movement extraction is shared across adapters (decision in Phase 2).

**Infrastructure (`apps/api/llm_band/infrastructure/mir/`):**
- `demucs_separator.py` — implement real Demucs separation → writes stems to artifact store, returns `StemProfile` list with `artifact_uri`.
- `basic_pitch_transcriber.py` — implement real transcription → `Note` lists per pitched stem.
- New `spectral_features.py` — STFT/Fourier feature extraction (idea C).
- New `movement_features.py` — contour, intervals, voice-leading over `Note` lists (idea D).
- New `harmony_features.py` — chord + harmonic-rhythm + optional Roman numerals (idea F), music21-backed.
- New `rhythm_features.py` — groove/swing/syncopation (idea G).
- `librosa_analyzer.py` — refactor into the **orchestrator** that composes separation → transcription → feature modules, or introduce a new `deep_analyzer.py` that wraps it (decision in Phase 2).

**Application (`apps/api/llm_band/application/`):**
- `analyze_reference.py` — `AnalyzeReference` gains an optional "depth" notion (quick mix-only vs deep per-stem) and wires the separator/transcriber.
- `answer_music_question.py` — extend evidence extraction to cite per-stem timbre, movement, harmonic rhythm, arrangement.

**Interfaces (`apps/api/llm_band/interfaces/`):**
- `api_models.py` / `api.py` — `/references/analyze` returns the richer `ReferenceProfile`; consider an async/long-running pattern since deep analysis is slow (decision in Phase 6).

**Frontend (`apps/web/`):**
- `lib/types.ts` — mirror the new domain models.
- `components/AnalysisResultBlock.tsx` — extend with stem roster, timbre chips, movement summary, arrangement strip, harmonic-rhythm line.
- New components: `StemRoster.tsx`, `ArrangementStrip.tsx`, `MovementSummary.tsx` (kept compact / behind detail toggles per DESIGN.md).

**Ops:**
- `apps/api/Dockerfile` — CUDA-capable base, pre-download Demucs/basic-pitch model weights at build time.
- `apps/api/pyproject.toml` — add `demucs`, `basic-pitch`, torch (CUDA extra).
- `apps/api/tests/fixtures/audio/` — short multi-instrument fixture(s).

---

## Phase 0: Contract & Fakes First (no heavy deps)

Establish the full domain contract and fake adapters so every later phase has a target shape and the test suite stays fast and dependency-free.

**Files:**
- Modify: `apps/api/llm_band/domain/audio_profile.py`
- Modify: `apps/web/lib/types.ts`
- Create: `apps/api/tests/test_deep_profile_contract.py`
- Create: `apps/api/tests/fakes/` (fake separator, transcriber, feature extractors)

- [ ] Add the new domain models (`TimbreProfile`, `MovementProfile`, `RhythmProfile`, `HarmonyProfile`, `EnsembleProfile`, `AnalysisFeature`) and extend `StemProfile`/`AudioProfile`. Keep all time series as bounded point lists; add validators that reject oversized arrays.
- [ ] Every derived field carries a `confidence` and an `interpretation: str`.
- [ ] Add fake adapters returning deterministic data for tests.
- [ ] Mirror all new models in `apps/web/lib/types.ts`.
- [ ] Verify:
```bash
cd apps/api && python -m pytest tests/test_deep_profile_contract.py
cd apps/web && npm run typecheck
```
- [ ] Expected: contract round-trips through Pydantic; TS compiles; no raw arrays exceed bounded sizes.

## Phase 1: Stem Separation (Demucs)

**Files:**
- Modify: `apps/api/pyproject.toml` (add `demucs`, torch CUDA extra)
- Modify: `apps/api/llm_band/infrastructure/mir/demucs_separator.py`
- Modify: `apps/api/llm_band/ports/stem_separator.py` (only if return shape needs `StemProfile` + artifact URIs)
- Create: `apps/api/tests/test_demucs_separator.py` (skipped unless `DEMUCS_AVAILABLE`)
- Modify: `apps/api/Dockerfile` (CUDA base, pre-fetch weights)

- [ ] Implement `DemucsSeparator.separate(source) -> list[StemProfile]`: load audio, run `htdemucs`, write each stem to the artifact store, return `StemProfile(name, role, artifact_uri, confidence)`.
- [ ] Map Demucs labels → roles: drums→percussion, bass→bass, vocals→lead/vocal, other→harmony/other.
- [ ] Handle GPU/CPU selection via env; graceful fallback to whole-mix (single "mix" pseudo-stem) on failure.
- [ ] Test with the fixture behind an availability guard so CI without torch still passes.
- [ ] Verify:
```bash
cd apps/api && python -m pytest tests/test_demucs_separator.py
docker compose build api   # confirms CUDA image + weights bake
```

## Phase 2: Analyzer Orchestration (mix-only deep path, no transcription yet)

Restructure so the analyzer composes feature modules. Wire spectral + dynamics + improved harmony on the **whole mix and per stem** (features that don't need transcription).

**Files:**
- Create: `apps/api/llm_band/infrastructure/mir/spectral_features.py` (idea C)
- Create: `apps/api/llm_band/infrastructure/mir/harmony_features.py` (idea F)
- Create: `apps/api/llm_band/infrastructure/mir/rhythm_features.py` (idea G)
- Modify: `apps/api/llm_band/infrastructure/mir/librosa_analyzer.py` (extract reusable helpers) or add `deep_analyzer.py`
- Modify: `apps/api/llm_band/application/analyze_reference.py` (inject separator)
- Create: `apps/api/tests/test_spectral_features.py`, `test_harmony_features.py`, `test_rhythm_features.py`

- [ ] Spectral: centroid/bandwidth/rolloff/flatness/contrast/ZCR + low/mid/high band split + MFCC summary → `TimbreProfile` with interpretation strings ("bright", "mid-heavy", "noisy/percussive").
- [ ] Harmony: chord estimation on bass+other chroma, harmonic-rhythm (changes per bar/section), key voting across stems → `HarmonyProfile`. Optional Roman numerals via music21.
- [ ] Rhythm: onset density, swing ratio, syncopation from drum stem + beat grid → `RhythmProfile`.
- [ ] Orchestrator runs per stem (timbre, energy curve, rhythm) and at mix level (harmony, sections, key); fills `AudioProfile.stems[*]` and `AudioProfile.harmony`.
- [ ] Preserve the existing mono-mix behavior as the fallback when no stems.
- [ ] Verify:
```bash
cd apps/api && python -m pytest tests/test_spectral_features.py tests/test_harmony_features.py tests/test_rhythm_features.py tests/test_librosa_analyzer.py
```

## Phase 3: Transcription (basic-pitch) + Melodic Movement

**Files:**
- Modify: `apps/api/pyproject.toml` (add `basic-pitch`)
- Modify: `apps/api/llm_band/infrastructure/mir/basic_pitch_transcriber.py`
- Create: `apps/api/llm_band/infrastructure/mir/movement_features.py` (idea D)
- Modify: orchestrator to transcribe pitched stems and compute movement
- Create: `apps/api/tests/test_basic_pitch_transcriber.py` (guarded), `test_movement_features.py`

- [ ] `BasicPitchTranscriber.transcribe_melody(source) -> list[Note]` reusing `domain/song_state.Note` (MIDI pitch, bar, start_beat, duration via the detected tempo grid).
- [ ] Per-stem movement: contour string, interval histogram, step/leap ratio, range, avg duration, density-over-time → `MovementProfile` with interpretation ("mostly stepwise, narrow range").
- [ ] Drums: onset-only → coarse kit buckets by spectral band (no pitch).
- [ ] Movement tests run on synthetic `Note` lists (no audio needed) for determinism.
- [ ] Verify:
```bash
cd apps/api && python -m pytest tests/test_basic_pitch_transcriber.py tests/test_movement_features.py
```

## Phase 4: Ensemble / Voice-Leading & Arrangement ("together")

**Files:**
- Modify: `apps/api/llm_band/infrastructure/mir/movement_features.py` (cross-stem voice-leading)
- Create: `apps/api/llm_band/infrastructure/mir/ensemble_features.py` (idea H)
- Modify: orchestrator to assemble `EnsembleProfile`
- Create: `apps/api/tests/test_ensemble_features.py`

- [ ] Voice-leading bass↔lead per harmonic window: motion type (parallel/contrary/oblique/similar), average spacing, root-to-melody interval → summary on `EnsembleProfile`.
- [ ] Arrangement timeline: per section × stem activity + role + energy (idea E stacked picture + idea H).
- [ ] Call-and-response / layering heuristics from alternating per-stem energy.
- [ ] Generic interpretation strings ("bass and melody mostly contrary; full arrangement enters at section B").
- [ ] Verify:
```bash
cd apps/api && python -m pytest tests/test_ensemble_features.py
```

## Phase 5: Evidence-Grounded Explanation

**Files:**
- Modify: `apps/api/llm_band/application/answer_music_question.py`
- Modify: `apps/api/tests/test_answer_music_question.py`

- [ ] Extend evidence extraction to cite per-stem timbre, movement, harmonic rhythm, groove, and arrangement events with their confidence.
- [ ] Keep probabilistic phrasing; deterministic fallback explainer for no-LLM/local runs.
- [ ] Verify:
```bash
cd apps/api && python -m pytest tests/test_answer_music_question.py
```

## Phase 6: API Surface for Slow Deep Analysis

Deep analysis (Demucs + transcription) is slow — the synchronous `/references/analyze` may need a streaming/job pattern.

**Files:**
- Modify: `apps/api/llm_band/interfaces/api.py`, `api_models.py`
- Create: `apps/api/tests/test_reference_analysis_api.py` updates

- [ ] **Decision:** SSE progress stream (matches existing `/compose/stream` style) vs job-id polling. Recommend SSE: emit `separating → transcribing → analyzing-stems → ensemble → done` events so the UI shows live progress (DESIGN.md "Analysis In Progress").
- [ ] Keep a fast "quick" mode (mix-only, current behavior) and an opt-in "deep" mode.
- [ ] Verify:
```bash
cd apps/api && python -m pytest tests/test_reference_analysis_api.py tests/test_api_architecture.py
```

## Phase 7: UI Surfacing

**Files:**
- Modify: `apps/web/lib/types.ts`, `apps/web/components/AnalysisResultBlock.tsx`
- Create: `apps/web/components/StemRoster.tsx`, `ArrangementStrip.tsx`, `MovementSummary.tsx`
- Modify: `apps/web/app/api/references/analyze/route.ts` (consume SSE if Phase 6 chooses it)

UI concept (compact, expandable — never dashboard-first):
- **Stem roster:** one row per detected instrument with role, play/solo, and a one-line timbre chip set (*bright • mid-heavy • sustained*).
- **Arrangement strip:** sections (cols) × stems (rows), cells shaded by energy — the "together" view at a glance.
- **Per-stem detail (toggle):** movement summary (contour, step/leap, range), groove chips, optional piano-roll thumbnail.
- **Harmony line:** chords per section + harmonic-rhythm descriptor + optional Roman numerals behind detail.
- **Mix balance bar:** low/mid/high energy split.

- [ ] Show analysis blocks only after a reference exists; keep agent/tool detail in expandable sections.
- [ ] Live progress while deep analysis runs (if SSE).
- [ ] Verify:
```bash
cd apps/web && npm run typecheck && node --test lib/*.test.mjs
```

## Phase 8: End-to-End & Compose-From-Reference Bridge

**Files:**
- Modify: `README.md`, optional `docs/demo-script.md`
- (Bridge only — full reference-guided composition stays in `plans/chat-musical-mvp.md` Phase 6)

- [ ] Document a deep-analysis demo: upload multi-instrument file → see stems, timbre, movement, arrangement, harmonic rhythm → ask "why does the chorus feel bigger?" → get an evidence-grounded answer.
- [ ] Note how transcribed per-stem `Note` lists can later seed the composer's `notes_summary` (do not implement the full bridge here).
- [ ] Full suite:
```bash
cd apps/api && python -m pytest
cd apps/web && npm run typecheck && node --test lib/*.test.mjs
docker compose build api
```

---

## Open Decisions

- **Orchestrator location:** extend `LibrosaAnalyzer` vs new `DeepAnalyzer` wrapping it behind the same `AudioAnalyzer` port (lean toward new `DeepAnalyzer`, keep `LibrosaAnalyzer` as the quick/fallback path).
- **API pattern for slow analysis:** SSE progress (recommended) vs job polling (Phase 6).
- **Drum sub-classification depth:** coarse kick/snare/hat vs full GM kit — start coarse.
- **Roman-numeral functional analysis:** ship as optional/behind-detail; chord + harmonic-rhythm are the priority.
- **Model weight management:** bake Demucs/basic-pitch weights into the image vs mount a cache volume (lean toward baking for reproducible GPU container deploys).
- **Confidence calibration:** separation/transcription quality varies by genre; keep all derived confidences conservative and visibly probabilistic.

## Non-Goals (inherited from PRODUCT.md)

- No YouTube ingestion; local files only.
- No perfect transcription or perfect separation — estimates with confidence.
- No persistent analysis library / database for the MVP.
- Not a full DAW; the mixer/roster stays lightweight and post-analysis.
