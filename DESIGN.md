# Design — Daft Prompt Scraping Analysis

Daft Prompt is a conversational music workspace. In this branch, the interface
is centered on researching songs by name and composing from researched traits.

## Interaction Model

Chat is the primary surface. The user can write:

- "Analyze Every Breath You Take."
- "What is the likely key of Space Cowboy?"
- "Compose with the groove of X and the harmony of Y."
- "Make a cumbia from scratch."

The app should infer intent from the conversation and current references.

## Main States

### Start

Show one chat input and a few example prompts. Do not show upload controls.

### Research In Progress

Show compact progress:

- searching sources;
- fetching pages;
- extracting claims;
- fusing evidence.

### Research Result

Show a readable summary:

- likely tempo;
- likely key;
- probable chords/progressions when available;
- source evidence and confidence;
- warnings when sources conflict.

### Composition

Generated songs should show:

- a short assistant summary;
- play/stop;
- per-instrument mute/solo;
- MIDI export;
- compact agent/tool details.

## Visual Direction

The UI should remain modern, focused, and musical without becoming a dashboard.
Evidence and sources should be compact details, not raw HTML or JSON.

## Content Tone

Good:

- "Sources suggest roughly 117-118 BPM."
- "The harmony is probably A - E - F#m - D, but confidence is medium."
- "I will use the groove and energy, not copy the song."

Avoid:

- claiming scraped chords are certain;
- reproducing full tabs or lyrics;
- making the user choose a rigid mode before typing.
