# Deep Harmonic Analysis Implementation Plan

> **Canonical plan for `feat/music-analysis-quality`:** This is the plan that
> should guide the current deep harmonic analysis work. It supersedes the broader
> alternate `deep-music-analysis` direction for this branch by narrowing the
> implementation to default local harmonic analysis: stems, tempo/grid, key,
> triad chords, and A/B/C structure.
>
> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the current shallow mono-mix reference analysis with a deep, default harmonic listener that uses stem separation, beat/bar-aware harmony, key candidates, triad chord estimates, and A/B/C form detection for full songs.

**Architecture:** Keep the existing clean architecture boundaries. Add a new deep analysis path behind the existing `AudioAnalyzer` port; it uses Demucs for source separation, falls back internally when separation fails, and returns a compact `ReferenceProfile` without leaking raw spectrograms, chroma matrices, tensors, or provider details.

**Tech Stack:** FastAPI, Pydantic v2, librosa, NumPy, music21, Demucs/PyTorch, optional Essentia/HPCP key extraction, Next.js, React, TypeScript, Docker container runtime.

---

## Source Documents

- `PRODUCT.md`: chat-first MVP behavior, local-file-only reference analysis, probabilistic musical claims.
- `DESIGN.md`: contextual analysis details, compact UI, no dashboard-first workflow.
- `docs/architecture.md`: clean architecture boundaries and reference/composition separation.
- `docs/chat-api-direction.md`: current split endpoints and future chat orchestration direction.
- `plans/chat-musical-mvp.md`: active MVP implementation roadmap.
- `plans/deep-music-analysis.md`: broader future plan from `feat/music-analysis-deep`; this plan borrows stem separation but narrows scope to key, chords, and A/B/C structure.

## Decisions Locked In

- Analyze full songs, not short loops as the primary target.
- Deep analysis is the default product behavior.
- Do not expose a quick/deep mode selector.
- Try Demucs stem separation from the start.
- If Demucs fails, continue inside the same analysis run using harmonic/percussive separation or whole-mix fallback and lower confidence.
- Prioritize key and chords over generic energy/dynamics.
- Estimate triads first: major, minor, diminished, unknown.
- Align chords and sections to bars.
- Assume `4/4` in the first version.
- Label form as `A/B/C`, not `verse/chorus/bridge`.
- Return structured, renderable evidence; text summaries are views over the data.
- Keep composition agents decoupled from raw audio, Demucs, librosa, Essentia, and analysis internals.

## Product Output Shape

The final user-facing result should support answers and UI blocks like:

```text
Likely key: A minor, with C major as the closest relative-key alternative.
Main progression: probably Am - F - C - G.
Structure: A / B / C / B, aligned to bars.
Section B repeats with similar harmonic material.
Chord confidence is medium because bars 17-24 are stable, but the bass and harmony stems disagree around bar 25.
```

The frontend should eventually render a timeline rather than treat the analysis as plain text:

```text
Bars:      1      9      17     33     49
Sections: A      B      C      B      D
Chords:   Am ... Am-F-C-G ... F-C-G-Am ...
```

## Target Domain Contract

Extend `apps/api/music_assistant/domain/audio_profile.py` with compact models that keep compatibility with the current `ReferenceProfile` while moving the useful data into explicit harmonic and structural fields.

