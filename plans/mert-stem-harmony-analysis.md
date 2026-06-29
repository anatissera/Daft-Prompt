# MERT And Stem-Harmony Analysis Plan

> **Status in `feat/scraping-analysis`: paused.** This plan belongs to the
> heavier local-audio analysis direction. The active experiment in this branch is
> research-only song analysis from public web evidence.

## Goal

Improve local song understanding by delaying musical decisions until after the
system has collected evidence per stem.

The current analyzer already has a strong first step: it accepts local audio,
separates stems, estimates a tempo/bar grid, and builds harmonic and section
profiles. The weak part is the interpretation layer. Chords, key, and structure
are often inferred from compressed signals too early, which makes the assistant
either overstate weak evidence or collapse to "everything is A".

This plan moves the analyzer toward a music-teacher workflow:

```text
separate stems
  -> collect evidence per stem
  -> fuse harmonic evidence late
  -> detect section changes from harmonic, arrangement, and MERT evidence
  -> explain conclusions with uncertainty and sources
```

The output should still be a compact `ReferenceProfile`. Rich model internals,
per-stem evidence, and decision traces belong in audit artifacts.

## Product Direction

The user-facing experience remains chat-first. The user should be able to upload
a local audio file and ask:

- "What key is this probably in?"
- "What chords does this section probably use?"
- "Where does the section change?"
- "Why does this part feel bigger?"

Answers must stay probabilistic. When evidence is weak or conflicting, the app
should say that clearly and cite the relevant evidence instead of forcing a
single confident result.

This work does not turn LLMinem into a full DAW, notation editor, or perfect
transcription tool. The near-term goal is better musical understanding and
better explanations, not professional-grade score extraction.

## Runtime Assumptions

This future implementation assumes a heavier local analysis runtime:

- MERT is a required dependency for deep section analysis.
- Stem transcription is a required dependency for harmonic fusion.
- The target runtime is a local machine with GPU support.
- Missing model files, unavailable GPU resources, or model load failures should
  fail loudly with clear analysis errors rather than silently falling back to
  weaker behavior.

The exact model packages and installation details should be selected during
implementation, but the design should treat them as first-class backend analysis
dependencies rather than optional UI features.

## Architecture

Keep clean architecture boundaries:

- Domain models stay compact and stable.
- Application use cases orchestrate analysis and explanation.
- MIR/model code lives under infrastructure adapters.
- Composition agents only consume compact reference summaries.

The main architectural change is to add an internal evidence layer between stem
separation and the final `HarmonicProfile` / `StructureProfile`.

```text
DeepHarmonicAnalyzer
  -> stem separation
  -> tempo/bar grid
  -> per-stem evidence extraction
  -> harmonic evidence fusion
  -> MERT section evidence
  -> structure detection
  -> ReferenceProfile + audit files
```

## Stem Evidence Model

Introduce an internal evidence representation aligned to the bar grid. This
model is not intended to be exposed directly in `ReferenceProfile`.

### Bass Evidence

Use the bass stem for root and low-register pitch evidence:

- detected notes or pitch classes per bar;
- likely bass root per bar;
- confidence for each root;
- ambiguity markers when multiple roots compete.

The bass should strongly influence chord roots, but it should not force a chord
when the accompaniment contradicts it.

### Other Evidence

Use the `other` stem as the main harmonic accompaniment source:

- bar-level chroma;
- note or pitch-class evidence when transcription is available;
- chord candidates per bar;
- confidence and candidate separation.

The `other` stem should strongly influence chord quality: major, minor,
diminished, unknown.

### Harmonic Evidence

Fuse bass and other evidence into bar-level harmonic hypotheses:

- likely chord candidates;
- chosen chord only when evidence clears confidence thresholds;
- key candidates;
- repeated progression candidates;
- explicit conflict notes when bass and other disagree.

### Drums And Vocals

Drums and vocals should not drive chord or key decisions by default.

Use them for:

- section boundaries;
- arrangement density;
- groove/rhythmic change;
- vocal presence or absence;
- explanation of why a section feels bigger, thinner, or different.

Vocals may support global key or melodic color later, but should not contaminate
bar-level chord detection in the first implementation.

## Harmonic Fusion

Replace the current early-mixing harmonic decision with late fusion.

Current shape:

```text
bass + other harmonic source
  -> chroma
  -> chord spans
  -> key context
```

Target shape:

```text
bass stem
  -> root evidence

other stem
  -> chord candidates / chroma / note evidence

key candidates
  -> diatonic context, never hard forcing

fusion
  -> fused ChordSpan sequence
  -> progression candidates
```

The fusion layer should:

- boost chords whose root matches confident bass evidence;
- prefer chord qualities supported by `other`;
- reduce confidence when bass and `other` disagree;
- preserve multiple candidates in ambiguous bars;
- avoid choosing a chord for flat, smeared, or low-evidence bars;
- keep all chord language probabilistic.

Progression detection should run over fused `ChordSpan` values. If the fused
progression becomes reliable, structure detection can use harmonic changes as
stronger section evidence.

## MERT Section Analysis

Use MERT as a learned musical-similarity signal for section detection.

