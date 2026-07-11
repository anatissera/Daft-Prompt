# Architecture Notes

This document preserves technical decisions for Daft Prompt, a chat-first music
assistant that answers from public evidence and composes or edits MIDI-first
songs through a multi-agent band.

`PRODUCT.md` is the product source of truth. This document is technical support.

## Core Boundaries

The backend follows clean architecture boundaries:

- `domain/`: stable music, evidence, style, playable, tone, brief, and song
  models.
- `application/`: use cases such as chat routing, song knowledge lookup, artist
  style profiling, playable rendering, composition, and edits.
- `ports/`: interfaces for LLMs, source connectors, storage, rendering, and
  other dependencies.
- `infrastructure/`: adapters for providers, scraping, web search, storage,
  rendering, and deployment.
- `interfaces/`: FastAPI HTTP/SSE boundary.

Preferred flow:

```text
FastAPI route
  -> application use case
  -> domain models
  -> ports
  -> infrastructure adapters
```

Routes stay thin: parse/validate input, call use cases, and return models or
streams. Business rules do not belong in route handlers.

## Song Knowledge

Known-song understanding is connector-based. User-uploaded file analysis and
local audio analysis are not supported Daft Prompt product paths.

The song knowledge bounded context should expose compact provider-agnostic
domain models:

- `SongKnowledgeProfile`: evidence-backed facts and claims about a known song,
  artist, album, or genre.
- `EvidenceClaim`: one attributed source claim with confidence, conflicts, and
  optional section/time context.
- `PlayablePart`: a requested part represented as guitar tab, bass tab, drum
  tab, piano keys, piano roll, chord chart, or rhythm grid.
- `ArtistStyleProfile`: aggregated traits from representative songs and style
  evidence.
- `ToneProfile`: compact tone, patch, amp, pedal, synth, and production traits.
- `CompositionBrief`: instructions for the composer derived from chat plus
  optional song/style evidence.

Infrastructure adapters may scrape Songsterr, tab/chord pages, metadata pages,
or style/corpus sources. Raw HTML, source-specific response shapes, and
provider clients must not leak into `domain/`, `application/`, `agents/`, or
`music/`.

Songsterr/tab evidence is expected to be an important connector, but the domain
model must remain source-agnostic.

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

The LLM should emit structured data that maps to this schema. MIDI, audio,
MusicXML, tabs, piano keys, and piano roll views are exports or projections, not
the source of truth for generated compositions.

## Composition Engine

The multi-agent composer remains valuable and should stay isolated from source
connector details.

Composition flow:

```text
chat request + context
  -> CompositionBrief
  -> director/orchestrator
  -> dynamic instrument or role agents
  -> negotiation through shared SongState
  -> arbiter/reviewer
  -> render artifacts and playable views
```

Agent communication happens through structured `negotiation_requests` in shared
state. Do not add a separate message bus without a strong reason.

Composition agents may consume compact `SongKnowledgeProfile`,
`ArtistStyleProfile`, `PlayablePart`, `ToneProfile`, and `CompositionBrief`
summaries. They must not call scrapers, storage adapters, web search, raw
provider APIs, or legacy audio analyzers directly.

For evidence-guided composition, default behavior is transformative:

- use requested traits explicitly;
- preserve exact parts only when the user asks;
- do not copy complete source songs by default;
- keep source attribution visible in the response and details.

## Artist Style Profiling

Artist/band style profiling is an application use case.

It should:

- resolve the artist or band;
- select representative songs using popularity, tab availability, user mentions,
  and musical relevance;
- fetch evidence through source connector ports;
- aggregate genre, harmony, rhythm, instrumentation, form, tone, and production
  traits;
- preserve sources and confidence;
- cache the compact profile in chat context.

For prompts like "compose something similar to this band", the resulting
`ArtistStyleProfile` feeds `CompositionBrief`. Raw pages and full tabs do not.

## Chat Router

The chat router should classify requests into tool paths:

- identify song/entity;
- fetch or refresh song evidence;
- build or reuse artist/band style profile;
- answer music theory or production question;
- render a requested playable part;
- compose from scratch;
- compose from song, artist, album, or genre evidence;
- edit an existing generated `SongState`;
- ask one clarification when required.

The router preserves conversational context:

- current song knowledge profile;
- current artist/band style profile;
- current generated song;
- selected instrument or section;
- accepted constraints;
- evidence already gathered.

LangGraph can orchestrate routing, but deterministic fallback behavior should
exist for obvious prompts and tests.

## Frontend / Backend Split

The frontend is Next.js. The backend is FastAPI/Python.

Frontend responsibilities:

- render chat, contextual evidence, playable views, mixer, piano roll, and
  agent details;
- manage local UI state;
- call API routes.

Frontend code should not decide musical analysis, source fusion, chat routing,
composition policy, or edit semantics.

Backend responsibilities:

- route chat intent in `application/`;
- fetch and fuse evidence through ports;
- create style profiles and composition briefs;
- run the composer and edit use cases;
- render artifacts through deterministic helpers.

## Architecture Graphs Must Stay In Sync

The UI ships hand-maintained architecture/pipeline diagrams in
`apps/web/components/PipelineGraphs.tsx`, opened from sidebar controls when
present.

If you change anything those diagrams describe, update them in the same change.
This includes:

- adding, removing, or renaming pipeline nodes, tools, or fallback tiers;
- changing which models or providers each role uses;
- changing structured output schemas;
- changing the SSE streaming path or parallelism;
- changing what a node fundamentally is.

Stale diagrams are worse than no diagrams because they are part of the product
and onboarding.

## Deployment Direction

The MVP does not require persisted memory or a database.

Generated songs, gathered evidence, profiles, and chat state may disappear when
the process or container restarts.

Likely deployment shape:

- Next.js frontend on Vercel or another web host;
- FastAPI backend on a container host such as Render, Railway, Fly.io, or Cloud
  Run;
- local filesystem storage for MVP;
- optional object storage later for durable deployed artifacts.

## Gotchas

- Keep TypeScript types in sync with Pydantic models.
- Keep source attribution and confidence attached to claims.
- Do not let raw scraped HTML leak past infrastructure adapters.
- Validate note timing carefully; beat/bar math is a common failure source.
- Drums use GM percussion semantics and should not be validated like pitched
  instruments.
- Keep round caps and recursion limits on negotiation.
- Keep peer context compact to avoid token blowup.
- Do not make notation a hard dependency for playback.
- Do not reintroduce upload-first or local-audio analysis as a supported
  product path.
- Do not add YouTube download or conversion.

## Verification Expectations

The repo should continue to support:

- backend unit tests for domain contracts, connectors, profile aggregation,
  chat routing, validators, converters, agents, negotiation, provider routing,
  and composition/edit behavior;
- frontend type checking;
- focused tests for mixer/playback logic and pure UI adapters;
- local end-to-end smoke testing once chat, evidence, and composition are
  connected;
- Docker build verification for deployable runtime changes.
