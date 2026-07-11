# Deep Music Analysis Plan — Broader Listening Vision (post-MVP)

> **Status: future vision, not the active branch plan.** The active, canonical plan
> for `feat/music-analysis-quality` is [`plans/deep-harmonic-analysis.md`](./deep-harmonic-analysis.md),
> which narrows scope to the harmonic MVP (stems → tempo/bar grid → key → triads →
> A/B/C structure). **This document is what we build *after* that MVP lands.** It
> extends the same domain contract and the same `AudioAnalyzer` port toward
> per-instrument, melodic, and timbral listening.
>
> **For agentic workers:** Do not start here. Finish `deep-harmonic-analysis.md`
> first. Then pick extension tracks from this plan. Steps use checkbox (`- [ ]`)
> syntax for tracking.

**Goal:** Once harmonic analysis (key, chords, structure) is reliable, extend the
listener into a deep, per-instrument + ensemble analysis: transcribe each stem,
and extract spectral ("Fourier") timbre, melodic-movement / voice-leading,
per-stem dynamics, and groove — all mapped to plain music-theory interpretation
and surfaced in the chat UI.

**Runtime target:** Container on a Google GPU. Heavy dependencies (Demucs/torch,
basic-pitch/tensorflow) are acceptable. Analysis runs server-side; the UI renders
compact results.

**Tech stack:** FastAPI, Pydantic v2, librosa, Demucs (torch), **basic-pitch
(Spotify)**, music21, NumPy, Next.js/React/TypeScript, Docker (CUDA base image).

---

## Relationship To The Harmonic MVP

The harmonic MVP (`deep-harmonic-analysis.md`) already delivers a chunk of the
original "deep analysis" idea. This plan does **not** redo that work. Concretely:

| Original idea | Status after harmonic MVP |
| --- | --- |
| A. Source separation (Demucs) | ✅ **Delivered** — `DemucsSeparator` returns drums/bass/vocals/other with mix fallback. |
| F. Harmony + harmonic rhythm | ✅ **Delivered** — `HarmonicProfile` (key candidates, bar-aligned triads, progressions). |
| H-(structure). A/B/C form | ✅ **Delivered** — `StructureProfile` bar-aligned sections. |
| B. Per-stem transcription (basic-pitch) | ⬜ **Extension** (this plan). |
| C. Spectral / "Fourier" timbre | ⬜ **Extension** (this plan). |
| D. Melodic movement / voice-leading | ⬜ **Extension** (this plan). |
| E. Per-stem dynamics over time | ⬜ **Extension** (this plan). |
| G. Rhythm / groove (swing, syncopation) | ⬜ **Extension** (this plan). |
| H-(ensemble). Arrangement "together" view | ⬜ **Extension** (this plan). |

So the remaining work is: **transcription, timbre, movement/voice-leading, per-stem
dynamics, groove, and the ensemble arrangement view.**

## Design Principles (shared with the harmonic MVP)

1. **Bar-based, not seconds-based.** Every new symbolic/structural field is keyed to
   `start_bar`/`end_bar` (with `start_beat`/`end_beat` where finer), matching the
   harmonic MVP contract and the composer's `SongState`. Seconds remain only as a
   secondary view for playback alignment. *(This is the key alignment decision
   adopted from the harmonic plan; the earlier seconds-first draft is superseded.)*
2. **Evidence + uncertainty.** Every derived claim carries a confidence and is
   phrased probabilistically. No estimate is presented as ground truth.
3. **Compact domain, no raw arrays.** No FFT bins, chroma matrices, or torch tensors
   leak into `ReferenceProfile`. Time series are bounded point/summary lists with
   `max_length` like the harmonic MVP models.
4. **Engine-agnostic contract.** Consumers depend on domain models, never on
   Demucs/basic-pitch internals. Swapping an engine must not change the profile shape.
5. **Graceful degradation.** If transcription fails on a stem, fall back to
   spectral-only features for that stem and lower confidence — never hard-fail the run.
6. **Chat-first surfacing.** Results render as compact, expandable analysis blocks,
   not a permanent dashboard.

---

## The Extension Ideas — Technique, Musical Payoff, Surfacing