```python
class AnalysisNote(BaseModel):
    code: str
    message: str
    severity: Literal["info", "warning", "error"] = "info"


class TempoCandidate(BaseModel):
    bpm: float
    confidence: float = Field(ge=0.0, le=1.0)
    relation: Literal["primary", "half_time", "double_time", "alternate"] = "primary"


class TempoProfile(BaseModel):
    primary_bpm: float | None = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    candidates: list[TempoCandidate] = Field(default_factory=list, max_length=6)
    beat_grid_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    bar_grid_confidence: float = Field(default=0.0, ge=0.0, le=1.0)


class MeterProfile(BaseModel):
    time_signature: tuple[int, int] = (4, 4)
    source: Literal["assumed", "estimated"] = "assumed"
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)


class KeyCandidate(BaseModel):
    key: str
    mode: Literal["major", "minor", "unknown"]
    confidence: float = Field(ge=0.0, le=1.0)


class KeyProfile(BaseModel):
    primary: KeyCandidate | None = None
    candidates: list[KeyCandidate] = Field(default_factory=list, max_length=8)
    relative_key_ambiguity: bool = False
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)


class ChordCandidate(BaseModel):
    root: str
    quality: Literal["major", "minor", "diminished", "unknown"]
    label: str
    confidence: float = Field(ge=0.0, le=1.0)


class ChordSpan(BaseModel):
    start_bar: int
    end_bar: int
    start_beat: float = 1.0
    end_beat: float = 1.0
    start_seconds: float
    end_seconds: float
    candidates: list[ChordCandidate] = Field(default_factory=list, max_length=5)
    chosen: ChordCandidate | None = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)


class ProgressionEstimate(BaseModel):
    start_bar: int
    end_bar: int
    chords: list[str] = Field(default_factory=list, max_length=16)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    repetitions: int = 1


class HarmonicProfile(BaseModel):
    key: KeyProfile = Field(default_factory=KeyProfile)
    chord_spans: list[ChordSpan] = Field(default_factory=list, max_length=512)
    progressions: list[ProgressionEstimate] = Field(default_factory=list, max_length=32)
    harmonic_rhythm_label: str = ""
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)


class StructuralSection(BaseModel):
    label: str
    start_bar: int
    end_bar: int
    start_seconds: float
    end_seconds: float
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    main_progression: list[str] = Field(default_factory=list, max_length=16)


class StructureProfile(BaseModel):
    sections: list[StructuralSection] = Field(default_factory=list, max_length=64)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)


class StemProfile(BaseModel):
    name: str
    role: Literal["percussion", "bass", "vocal", "harmony", "mix", "other"] = "other"
    artifact_uri: str | None = None
    available: bool = True
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
```

`MusicProfile` should keep existing fields during migration and add:

```python
tempo: TempoProfile | None = None
meter: MeterProfile = Field(default_factory=MeterProfile)
harmony: HarmonicProfile | None = None
structure: StructureProfile | None = None
analysis_notes: list[AnalysisNote] = Field(default_factory=list)
```

Existing `tempo_bpm`, `tempo_confidence`, `key`, `key_confidence`, `chord_estimates`, and `sections` can be populated as compatibility views derived from the richer fields until the frontend is migrated.

## File Map

### Backend Domain

- Modify `apps/api/music_assistant/domain/audio_profile.py`
  - Add tempo, meter, key, chord, harmony, structure, stem, and analysis note models.
  - Add bounded list lengths for renderable outputs.
  - Keep current fields available during migration.

### Backend Ports

- Modify `apps/api/music_assistant/ports/stem_separator.py`
  - Return a compact stem bundle/profile, not Demucs internals.
- Keep `apps/api/music_assistant/ports/audio_analyzer.py`
  - `AudioAnalyzer.analyze(source: ReferenceSource) -> ReferenceProfile` remains the boundary.

### Backend Infrastructure

- Modify `apps/api/music_assistant/infrastructure/mir/demucs_separator.py`
  - Implement Demucs separation for `drums`, `bass`, `vocals`, `other`.
  - Save stems under the analysis upload/job directory.
  - Return compact stem metadata.
- Create `apps/api/music_assistant/infrastructure/mir/deep_harmonic_analyzer.py`
  - Orchestrate the full deep harmonic pipeline behind `AudioAnalyzer`.
- Create `apps/api/music_assistant/infrastructure/mir/harmonic_source.py`
  - Build `bass + other` harmonic source when stems exist.
  - Build HPSS harmonic fallback when stems are unavailable.
- Create `apps/api/music_assistant/infrastructure/mir/tempo_grid.py`
  - Estimate tempo candidates, beat grid, and bar grid assuming `4/4`.
- Create `apps/api/music_assistant/infrastructure/mir/key_features.py`
  - Estimate key candidates from harmonic source using CQT/HPCP-style features.
- Create `apps/api/music_assistant/infrastructure/mir/chord_features.py`
  - Estimate triad chord candidates per bar and smooth the chord timeline.
