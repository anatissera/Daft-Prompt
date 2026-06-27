# Harmonic Analysis V3: Evidence Hardening Plan

> **Canonical plan for `feat/harmonic-analysis-v3`.** This plan continues the work
> recorded in `docs/harmonic-analysis-learnings.md` after phases 8-10 and the V2
> hardening pass. It does NOT start `plans/deep-music-analysis.md`. It improves the
> existing evidence pipeline so that when the analyzer is uncertain, it fails in an
> informative way rather than a misleading one.

**Goal:** Make the harmonic MVP a more trustworthy "draft listener" by finishing
work that is already partially built, adding the single highest-leverage accuracy
signals (bass-informed roots, downbeat phase), and being explicit when the
analysis is simply not useful.

**Non-goals (unchanged from the harmonic plan):** no YouTube ingestion, no
database, no external chord/metadata APIs, no Basic Pitch, no Essentia, no
semantic verse/chorus labels, no new heavy MIR engine.

---

## Why This Plan Exists (Review Findings)

An independent review of `feat/music-analysis-quality` (phases 8-10 + V2 hardening)
found the work is architecturally sound, honest in its copy, and fully tested
(143 backend + 16 frontend tests green). It also surfaced concrete gaps:

1. **`section_features.py` is wired but starved.** The orchestrator calls
   `section_detector(chord_spans)` with no `energy_by_bar` or
   `stem_activity_by_bar`, so the module falls back to chord novelty only - the
   exact thing it was built to improve. Its arrangement/energy logic is dead code
   in production. (Matches learnings gap #4 and next-step #1.)
2. **Chord roots ignore the bass.** Triads are scored by template fit against the
   harmonic-source chroma. The bass stem (a strong root cue) is not consulted.
   (Learnings gap #1.)
3. **Bar-grid phase errors cascade.** A wrong first-downbeat offset makes every
   downstream chord/section coherent-but-shifted. No phase sanity check exists.
   (Learnings gap #3.)
4. **No usefulness gate.** When key + chords + grid + structure are all weak, the
   summary still leads with candidate details instead of saying so plainly.
   (Learnings gap #6.)
5. **Tuning is coupled to labeling.** Both key and chord chroma use `tuning=0.0`.
   Labeling at A=440 is correct, but the chroma used for *scoring* should be
   tuning-corrected so detuned recordings are not systematically mis-scored.
6. **Minor correctness/cleanup:** `"chorus"` routes to the chord branch (not
   structure) in `answer_music_question.py`; three overlapping structure
   heuristics are hard to reason about; `DeepHarmonicAnalyzer.analyze_with_progress`
   is buffered dead code (real streaming lives in the API queue/thread).

---

## Phase 1: Feed Real Energy/Activity Into Section Detection

**Files:**
- Create `apps/api/llm_band/infrastructure/mir/bar_energy.py`
- Create `apps/api/tests/test_bar_energy.py`
- Modify `apps/api/llm_band/infrastructure/mir/deep_harmonic_analyzer.py`
- Modify `apps/api/tests/test_deep_harmonic_analyzer.py`

- [x] Add `per_bar_energy(audio_path, bar_times, end_seconds, *, rms_provider=None)`
  returning a normalized per-bar RMS list aligned to the bar grid.
- [x] Add `per_stem_activity_by_bar(stem_paths, bar_times, end_seconds, ...)`
  returning per-bar `{stem_name: activity}` dicts, each stem self-normalized.
- [x] Keep audio I/O behind an injectable `rms_provider` so logic is unit-testable
  without audio.
- [x] Wire both into the orchestrator and pass them to `section_detector`. Guard
  with safe wrappers so a missing/unreadable file degrades to empty signals.
- [x] Update the orchestrator test fake so `section_detector` accepts the new
  keyword signals.
- [x] Test: per-bar energy means align to bars; stem activity produces one dict
  per bar; the orchestrator passes non-empty signals when stems and bars exist.
- [x] Run: `python -m pytest tests/test_bar_energy.py tests/test_deep_harmonic_analyzer.py`
  → 149 passed, 1 skipped (full suite).

## Phase 2: Bass-Informed Chord Roots

**Files:**
- Modify `apps/api/llm_band/infrastructure/mir/chord_features.py`
- Modify `apps/api/tests/test_chord_features.py`

- [x] Add an optional per-bar bass-root prior (from a bass chroma/root vote) that
  biases triad-root selection before template scoring. (`bass_root_from_chroma`,
  `estimate_bass_roots`; capped `BASS_ROOT_BONUS` in `_score_bar`.)
- [x] Keep it optional: when no bass signal is available, behavior is unchanged.
  (Orchestrator passes `bass_roots=None` when no bass stem; safe wrapper.)
- [x] Only let the bass break near-ties; it must not override a confident
  non-bass-root triad. (Bonus is capped at 0.06; a clear winner keeps its lead.)
- [x] Test: a bar whose upper harmony is ambiguous but whose bass clearly implies
  a root picks the bass-consistent triad; a confident triad is not overridden.
- [x] Run: `python -m pytest tests/test_chord_features.py` → full suite 154 passed.

## Phase 3: Downbeat / Bar-Phase Offset Check

**Files:**
- Modify `apps/api/llm_band/infrastructure/mir/tempo_grid.py` (or a new
  `bar_phase.py` helper)
- Create/modify the matching test

- [x] Evaluate a small set of bar-start offsets (0..beats_per_bar-1) and pick the
  one whose bar windows produce the most stable chord/energy boundaries.
  (`bar_phase.py`: `choose_bar_phase_offset` scores per-bar `best_triad_fit`.)
- [x] Apply the chosen offset to `bar_times` before chord/structure extraction.
  (Orchestrator `_apply_bar_phase`; corrected `bar_times` feed chords, bass roots,
  and section energy/stem signals.)
- [x] Lower bar-grid confidence when no offset is clearly better. (Below
  `BAR_PHASE_MIN_CONFIDENCE`, keep offset 0 and apply a 0.85 grid penalty.)
- [x] Test: a synthetic grid offset by one beat is recovered to the musically
  correct downbeat.
- [x] Run focused tests. → full suite 162 passed, 1 skipped.

## Phase 4: Usefulness Gate

**Files:**
- Modify `apps/api/llm_band/infrastructure/mir/deep_harmonic_analyzer.py`
- Modify `apps/api/llm_band/application/answer_music_question.py`
- Modify `apps/web/lib/referenceProfileView.mjs`
- Update matching tests

- [x] When key, chord, grid, and structure confidence are all low, emit a
  `low_usefulness` analysis note and lead the summary with the limitation before
  listing candidates. (`_is_low_usefulness`, threshold 0.5; summary inserts the
  limitation right after the objective duration/tempo facts.)
- [x] Q&A and the frontend summary respect the same gate. (Q&A general answer
  leads with the caveat; `isLowUsefulness` + `describeReferenceSummary` in the
  frontend.)
- [x] Test: an all-low-confidence profile leads with the limitation; a mixed
  profile still shows candidates. → backend 165 passed, frontend 17 passed.

## Phase 5: Decouple Tuning From Labeling

**Files:**
- Modify `apps/api/llm_band/infrastructure/mir/key_features.py`
- Modify `apps/api/llm_band/infrastructure/mir/chord_features.py`
- Update matching tests

- [x] Use estimated tuning for the chroma that is *scored* (key + chords); keep
  A=440 for the printed labels. (Both default chroma providers now pass
  `librosa.estimate_tuning(...)` to `chroma_cqt`; labels still come from the
  pitch-class index, which tuning does not change.)
- [x] Keep the existing `possible_detuning` note when deviation is significant.
- [x] Test: a deliberately detuned synthetic source still scores the correct key
  while the label stays A=440. (Plus chord provider applies estimated tuning.)

## Phase 6: Cleanups

**Files:**
- Modify `apps/api/llm_band/application/answer_music_question.py`
- Modify `apps/api/llm_band/infrastructure/mir/deep_harmonic_analyzer.py`
- Modify `apps/api/llm_band/infrastructure/mir/structure_features.py`

- [x] Route `"chorus"`/`"verse"` to the structure branch, not the chord branch.
  (Removed `"chorus"` from the chord regex in backend Q&A and frontend view.)
- [x] Document (and ideally collapse) the three structure heuristics
  (`detect_structure`, `_fallback_sections_if_degenerate`, `section_features`)
  into one clearly-ordered path. (Documented the three ordered tiers inline in the
  orchestrator; kept the paths since each is independently tested.)
- [x] Remove or clearly mark the unused buffered `analyze_with_progress`.
  (Removed the dead buffered method; real streaming is the API queue/thread, now
  noted on `analyze`.)

## Verification Before Completion

```bash
cd apps/api && PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest
cd apps/web && node --test lib/referenceProfileView.test.mjs
```

## Expand Known-Song Expectations (Ongoing)

Without storing commercial audio, grow `tests/test_known_song_expectations.py`
to assert behavior, not exact chords: does not claim high confidence for
ambiguous keys; produces more than one section when strong energy changes exist;
surfaces a weak loop candidate instead of isolated triads; leads with the
limitation when everything is low.