### B. Per-stem transcription → notes — *basic-pitch* (pitched stems) + onset detection (drums)
- **Technique:** basic-pitch on bass/vocals/other → `Note` lists (reuse
  `domain/song_state.Note`: MIDI pitch, **bar + start_beat**, duration in beats, via
  the bar grid the harmonic MVP already computes). Drums → onset-only events bucketed
  into a coarse kit (kick/snare/hat) by spectral band.
- **Buys:** A symbolic per-instrument representation → foundation for movement and
  voice-leading. Closes the loop with the composer, which already speaks
  `SongState`/`Note`; a transcribed reference can later seed `notes_summary`.
- **Surfacing:** Per-stem note count, register (lowest/highest), optional piano-roll
  thumbnail behind a detail toggle.

### C. Spectral / "Fourier" timbre — *librosa STFT family*, per stem + mix
- **Technique:** STFT features summarized over time: spectral centroid (brightness),
  bandwidth, rolloff, flatness (noisiness/tonalness), spectral contrast, ZCR, and a
  low/mid/high band-energy split. MFCC summary for timbre fingerprinting.
- **Buys:** Objective timbre descriptors ("bright/thin" vs "dark/full"), mix balance
  (who owns which band), noisiness (distortion/percussiveness). The literal "Fourier"
  layer, made musically legible.
- **Surfacing:** Per-stem timbre chips (*bright • mid-heavy • sustained*) + a mix
  frequency-balance bar.

### D. Melodic movement / voice-leading — *over transcribed notes*
- **Technique (per melodic stem):** contour (up/down/static), interval histogram,
  stepwise-vs-leap ratio, range/tessitura, avg note duration, rhythmic density per bar.
  **Between stems:** bass↔lead voice-leading per **bar-aligned** harmonic window —
  motion type (parallel/contrary/oblique/similar), avg voice spacing, bass-root-to-
  melody interval.
- **Buys:** Directly answers "movimiento melódico / conducción de voces". Smooth
  stepwise vs angular leaping; bass and melody parallel vs independent. Teachable,
  music-theory-grounded output.
- **Surfacing:** Movement mini-summary per melodic stem + a bass/melody relationship
  line ("mostly contrary motion, ~stepwise melody").

### E. Per-stem dynamics over time — *RMS envelopes per stem*
- **Technique:** Per-stem normalized RMS keyed to bars, plus crescendo/diminuendo
  detection (sustained slope). Aligns loudness to the bar grid and the A/B/C sections.
- **Buys:** "Why does this section feel bigger?" answered concretely: *drums and
  'other' enter and bass loudness doubles at bar 17*. Maps energy to arrangement
  events, not a single global curve.
- **Surfacing:** Stacked per-stem energy aligned to the section/bar timeline + textual
  "build/drop" callouts.

### G. Rhythm / groove — *onsets + the existing beat grid*
- **Technique:** From drums + the bar grid: swing/straight feel (off-beat onset
  timing), syncopation score (onsets off strong beats), per-stem rhythmic density.
- **Buys:** Groove descriptors — straight vs swung, busy vs sparse, syncopated vs
  on-grid. Ties rhythm to feel.
- **Surfacing:** Groove chips (*straight • syncopated • busy hats*).

### H. Ensemble / arrangement view — *the "together" analysis*
- **Technique:** Combine B–G into a **bar-aligned** arrangement timeline: which
  instruments are active per A/B/C section, their register/role, and interaction
  (call-and-response via alternating energy, density layering).
- **Buys:** The "en conjunto" view — how instruments compose together, not just in
  isolation. Bridge to the composer's `notes_summary` peer context.
- **Surfacing:** An arrangement strip: rows = stems, columns = sections (bars), cells
  = active/role/energy.

> Every numeric feature ships with a short generic interpretation string so the LLM
> explainer (`answer_music_question.py`) grounds answers in evidence.

---

## Domain Contract Extensions (build on the harmonic MVP models)

Add to `apps/api/music_assistant/domain/audio_profile.py`, reusing the harmonic MVP's
bar-keyed style and `max_length` discipline:

- `TimbreProfile` — spectral summary + interpretation (idea C); attach to each stem
  and to the mix.
- `MovementProfile` — contour, interval histogram, step/leap ratio, range, density
  (idea D); per melodic stem.
- `VoiceLeadingProfile` — bar-aligned bass↔lead motion summary (idea D); on the
  ensemble.