- Create `apps/api/music_assistant/infrastructure/mir/structure_features.py`
  - Group repeated progressions into A/B/C bar-aligned sections.
- Keep `apps/api/music_assistant/infrastructure/mir/librosa_analyzer.py`
  - Use only as compatibility/fallback helper during migration.

### Backend Application

- Modify `apps/api/music_assistant/application/analyze_reference.py`
  - Keep `AnalyzeReference` thin.
  - Continue to call the injected `AudioAnalyzer`.
  - Do not put Demucs, harmony, or routing logic in the use case.
- Later modify `apps/api/music_assistant/application/answer_music_question.py`
  - Answer from `harmony` and `structure` evidence.

### Backend Interface

- Modify `apps/api/music_assistant/interfaces/api.py`
  - `/references/analyze` should use `DeepHarmonicAnalyzer` by default.
  - Add streaming progress after the contract and analyzer stabilize.
- Modify `apps/api/music_assistant/interfaces/api_models.py`
  - Add analysis progress SSE models when streaming is introduced.

### Frontend

- Modify `apps/web/lib/types.ts`
  - Mirror the new Pydantic models.
- Modify `apps/web/lib/referenceProfileView.mjs`
  - Read new `harmony` and `structure` fields first; fall back to legacy fields during migration.
- Modify `apps/web/components/AnalysisResultBlock.tsx`
  - Render key candidates, chord progressions, and A/B/C structure.
  - Stop making energy the main analysis detail.
- Optional create `apps/web/components/HarmonyTimeline.tsx`
  - Render bar-aligned sections and chord summaries.

### Ops

- Modify `apps/api/pyproject.toml`
  - Add Demucs/PyTorch dependencies in a way compatible with the Docker runtime.
- Modify `apps/api/Dockerfile`
  - Install system/audio dependencies needed by Demucs and librosa.
  - Configure model cache location.

## Phase 0: Contract First

**Files:**
- Modify `apps/api/music_assistant/domain/audio_profile.py`
- Modify `apps/web/lib/types.ts`
- Create `apps/api/tests/test_deep_harmonic_contract.py`

- [x] Add the new Pydantic models listed in "Target Domain Contract".
- [x] Keep legacy `MusicProfile` fields so existing API and frontend tests still pass.
- [x] Add validators or `max_length` constraints so no raw feature arrays can leak into `ReferenceProfile`.
- [x] Add TypeScript mirrors for every new model in `apps/web/lib/types.ts`.
- [x] Write contract tests that build a full `ReferenceProfile` with:
  - one tempo profile;
  - assumed `4/4` meter;
  - two key candidates;
  - four bar-aligned chord spans;
  - two progression estimates;
  - three A/B/C structural sections;
  - four stem profiles.
- [x] Run:

```bash
cd apps/api
python -m pytest tests/test_deep_harmonic_contract.py
```

- [x] Run:

```bash
cd apps/web
npm run typecheck
```

## Phase 1: Stem Separation With Demucs

**Files:**
- Modify `apps/api/music_assistant/ports/stem_separator.py`
- Modify `apps/api/music_assistant/infrastructure/mir/demucs_separator.py`
- Modify `apps/api/pyproject.toml`
- Modify `apps/api/Dockerfile`
- Create `apps/api/tests/test_demucs_separator.py`

- [x] Define a compact return shape for separation:

```python
class SeparatedStem(BaseModel):
    name: Literal["drums", "bass", "vocals", "other", "mix"]
    role: Literal["percussion", "bass", "vocal", "harmony", "mix", "other"]
    path: str
    artifact_uri: str | None = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
```

- [x] Implement `DemucsSeparator.separate(source)` so it:
  - resolves only local paths/file URIs;
  - runs Demucs `htdemucs`;
  - writes separated stems into an analysis-specific directory;
  - returns `drums`, `bass`, `vocals`, and `other` when successful.
- [ ] On Demucs failure, return a single `mix` pseudo-stem and an analysis note from the analyzer layer. `mix` fallback is implemented; analyzer-level notes remain for the orchestrator phase.
- [x] Guard heavy tests with an environment flag such as `LLMINEM_RUN_DEMUCS_TESTS=1` so normal local test runs stay fast.
- [x] Run:

