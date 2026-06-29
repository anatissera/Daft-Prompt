# Product — Daft Prompt Scraping Analysis

Daft Prompt is a conversational music workspace.

In this experimental branch, the product researches known songs from public web
sources instead of analyzing uploaded audio. The goal is to test whether web
evidence can provide a cheaper, faster, and more deployable foundation for music
understanding and reference-guided composition.

## Product Goal

> A chat-first assistant that researches songs, explains musical traits with
> cited evidence, and composes new sketches from one or more reference profiles.

The product should feel like a small conversational studio, not a dashboard and
not a form-heavy generator.

## MVP Capabilities

### Conversational Chat

The user can write naturally:

- "Analyze Every Breath You Take."
- "What chords does Space Cowboy probably use?"
- "Compose something with the drums of one song and the harmony of another."
- "Make a slow blues from scratch."

The assistant routes the request to research, Q&A over existing references,
composition from scratch, or composition from reference traits.

### Song Research

The MVP researches songs by name. It searches candidate public pages, fetches
HTML, extracts compact musical claims, and fuses evidence into a `ReferenceProfile`.

Good claims include:

- tempo or BPM;
- likely key;
- probable chords or progressions;
- section/form hints;
- groove, mood, instrumentation, or style traits.

The app must cite sources and use probabilistic language. It should not store or
reproduce full tabs or lyrics.

### Music Explanation

Answers should distinguish evidence from interpretation:

- "Two sources point to roughly 117-118 BPM."
- "The key is probably A major, but one source frames it as F# minor."
- "The chords are a likely guide, not a verified transcription."

When sources disagree or block access, the app should say so.

### Composition

Composition from scratch remains first-class. Reference-guided composition uses
compact research profiles, not raw pages or copied tabs.

The default behavior is transformative:

- use tempo, energy, mood, instrumentation, groove, or form when useful;
- use harmonic guidance only as a probable guide;
- do not copy full tabs, lyrics, or melodies.

The user can combine references conversationally, such as "use the drum feel from
X and the harmony from Y."

### Playable Output

Generated songs are playable and exportable. The app never plays commercial
reference songs.

## Non-Goals

- local audio upload or audio analysis in this branch;
- YouTube download/conversion;
- commercial-song playback;
- full tab/lyrics storage;
- persistent accounts or database;
- full DAW or notation-first workflow.

## Architecture Rules

The backend follows clean architecture:

```text
Interface route
  -> application use case
  -> domain models
  -> ports
  -> infrastructure adapters
```

Composition agents consume compact `ReferenceProfile` summaries only.

## Testing

Standard checks:

```bash
cd apps/api
python -m pytest
```

```bash
cd apps/web
npm run typecheck
node --test lib/analysisProgress.test.mjs lib/chatActionAdapter.test.mjs lib/referenceProfileView.test.mjs lib/trackMixerLogic.test.mjs
```
