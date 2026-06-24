# Product — LLMinem

LLMinem is a conversational music workspace.

The product lets a user talk with an assistant that understands songs, analyzes
local audio files with music tools, and can compose new songs either from a text
prompt or from a previously analyzed reference.

The core experience is a chat. The user should not need to choose a rigid mode
before acting. They can ask a question, upload a local audio file, request a new
composition, or ask the system to compose using a reference. The system infers
the intent, uses the right tools, and asks a short follow-up only when the
request is ambiguous.

This document is the source of truth for product behavior and MVP scope.

## Problem

Musicians and music students often want to understand a song and quickly turn
that understanding into a new musical idea.

They may ask:

- What key is this in?
- What is the tempo?
- What chords does the chorus probably use?
- Why does this section feel bigger?
- Can you make something with this energy but not copy the song?
- Can you compose a disco/cumbia/blues track from scratch?

Most tools split these workflows apart: analysis tools expose technical data,
composition tools generate material, and chat assistants explain music without
grounding their answers in deterministic analysis. LLMinem should connect those
steps in one conversational flow.

## Product Goal

The MVP goal is:

> A chat-first assistant that analyzes local songs with tools and can compose new
> songs from scratch or from the analyzed musical profile.

The product should feel like a small conversational studio, not a dashboard and
not a form-heavy generator.

## Core User

The initial user is a music-curious technical user: a student, musician, producer,
or course evaluator who wants to see both musical reasoning and agentic
composition.

They value:

- quick local experimentation;
- visible evidence for musical claims;
- playable output;
- a clear explanation of what the agents did;
- low setup friction;
- few manual controls unless they are useful.

## MVP Capabilities

### 1. Conversational Chat

The chat is the primary interface.

The user can write naturally:

- "Analyze this audio."
- "What chords are probably in the chorus?"
- "Compose a slow blues from scratch."
- "Use the energy of this reference, but do not copy the chords."
- "Make it more like Argentine cumbia."

The assistant should route the request to the right use case:

- answer from existing context;
- analyze an attached local audio file;
- compose from a text prompt;
- compose from a previously analyzed `ReferenceProfile`;
- ask one short clarification if needed.

### 2. Local Audio Analysis

The MVP accepts local audio files only.

Out of scope for the MVP:

- YouTube search;
- YouTube download or conversion;
- commercial-song acquisition;
- external music catalog integrations;
- persistent reference libraries.

The analysis tools should extract:

- duration;
- estimated tempo;
- estimated key;
- energy curve or section-level energy;
- simple section boundaries;
- estimated chords by section or time range.

Chord analysis must be presented as an estimate, not a fact. The assistant should
use language such as:

> "Probably Am - F - C - G in this section."

When possible, the answer should include confidence language: high, medium, low,
or an equivalent score.

### 3. Music Explanation

The assistant explains songs using the analysis results as evidence.

Good answers should connect technical observations to musical interpretation:

- tempo and groove;
- key and harmonic color;
- chord motion;
- energy changes;
- section contrast;
- density, register, and rhythmic activity when available.

The assistant should avoid pretending to know more than the tools support. If an
estimate is uncertain, it should say so.

### 4. Composition From Scratch

The user can compose without analyzing a prior song.

Example:

> "Compose a dark cumbia villera loop of 16 bars."

This uses the existing multi-agent composition pipeline:

- director agent decides the arrangement;
- instrument agents compose parts;
- agents negotiate through shared structured state;
- the result is exported as structured JSON and playable audio/MIDI.

Composition from scratch is a first-class path, not a fallback.

### 5. Composition From Reference

After analyzing a local audio file, the user can ask the assistant to compose
using that reference.

The reference is passed to the composition system as a compact
`ReferenceProfile`, not as raw audio or provider-specific data.

The default transfer behavior should be intelligent and conservative:

- use tempo by default when confidence is reasonable;
- use section shape and energy curve by default;
- use general mood/style observations by default;
- use key when confidence is reasonable;
- do not copy estimated chords by default;
- use estimated chords only when the user asks for it or accepts it in chat.