```bash
cd apps/api
python -m pytest tests/test_demucs_separator.py
```

- [ ] Run:

```bash
docker compose build api
```

## Phase 2: Harmonic Source Builder

**Files:**
- Create `apps/api/music_assistant/infrastructure/mir/harmonic_source.py`
- Create `apps/api/tests/test_harmonic_source.py`

- [x] Implement `build_harmonic_source(stems, output_path)`:
  - when `bass` and `other` exist, mix those stems into a harmonic analysis file;
  - reduce or exclude `vocals` for the first version because vocals can distort chord estimates;
  - ignore `drums` for harmony;
  - when separated stems are unavailable, use librosa HPSS to build a harmonic component from the mix.
- [x] Return a small object with:

```python
class HarmonicSource(BaseModel):
    path: str
    source_kind: Literal["stems_bass_other", "hpss_harmonic", "mix"]
    confidence_adjustment: float
    notes: list[AnalysisNote] = Field(default_factory=list)
```

- [x] Test that `bass + other` is preferred when available.
- [x] Test that HPSS fallback emits an analysis note and lowers confidence. (Also: raw-mix last-resort fallback when HPSS errors; `bass`-without-`other` falls back to HPSS; empty stems raises.)
- [x] Run:

```bash
cd apps/api
python -m pytest tests/test_harmonic_source.py
```

## Phase 3: Tempo, Beat Grid, And Assumed 4/4 Bar Grid

**Files:**
- Create `apps/api/music_assistant/infrastructure/mir/tempo_grid.py`
- Create `apps/api/tests/test_tempo_grid.py`

- [x] Implement tempo candidate extraction from the full mix and, when available, the drum stem. (Beat input prefers `drum_path`; `beat_tracker` is injectable for fast unit tests.)
- [x] Return primary, half-time, and double-time candidates.
- [x] Estimate beat times and compute confidence from beat interval stability.
- [x] Build bars by grouping beats in fours. (Returned in an internal `TempoGrid` dataclass with `beat_times`/`bar_times`, not leaked into `ReferenceProfile`.)
- [x] Return `MeterProfile(time_signature=(4, 4), source="assumed", confidence=0.5)`.
- [x] Test stable synthetic click/audio produces:
  - primary tempo near expected BPM;
  - half/double candidates;
  - bars with four beats each;
  - nonzero beat and bar confidence.
  - (Also: drum-path preference, and graceful degradation when no beats are found.)
- [x] Run:

```bash
cd apps/api
python -m pytest tests/test_tempo_grid.py
```

## Phase 4: Key Candidates

**Files:**
- Create `apps/api/music_assistant/infrastructure/mir/key_features.py`
- Create `apps/api/tests/test_key_features.py`

- [x] Estimate key candidates from the harmonic source, not the full mix when stems or HPSS are available. (`estimate_key(harmonic_path, ...)`; `confidence_adjustment` carries the HPSS/mix penalty from `HarmonicSource`.)
- [x] Use CQT/chroma or HPCP-style pitch-class summaries with tuning-aware preprocessing. (Default provider: `chroma_cqt` with `estimate_tuning`; pure scoring is provider-independent.)
- [x] Return multiple candidates, including relative major/minor alternatives when close. (`relative_key_ambiguity` flagged when top two are a relative pair within margin.)
- [~] Populate compatibility fields (`audio.key`, `audio.key_confidence`) — deferred to the Phase 7 orchestrator, which composes `f"{primary.key}"`/`primary.confidence` into legacy fields. `KeyCandidate.key` already carries the full label (e.g. "A minor").
- [x] Test synthetic A minor/C major ambiguous material returns both candidates.
- [x] Test a clear major triad progression returns the expected major key candidate. (Also: empty vector → empty profile; confidence adjustment lowers confidence; injected provider path.)
- [x] Run:

```bash
cd apps/api
python -m pytest tests/test_key_features.py
```

## Phase 5: Triad Chord Estimation Per Bar

**Files:**
- Create `apps/api/music_assistant/infrastructure/mir/chord_features.py`
- Create `apps/api/tests/test_chord_features.py`