MERT should not replace interpretable stem features. It should add a second
opinion:

```text
manual stem evidence says "several medium changes"
MERT says "the musical texture changed strongly"
  -> stronger boundary candidate
```

Compute MERT embeddings over bar-aligned windows:

- 4-bar windows for local novelty;
- 8-bar windows for phrase-level similarity;
- mix or harmonic audio for global texture;
- optionally stems when runtime cost is acceptable.

Use these embeddings for:

- boundary novelty around candidate bars;
- grouping similar sections as A/B/A;
- audit evidence for accepted and rejected section cuts.

The audit should record values such as:

```json
{
  "bar": 41,
  "mert_novelty": 0.61,
  "mert_window": "8_bars",
  "manual_modality_scores": {
    "vocals": 0.465,
    "drums": 0.418,
    "other": 0.386,
    "bass": 0.128
  },
  "decision_reason": "mert_and_multistem_arrangement_change"
}
```

## Audit Artifacts

Keep `ReferenceProfile` compact. Add richer details to audit files.

Expected audit data:

- bar grid metadata;
- key candidates and ambiguity;
- fused chord candidates per bar;
- bass root evidence;
- other harmonic evidence;
- progression candidates;
- section boundary candidates;
- MERT novelty and similarity;
- accepted/rejected decisions with reasons;
- top feature changes by stem when available.

The audit should support explanations such as:

> "A section change is likely near bar 41. The harmonic evidence is weak, but
> MERT novelty is high and vocals, drums, and accompaniment all change together."

or:

> "The chord is probably F. The bass supports F as root and the accompaniment
> contains strong A/C evidence, but confidence is medium because the bar is
> smeared across neighboring harmony."

## Explanation Behavior

Music Q&A should use fused evidence instead of raw detector output.

Good answers:

- cite tempo, key, chords, sections, and confidence;
- explain whether a section change is harmonic, arrangement-based, or both;
- name evidence sources: bass root, accompaniment chroma, MERT novelty, vocal
  activity, drum pattern change;
- say when no reliable progression was found.

Bad answers:

- "The song is in X" when candidates are close;
- "The chorus chords are X" when no section/chord evidence supports that;
- raw JSON dumps as the primary explanation;
- treating vocals/drums as chord evidence by default.

## Implementation Phases

### Phase 1: Plan And Runtime Contract

- Add this plan to `/plans`.
- Decide exact model packages and GPU requirements before implementation.
- Document model setup and failure behavior.

### Phase 2: Per-Stem Harmonic Evidence

- Build internal evidence types for bar-aligned bass and other stem analysis.
- Implement bass root extraction from transcription and/or chroma.
- Implement other-stem chord candidate extraction.
- Write pure unit tests with synthetic pitch-class evidence.

### Phase 3: Harmonic Fusion

- Add a fusion module that produces fused `ChordSpan` values.
- Feed fused spans into existing progression and structure helpers.
- Add audit output for agreement, disagreement, and confidence changes.

### Phase 4: MERT Section Evidence

- Add MERT embedding extraction over bar-aligned windows.
- Add MERT novelty and similarity to section audit candidates.
- Use MERT evidence in boundary acceptance and section label grouping.

### Phase 5: Explanation And UI Surfacing

- Update deterministic music answers to cite fused evidence.
- Keep UI compact: show summary first, technical evidence behind details.
- Do not expose raw vectors in the primary chat surface.

## Tests And Acceptance Criteria

### Unit Tests

- Bass root extraction returns a confident root when one pitch class dominates.
- Bass root extraction returns ambiguous when multiple roots compete.
- Other-stem chord scoring produces major/minor/diminished candidates from
  synthetic chroma.
- Fusion boosts agreement between bass root and other chord candidates.
- Fusion lowers confidence when bass and other conflict.
- Fused low-confidence bars remain unknown instead of forcing chords.

### Integration Tests With Fakes

- Fake transcription evidence produces a repeated progression.
- Fake MERT embeddings produce a section boundary at the expected bar.
- Fake MERT similarity groups repeated sections as A/B/A.
- Model-unavailable errors are surfaced clearly.

### Regression Tests

- Existing chat-first analysis responses keep probabilistic language.
- `ReferenceProfile` remains compact and does not expose raw embeddings.
- Composition agents do not receive raw audio, raw MERT vectors, or provider
  details.
- Section audit includes enough evidence to explain accepted and rejected
  boundaries.

### Demo Acceptance

On a local song with separated stems, the analyzer should be able to produce one
of these honest outcomes:

- a likely key/progression with bass and accompaniment evidence;
- a section boundary explanation supported by MERT and stem changes;
- or a clear low-confidence result explaining which evidence was ambiguous.

## Risks

- MERT and transcription dependencies may make setup significantly heavier.
- GPU runtime can be hard to make portable.
- Stem separation artifacts can mislead downstream transcription.
- More evidence can create false confidence unless disagreement is surfaced.
- Perfect chord transcription is still out of scope.

Mitigation: keep confidence calibrated, preserve audit evidence, and prefer
unknown/ambiguous output over forced certainty.