The user should be able to override this conversationally:

- "Use only the tempo."
- "Keep the energy curve but change the harmony."
- "Use the same chords as a guide."
- "Ignore the reference and compose from scratch."

### 6. Playable Output

Generated songs should be playable in the UI.

The MVP should support:

- play/stop;
- a simple per-instrument mixer with mute/solo after a song exists;
- MIDI download or equivalent export.

The mixer is useful after generation, but it should not dominate the initial
chat experience.

### 7. Agent Transparency

The user should be able to understand what happened without reading raw logs.

The UI should expose, in a compact way:

- which tools were used for analysis;
- what the detected musical profile was;
- which agents participated in composition;
- important negotiation requests and resolutions;
- final composition status.

This should be available as contextual detail, not as the main interaction.

## Non-Goals

The MVP does not need:

- persistent user accounts;
- a database;
- long-term chat history;
- collaborative editing;
- production-grade audio mastering;
- perfect chord transcription;
- perfect stem separation;
- YouTube ingestion;
- a full DAW interface;
- notation as a primary experience.

Sheet music can remain optional or hidden behind a detail view. It should not be
the center of the product unless it becomes reliable and useful.

## Product Principles

### Chat First

The user should mostly type what they want. Buttons and toggles should be
minimal.

Useful controls:

- attach local audio;
- play/stop;
- mute/solo generated instruments;
- export MIDI;
- show/hide technical details.

Avoid permanent panels full of switches. When configuration is needed, prefer a
short conversational clarification.

### Evidence-Based Answers

Musical explanations should be grounded in tool outputs. The assistant can
interpret, but it should distinguish interpretation from measured or estimated
facts.

### Defaults Over Configuration

The system should choose sensible defaults and tell the user what it is doing.

Example:

> "I will use the reference tempo, structure, and energy curve. I will not copy
> the estimated chords unless you ask me to."

### Reference As Context, Not Copying

Using a reference should mean borrowing high-level musical traits, not copying a
song. The product should encourage transformation:

- similar energy;
- similar structure;
- similar tempo;
- similar mood;
- different melody and arrangement;
- optional harmonic guidance only when requested.

### Local-First MVP

The first working version should run well locally. It can lose chats, songs, and
artifacts when restarted. Persistence is not required for the MVP.

## Architecture Expectations

The repository should keep a clean separation of responsibilities:

- UI renders chat, context, playback, and compact details.
- API boundaries accept chat, upload, analysis, and composition requests.
- Application use cases orchestrate behavior.
- Domain models represent song state and reference profiles.
- Ports define LLM, audio analysis, transcription, storage, and composition
  dependencies.
- Infrastructure adapters implement local storage, MIR analysis, LLM providers,
  and future cloud/object storage.
- Composition agents consume `ReferenceProfile` summaries, never raw audio or
  provider internals.

The existing multi-agent composer remains valuable. The product direction does
not replace it; it wraps it in a broader conversational music workflow.

## Deployment Direction

The MVP does not require persisted memory or a database.

It is acceptable for generated songs, uploaded references, and chat state to be
lost when the process or container restarts.

The backend should be containerized before deployment because audio analysis,
music rendering, and Python music libraries are better suited to a container
host than to serverless frontend functions.

The likely deployment shape is:

- frontend on Vercel or another static/Next.js host;
- Python backend as a container on Render, Railway, Fly.io, Cloud Run, or a
  similar provider;
- local filesystem storage for MVP/local use;
- optional object storage later if deployed artifacts need stable URLs.

## MVP Success Criteria

The MVP is successful when a user can:

1. Open the app locally.
2. Chat naturally with the assistant.
3. Upload or select a local audio file.
4. Ask for tempo, key, sections, energy, and probable chords.
5. Receive an evidence-based answer with uncertainty where appropriate.
6. Ask for a new composition from scratch.
7. Ask for a new composition using the analyzed reference.
8. Hear the generated result.
9. Mute or solo generated instruments.
10. Understand, at a high level, which tools and agents were involved.