- [x] Define triad templates for major, minor, and diminished chords.
- [x] Aggregate harmonic-source chroma by bar. (`estimate_chords` slices a chroma matrix along `bar_times`; pure `chords_from_bar_chromas` takes per-bar vectors.)
- [x] Produce up to five candidates per bar.
- [x] Pick `chosen` chord only when confidence is above a conservative threshold. (Confidence leans on candidate separation so flat/ambiguous bars stay unchosen.)
- [x] Smooth the bar sequence so isolated one-bar outliers are corrected when neighbors strongly agree.
- [~] Populate legacy `audio.chord_estimates` as time-range compatibility summaries — deferred to the Phase 7 orchestrator (ChordSpan → ChordEstimate).
- [x] Test a synthetic four-bar `Am - F - C - G` fixture returns that progression as chosen triads.
- [x] Test smoothing removes a one-bar spurious chord between matching neighbors. (Also: ≤5 candidates/bar, low-confidence bar has no `chosen`, diminished triad recognized.)
- [x] Run:

```bash
cd apps/api
python -m pytest tests/test_chord_features.py
```

## Phase 6: Progressions And A/B/C Structure

**Files:**
- Create `apps/api/music_assistant/infrastructure/mir/structure_features.py`
- Create `apps/api/tests/test_structure_features.py`

- [x] Detect repeated chord windows over bar-aligned `ChordSpan` data. (Fixed 4-bar phrase windows; signature = chosen-chord tuple.)
- [x] Create `ProgressionEstimate` entries for repeated progressions. (One per unique signature, with `repetitions` count.)
- [x] Group adjacent bars into structural sections.
- [x] Assign labels `A`, `B`, `C`, etc. by repeated harmonic similarity. (Same signature → same letter; consecutive same-label windows merge.)
- [x] Keep labels abstract. Do not emit `verse`, `chorus`, or `bridge`.
- [~] Populate legacy `audio.sections` as compatibility summaries from `StructureProfile` — deferred to the Phase 7 orchestrator.
- [x] Test a synthetic section pattern `A B C B` returns repeated `B` labels for matching progressions.
- [x] Test section boundaries are integer bars. (Also: consecutive identical phrases merge; empty input; labels stay abstract.)
- [x] Run:

```bash
cd apps/api
python -m pytest tests/test_structure_features.py
```

## Phase 7: Deep Analyzer Orchestrator

**Files:**
- Create `apps/api/music_assistant/infrastructure/mir/deep_harmonic_analyzer.py`
- Modify `apps/api/music_assistant/interfaces/api.py`
- Create `apps/api/tests/test_deep_harmonic_analyzer.py`
- Modify `apps/api/tests/test_reference_analysis_api.py`

- [x] Implement `DeepHarmonicAnalyzer.analyze(source)` as the default `AudioAnalyzer` for uploads. (Every stage injectable; real feature modules wired as defaults.)
- [x] Orchestration order:
  1. resolve local source path;
  2. run Demucs separation;
  3. build harmonic source;
  4. estimate tempo/beat/bar grid;
  5. estimate key candidates;
  6. estimate triad chords per bar;
  7. detect progressions and A/B/C sections;
  8. assemble `ReferenceProfile`;
  9. fill compatibility fields (`key`, `tempo_bpm`, `chord_estimates`, `sections`).
- [x] If Demucs fails, continue with HPSS/mix fallback and add an `AnalysisNote`. (`separation_unavailable` note when only the mix is available; HPSS note flows from the harmonic source.)
- [x] If beat/bar grid confidence is low, keep key candidates but lower chord/structure confidence. (`weak_bar_grid` note; harmony confidence blends key/chord/grid confidence.)
- [x] Update `/references/analyze` to instantiate `DeepHarmonicAnalyzer`. (Via `api._reference_analyzer()` factory, monkeypatchable in tests.)
- [x] Test the orchestrator with fake separator/feature modules so the main test is fast.
- [x] Test API upload still returns a `ReferenceProfile` with populated legacy fields and new `harmony`/`structure` fields. (Analyzer faked at the route boundary; rejection/failure paths kept.)
- [x] Run:

```bash
cd apps/api
python -m pytest tests/test_deep_harmonic_analyzer.py tests/test_reference_analysis_api.py tests/test_api_architecture.py
```

## Phase 8: Analysis Progress Streaming

**Files:**
- Modify `apps/api/music_assistant/interfaces/api_models.py`
- Modify `apps/api/music_assistant/interfaces/api.py`
- Modify `apps/web/app/api/references/analyze/route.ts`
- Create `apps/api/tests/test_reference_analysis_stream.py`

- [ ] Add SSE event models:

```python
class AnalysisProgressEvent(BaseModel):
    type: Literal[
        "accepted",
        "separating_stems",
        "building_harmonic_source",
        "estimating_tempo_grid",
        "estimating_key",
        "estimating_chords",
        "detecting_structure",
        "done",
        "error",
    ]
    message: str
```

- [ ] Add a streaming endpoint for analysis progress while keeping the product behavior as a single "analyze this song" action.
- [ ] The UI should call the streaming path for uploads.
- [ ] The final `done` event should include the complete `ReferenceProfile`.
- [ ] Test event order with fake analyzer stages.
- [ ] Run:

```bash
cd apps/api
python -m pytest tests/test_reference_analysis_stream.py
```

## Phase 9: Frontend Rendering

**Files:**
- Modify `apps/web/lib/types.ts`
- Modify `apps/web/lib/referenceProfileView.mjs`
- Modify `apps/web/lib/referenceProfileView.test.mjs`
- Modify `apps/web/components/AnalysisResultBlock.tsx`
- Optional create `apps/web/components/HarmonyTimeline.tsx`

- [ ] Display key candidates with confidence.
- [ ] Display main repeated progression.
- [ ] Display A/B/C section timeline aligned to bars.
- [ ] Display probable triads by section or progression.
- [ ] Display analysis notes, especially fallback notes.
- [ ] Remove energy as a primary visible block. Keep legacy energy rendering hidden or secondary while compatibility fields exist.
- [ ] Test formatting helpers for:
  - key candidate summary;
  - chord progression summary;
  - A/B/C timeline labels;
  - fallback analysis notes.
- [ ] Run:

```bash
cd apps/web
npm run typecheck
node --test lib/referenceProfileView.test.mjs
```

## Phase 10: Evidence-Grounded Music Q&A

**Files:**
- Modify `apps/api/music_assistant/application/answer_music_question.py`
- Create `apps/api/tests/test_answer_music_question.py`

- [ ] Add a deterministic fallback explainer over `HarmonicProfile` and `StructureProfile`.
- [ ] Answer key questions from `KeyProfile`.
- [ ] Answer chord questions from `ProgressionEstimate` and `ChordSpan`.
- [ ] Answer structure questions from `StructureProfile`.
- [ ] Use probabilistic language:
  - "likely" for key;
  - "probably" for chords/progressions;
  - "appears to repeat" for A/B/C structure.
- [ ] Include evidence strings with bars and confidence.
- [ ] Run:

```bash
cd apps/api
python -m pytest tests/test_answer_music_question.py
```

## Verification Before Completion

Run the focused tests as each phase lands. Before calling the feature complete, run:

```bash
cd apps/api
python -m pytest
```

```bash
cd apps/web
npm run typecheck
node --test lib/trackMixerLogic.test.mjs
node --test lib/referenceProfileView.test.mjs
```

```bash
docker compose config
docker compose build api
```

## Explicit Non-Goals For This Plan

- No YouTube ingestion.
- No web lookup for title/key/chords.
- No Basic Pitch transcription.
- No per-instrument melody analysis.
- No voice-leading analysis.
- No piano-roll UI.
- No semantic `verse`/`chorus`/`bridge` labels.
- No exposed quick/deep mode.
- No database or persisted reference library.
- No promise of perfect chord transcription.

## Future Work After This Plan

- Optional web evidence reconciliation when the song title/artist is known.
- Basic Pitch transcription for vocals/bass/other.
- Melody contour and voice-leading analysis.
- Richer Roman numeral analysis once triad detection is reliable.
- Stem playback controls if the analysis UI benefits from them.
- Better meter estimation beyond assumed `4/4`.
