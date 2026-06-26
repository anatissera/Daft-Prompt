# Architecture Notes

This document preserves technical decisions that remain valid after the product
direction moved from "multi-agent band demo" to "chat-first musical workspace".

`PRODUCT.md` is the product source of truth. This document is technical support.

## Core Boundaries

The backend follows clean architecture boundaries:

- `domain/`: stable music and reference models.
- `application/`: use cases such as composition, reference analysis, and music Q&A.
- `ports/`: interfaces for LLMs, storage, MIR analysis, transcription, and stems.
- `infrastructure/`: adapters for providers, storage, MIR libraries, and deployment.
- `interfaces/`: FastAPI HTTP/SSE boundary.

Composition code should not import MIR/audio adapters directly. It receives only
compact domain summaries, especially `ReferenceProfile`.

## Canonical Music Representation

`SongState` is the canonical representation for generated songs.

Important rules:

- pitches are MIDI note numbers;
- `null` pitch represents a rest;
- durations are in beats;
- notes use absolute `bar` plus `start_beat`;
- `header` is immutable after the director sets it;
- `parts` are keyed by roster id;
- `notes_summary` is the compact peer context used by instrument agents;
- `negotiation_requests` are the observable inter-agent protocol.

The LLM should emit structured data that maps to this schema. MIDI, MusicXML, and
notation are exports, not the source of truth.

## Composition Engine

The current composition engine remains valuable:

1. A director chooses key, tempo, meter, form, and instrumentation.
2. Instrument agents compose parts into `SongState.parts`.
3. Agents negotiate through `negotiation_requests` in shared state.
4. An arbiter resolves any remaining requests at the round cap.
5. Deterministic renderers convert `SongState` to MIDI and MusicXML.

LangGraph does not provide direct peer-to-peer calls. Agent communication is
modeled as structured requests written to shared state and routed on later turns.

## Reference Analysis

Reference analysis is a separate bounded context.

For the MVP it accepts local files only. The target profile includes:

- duration;
- tempo estimate;
- key estimate;
- energy or section-level energy;
- simple section boundaries;
- chord estimates by section or time range;
- confidence values where possible.

Chord, key, beat, and section estimates are probabilistic. The assistant should
explain uncertainty instead of presenting estimates as ground truth.

## Reference-Guided Composition

Composition from reference should pass only a compact `ReferenceProfile` summary
into the composer.

Default transfer behavior:

- use tempo when confidence is reasonable;
- use structure and energy by default;
- use key when confidence is reasonable;
- do not copy chord estimates by default;
- use chord estimates only when the user asks for them or accepts them.

This keeps the product transformative and avoids coupling composer agents to raw
audio files or MIR internals.

## Frontend / Backend Split

The frontend is Next.js. The backend is FastAPI/Python.

The Python backend should be containerized because the project depends on music
and audio libraries that are better suited to a container than to serverless
frontend functions.

Likely deployment shape:

- Next.js frontend on Vercel or another web host;
- FastAPI backend on a container host such as Render, Railway, Fly.io, or Cloud
  Run;
- local filesystem storage for MVP;
- optional object storage later for durable deployed artifacts.

## Gotchas

- Keep TypeScript types in sync with Pydantic models.
- Validate note timing carefully; beat/bar math is a common failure source.
- Drums use GM percussion semantics and should not be validated like pitched
  instruments.
- Keep round caps and recursion limits on negotiation.
- Keep peer context compact to avoid token blowup.
- Do not make notation a hard dependency for playback.
- Do not let analysis confidence disappear before explanation.
- Do not add YouTube ingestion to the MVP.

## Verification Expectations

The repo should continue to support:

- backend unit tests for validators, converters, agents, negotiation, provider
  routing, and reference boundaries;
- frontend type checking;
- focused tests for mixer/playback logic;
- local end-to-end smoke testing once chat analysis and composition are connected;
- Docker build verification once containerization is added.