- `RhythmProfile` — density, swing, syncopation (idea G); per stem.
- `StemDynamics` — bar-keyed RMS points + build/drop flags (idea E); per stem.
- `EnsembleProfile` — arrangement timeline (section × stem activity/role/energy) +
  `VoiceLeadingProfile` (idea H).
- Extend `StemProfile` with `note_count`, `pitch_low`/`pitch_high`, `timbre`,
  `movement`, `rhythm`, `dynamics`.
- Extend `AudioProfile` with `ensemble: EnsembleProfile | None`.

`StemProfile` already exists from the harmonic MVP; extend it, do not replace it.

## Extension Tracks (each is an independent vertical slice on top of the MVP)

Tracks are ordered by dependency, not by hard phase numbers — pick them up after the
harmonic MVP is green.

### Track 1: Per-stem transcription (basic-pitch)
- [ ] Add `basic-pitch` to `pyproject.toml`; bake weights into the CUDA image.
- [ ] Implement `BasicPitchTranscriber.transcribe_melody(source) -> list[Note]`,
  quantized to the harmonic MVP **bar grid** (bar + start_beat, duration in beats).
- [ ] Drums → onset-only coarse kit buckets by spectral band.
- [ ] Tests on synthetic `Note` lists for determinism (no audio needed).

### Track 2: Spectral / timbre features (per stem + mix)
- [ ] `spectral_features.py`: centroid/bandwidth/rolloff/flatness/contrast/ZCR +
  low/mid/high split + MFCC → `TimbreProfile` with interpretation strings.
- [ ] Fill `StemProfile.timbre` and a mix-level timbre.
- [ ] Tests on synthetic bright vs dark signals.

### Track 3: Melodic movement (per stem, over transcribed notes)
- [ ] `movement_features.py`: contour, interval histogram, step/leap ratio, range,
  per-bar density → `MovementProfile`.
- [ ] Tests on synthetic stepwise vs leaping note lists.

### Track 4: Per-stem dynamics (bar-aligned)
- [ ] `stem_dynamics.py`: per-stem RMS keyed to bars + build/drop detection →
  `StemDynamics`, aligned to the A/B/C structure.
- [ ] Tests asserting energy rises map to the right bars/sections.

### Track 5: Groove / rhythm
- [ ] `rhythm_features.py`: swing ratio, syncopation, per-stem density from onsets +
  bar grid → `RhythmProfile`.
- [ ] Tests on synthetic straight vs swung patterns.

### Track 6: Ensemble / voice-leading ("together")
- [ ] Cross-stem bass↔lead voice-leading per bar window → `VoiceLeadingProfile`.
- [ ] Arrangement timeline (section × stem activity/role/energy) → `EnsembleProfile`.
- [ ] Tests on synthetic multi-stem note/energy fixtures.

### Track 7: Explanation + UI
- [ ] Extend `answer_music_question.py` to cite timbre, movement, voice-leading,
  groove, and arrangement events (with confidence, probabilistic phrasing).
- [ ] UI: extend the analysis block with a stem roster (timbre chips, play/solo),
  a bar-aligned arrangement strip, per-stem movement/groove behind detail toggles,
  and a mix frequency-balance bar. Keep it compact / expandable (DESIGN.md).

### Track 8: Compose-from-reference bridge
- [ ] Document how transcribed per-stem `Note` lists can seed the composer's
  `notes_summary` (full reference-guided composition stays in `chat-musical-mvp.md`).

---

## Open Decisions

- **Transcription confidence per genre** — basic-pitch quality varies; keep derived
  confidences conservative and visibly probabilistic.
- **Drum sub-classification depth** — start coarse (kick/snare/hat), not full GM kit.
- **Model weight management** — bake basic-pitch weights into the image vs cache
  volume (lean toward baking for reproducible GPU deploys).
- **Streaming** — reuse the harmonic MVP's analysis SSE stages; add
  `transcribing`/`analyzing-stems` events rather than a new endpoint.

## Non-Goals (inherited from PRODUCT.md)

- No YouTube ingestion; local files only.
- No perfect transcription or separation — estimates with confidence.
- No persistent analysis library / database for the MVP.
- Not a full DAW; the roster/mixer stays lightweight and post-analysis.
