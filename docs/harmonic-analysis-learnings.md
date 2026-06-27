# Harmonic Analysis MVP Learnings

This document records the decisions, tradeoffs, and open hypotheses after
finishing phases 8, 9, and 10 of `plans/deep-harmonic-analysis.md` and the
subsequent `Harmonic MVP V2 Hardening` pass.

It is intentionally candid. The current harmonic analyzer is useful as an
evidence-backed prototype, but it is not yet a reliable song analyst for real
commercial recordings.

## Context

LLMinem / Daft Prompt is a chat-first musical workspace. The analysis path should
help users understand local songs and optionally compose from the resulting
`ReferenceProfile`.

The current harmonic MVP deliberately stays narrow:

- local audio only;
- Demucs/librosa-based harmonic analysis;
- tempo and bar grid;
- key candidates;
- bar-aligned triad estimates;
- repeated chord progressions;
- abstract `A/B/C` structure;
- probabilistic copy and confidence values.

The current hard boundary remains:

- no YouTube ingestion;
- no database;
- no external music metadata/chord APIs;
- no Basic Pitch transcription;
- no Essentia/HPCP production path;
- no semantic `verse`/`chorus` labels yet.

## What Landed After Phases 8-10

### Phase 8: Analysis Progress Streaming

The backend now supports progress-style analysis events around the deep harmonic
pipeline. The event stages mirror the real pipeline:

1. accepted;
2. separating stems;
3. building harmonic source;
4. estimating tempo and grid;
5. estimating key;
6. estimating chords;
7. detecting structure;
8. done/error.

Decision: keep streaming as an interface concern. The analyzer exposes progress
callbacks; FastAPI is responsible for turning those into HTTP/SSE behavior.

Why: this keeps clean architecture intact. The analyzer should not know about
HTTP, streaming response formats, or frontend timing.

### Phase 9: Frontend Rendering

The frontend moved from generic audio facts toward harmonic evidence:

- key candidates with calibrated confidence;
- repeated progression display;
- A/B/C timeline;
- probable triads;
- analysis notes;
- legacy energy hidden unless useful.

Decision: render `harmony` and `structure` first, with legacy fields only as
compatibility fallback.

Why: the new domain contract is more honest and more useful than flat fields like
`key`, `chord_estimates`, and `sections`. Keeping compatibility fields prevents
old tests and API consumers from breaking while the UI migrates.

### Phase 10: Evidence-Grounded Music Q&A

The deterministic Q&A path now answers from `ReferenceProfile` evidence:

- key questions use `KeyProfile`;
- chord questions use `ProgressionEstimate` first, then `ChordSpan`;
- structure questions use `StructureProfile`;
- answers include bars and confidence;
- low-confidence answers use cautious language.

Decision: keep this deterministic for now instead of asking an LLM to interpret
raw analysis.

Why: the output is easier to test, does not hallucinate unsupported claims, and
is aligned with the product rule that analysis confidence must not disappear
before explanation.

## Hardening Decisions After Real-Song Testing

Real-song testing, especially with "Every Breath You Take", showed that the
system can detect duration and tempo reasonably, but key, chords, and structure
can still be musically unhelpful:

```text
Key: Ab major · low · 44%, with nearby alternatives.
Structure: A bars 1-117 · low · 25%.
```

That result is technically honest but not useful enough.

### A=440 Labels

Decision: key and chord labels now assume A=440 by default.

Implementation direction:

- `key_features.py` and `chord_features.py` call `chroma_cqt` with
  `tuning=0.0`;
- tuning estimation is allowed only as a diagnostic note;
- if detuning is significant, the analyzer adds:

```text
Labels assume A=440; recording may be slightly detuned.
```

Why: silently retuning chroma before labeling can make labels harder to reason
about and harder to compare with user expectations. If a recording is detuned,
the user should see that as uncertainty, not as invisible relabeling.

### Honest Summary Copy

Decision: summaries should not say "likely key X" when confidence is low or
relative-key ambiguity is present.

Current behavior:

- low/ambiguous key: "Tonal center is ambiguous; close candidates include ...";
- weak progression: "Weak chord loop candidate ...";
- weak structure: "Structure is approximate/unclear.";
- notes remain visible when bar grid, stems, or section evidence are weak.

Why: the original copy sounded more certain than the evidence justified. This
made bad analyses feel wrong instead of uncertain.

### Repeated Progression Candidate

Decision: expose a repeated chord loop candidate even when exact A/B/C structure
is weak.

Implementation direction:

- `structure_features.py` now has a fuzzy repeated-progression helper;
- it tolerates unknown bars (`?`);
- it tolerates some low-confidence bars;
- it does not invent chords absent from observed spans;
- Q&A uses this candidate before listing isolated triads.

Why: a user asking "what chords repeat?" benefits more from a cautious loop
candidate than from eight isolated bar-level guesses.

### Approximate Section Boundaries

Decision: add an incremental `section_features.py` helper for approximate
sections using bar-aligned novelty signals.

Inputs:

- chord-window novelty;
- optional mix energy by bar;
- optional stem activity by bar.

Rules:

- labels remain abstract `A/B/C`;
- no `verse`/`chorus` inference;
- minimum section size is 8 bars;
- boundaries prefer multiples of 8 or 16;
- if evidence is weak, return a single low-confidence `A` section.

Why: exact chord repetition alone collapses many pop/rock songs into one giant
section. Arrangement and energy changes often define useful sections even when
the harmonic loop stays the same.

## Why It Still Does Not Work Well Enough

These are hypotheses, not settled conclusions.

### 1. Chroma Triads Are Too Weak For Dense Mixes

The current chord estimator scores triad templates against chroma. This is
fragile when:

- vocals dominate the harmonic source;
- guitars use partial voicings or suspended/add tones;
- bass implies a root that the upper harmony does not strongly include;
- production noise and reverb smear pitch classes;
- sections use pedal tones or riffs instead of block chords.

Possible improvement: add bass-informed root estimation before choosing triads.
Even a simple bass chroma/root vote could improve labels more than another round
of template tuning.

### 2. Key Detection Confuses Modal Mixture And Relative Keys

The current key detector is honest about ambiguity, but it still tries to return
a single primary key candidate. Real songs often hover between relative major
and minor, use modal color, or emphasize non-tonic hooks.

Possible improvement: represent "tonal center candidates" separately from
classical key labels. For example:

```text
Tonal center candidates: Ab / F / C#.
Mode confidence: unclear.
```

This may be more useful than forcing `Ab major` vs `F minor`.

### 3. Bar Grid Errors Cascade Into Chords And Structure

Chords and sections are bar-aligned. If downbeats drift or the first bar is
offset, every downstream result can look coherent but be shifted.

Possible improvement: add a downbeat/phase sanity check that evaluates multiple
bar offsets and picks the one with the most stable chord and energy boundaries.
This still stays within librosa-style features and does not require a new engine.

### 4. Structure Needs Arrangement Evidence, Not Just Harmony

The V2 section helper introduces energy/stem activity inputs, but the default
analyzer does not yet compute rich per-bar energy/activity from stems. Without
those signals, it mostly falls back to chord novelty.

Possible improvement: add cheap per-bar RMS/activity summaries for mix and
available stems, then feed them into `section_features.py`. This is still not
the broader `deep-music-analysis.md` plan; it is a small hardening step using
signals already available in the current pipeline.

### 5. Confidence Is Calibrated Locally, Not Musically Validated

Confidence values currently come from heuristic separation between candidates,
bar-grid confidence, and fallback penalties. They are useful for UI honesty but
not statistically calibrated against real songs.

Possible improvement: build a small metadata expectation suite with safe,
non-commercial fixtures or synthetic approximations. Do not assert exact
commercial-song chords; assert broad behavior like:

- does not claim high confidence for ambiguous keys;
- produces more than one section when strong energy changes exist;
- surfaces a weak loop candidate instead of isolated triads.

### 6. The Product May Need To Say "I Cannot Tell"

Some songs are simply poor targets for this MVP-level analyzer. The product
should sometimes lead with:

```text
I can estimate tempo and broad harmonic color, but the chord and structure
evidence is weak in this recording.
```

Possible improvement: add a high-level usefulness gate. If key, chord, grid, and
structure confidence are all low, the summary should emphasize limitations
before showing candidate details.

## Recommended Next Steps Before Deep Music Analysis

1. Add per-bar mix/stem RMS activity and pass it into `section_features.py`.
2. Add bar-phase/downbeat offset evaluation before chord/structure extraction.
3. Add bass-informed root weighting to chord choice.
4. Add a usefulness gate for low-confidence analyses.
5. Expand known-song expectation tests without storing commercial audio.
6. Only then revisit `plans/deep-music-analysis.md`.

## Current Position

The harmonic MVP is architecturally useful:

- clean boundary behind `AudioAnalyzer`;
- compact `ReferenceProfile`;
- testable pure helpers;
- chat/UI surfaces that preserve confidence;
- no new database or external ingestion.

But musically, it should be treated as an honest draft listener, not a reliable
transcriber. The next useful work is not adding a larger model immediately. It is
improving the current evidence pipeline so that when it is uncertain, it fails in
a way that is informative rather than misleading.
