# AGENTS.md

This repository contains Daft Prompt, a chat-first AI music assistant for
evidence-backed song understanding, playable teaching views, and multi-agent
MIDI composition/editing.

The application should stay focused. The goal is not to demonstrate every
possible agent pattern or music library; the goal is to deliver a clean,
production-minded MVP that feels coherent and works locally.

Before implementing any change, read:

1. `PRODUCT.md`
2. `DESIGN.md`
3. `docs/architecture.md`
4. `plans/daft-prompt-convergence.md` when working on the current Daft Prompt
   convergence
5. `plans/chat-musical-mvp.md` only as historical context for the superseded
   local-audio MVP

`PRODUCT.md` is the product source of truth. `DESIGN.md` defines UX direction.
`docs/architecture.md` preserves technical boundaries. The convergence plan is
the active roadmap.

## Repository

Daft Prompt is a monorepo with a Python backend and a Next.js frontend.

```text
apps/
  api/                    # FastAPI, LangGraph, music/source processing
    music_assistant/
      domain/             # SongState, song knowledge, style, playable, brief models
      application/        # chat, evidence, composition, style, render, edit use cases
      ports/              # LLM, source connector, storage, render, composer ports
      infrastructure/     # provider, scraping, research, storage, deployment adapters
      interfaces/         # FastAPI HTTP/SSE boundary
      agents/             # director, instrument, arbiter agents
      music/              # validation and symbolic rendering helpers
  web/                    # Next.js App Router UI
    app/
    components/
    lib/
docs/
plans/
PRODUCT.md
DESIGN.md
AGENTS.md
README.md
```

The application uses:

- FastAPI
- Pydantic
- LangGraph
- music21
- pretty_midi
- Next.js
- React
- TypeScript
- Docker

Some legacy audio-analysis modules still exist during migration. They are not a
supported Daft Prompt product path.

## Before Implementing Anything

Always follow this process:

1. Read `PRODUCT.md`.
2. Read `DESIGN.md`.
3. Read `docs/architecture.md` if touching backend boundaries.
4. Read `plans/daft-prompt-convergence.md` for current convergence work.
5. Inspect the existing implementation.
6. Identify existing patterns.
7. Extend existing patterns whenever possible.
8. Only then implement changes.

Do not introduce new patterns without a clear reason.

## Product Rules

The MVP is chat-first.

The user should mostly type what they want:

- ask a question about a known song, artist, album, or genre;
- ask how to play a part on guitar, bass, drums, or piano;
- request tabs, keys, rolls, rhythm grids, or chord charts;
- compose from scratch;
- compose from song, artist, album, genre, or style evidence;
- edit a generated song.

Avoid turning the product into:

- a dashboard-first app;
- a form-heavy generator;
- a full DAW;
- a notation-first product;
- a file-upload analyzer;
- a YouTube download or conversion tool.

Song knowledge must come from evidence connectors such as Songsterr, tab/chord
pages, metadata pages, artist/album information, and style/corpus references.
Do not make local audio analysis or user-uploaded file analysis a supported
product path.

Keep source attribution and uncertainty visible. Use language like:

> "Songsterr shows this guitar part, while the chord page simplifies the chorus
> differently."

Do not present scraped claims, estimated chords, keys, beats, sections, or tone
details as certain when sources cannot support that certainty.

## Architecture Rules

The backend follows clean architecture.

Preferred backend flow:

```text
Interface route
  -> application use case
  -> domain models
  -> ports
  -> infrastructure adapters
```

FastAPI routes are thin.

Responsibilities:

- parse/validate request data;
- call application use cases;
- return response models or streams.

Business rules do not belong in route handlers.

Application use cases orchestrate behavior.

Examples:

- route a chat message to evidence lookup, explanation, playable rendering,
  composition, or edit;
- build a `SongKnowledgeProfile`;
- build an `ArtistStyleProfile`;
- create a `CompositionBrief`;
- compose or edit a generated `SongState`.

Domain models represent stable concepts.

Examples:

- `SongState`;
- `SongKnowledgeProfile`;
- `ArtistStyleProfile`;
- `EvidenceClaim`;
- `PlayablePart`;
- `ToneProfile`;
- `CompositionBrief`;
- negotiation requests.

Ports define dependencies.

Examples:

- LLM provider;
- source connectors;
- web search;
- page fetcher;
- artifact storage;
- playable renderers.

Infrastructure adapters implement ports. They should not leak provider,
scraper, or library details into `application/`, `domain/`, `agents/`, or
`music/`.

## Composition Rules

The multi-agent composer is valuable and should remain isolated.

Composition flow:

```text
CompositionBrief
  -> director/orchestrator
  -> dynamic instrument or role agents
  -> negotiation through shared SongState
  -> arbiter/reviewer
  -> render artifacts
```

Agent communication happens through structured `negotiation_requests` in shared
state. Do not add a separate message bus unless there is a strong reason.

Composition agents may consume compact `SongKnowledgeProfile`,
`ArtistStyleProfile`, `PlayablePart`, `ToneProfile`, and `CompositionBrief`
summaries. They must not call source connectors, storage adapters, web search,
legacy audio analyzers, or raw provider APIs directly.

Do not copy source songs by default. Preserve exact parts only when the user
explicitly asks for preservation.

## Architecture Graphs Must Stay In Sync

The UI ships hand-maintained architecture diagrams in
`apps/web/components/PipelineGraphs.tsx` when present.

If you change anything those diagrams describe, update them in the same change.
This includes:

- adding, removing, or renaming pipeline nodes, tools, or fallback tiers;
- changing which models or providers each role uses;
- changing structured output schemas;
- changing the streaming path or parallelism;
- changing what a node fundamentally is.

Stale diagrams are worse than no diagrams because they are part of the product
and onboarding.

## UI Rules

The UI should be conversational first.

Components and pages are responsible for:

- rendering;
- user interaction;
- local UI state;
- calling API routes.

UI should not contain business logic for musical evidence fusion, chat routing,
composition decisions, or edit semantics.

Prefer:

- one main chat surface;
- contextual evidence details;
- contextual playable tabs/keys/rolls;
- contextual generated-song playback;
- compact tool/agent details;
- playback and mute/solo only after a song exists.

Avoid:

- upload-first analysis affordances;
- permanent panels full of toggles;
- forcing a mode selection before the user can type;
- raw JSON as the primary UI;
- sheet music as the default focus;
- decorative complexity that hides the workflow.

## TypeScript

Use TypeScript explicitly in the frontend.

Avoid `any` unless there is no reasonable alternative.

Keep `apps/web/lib/types.ts` in sync with backend Pydantic models. Prefer
updating both sides in the same change when contracts move.

## Error Handling

Handle expected failures clearly.

Examples:

- source connector unavailable;
- source lookup found multiple likely matches;
- evidence is thin or conflicting;
- unsupported playable view for the available evidence;
- LLM quota/provider failure;
- no playable parts generated;
- invalid composition output;
- unavailable artifact.

Never silently ignore errors. Surface partial results when useful and explain
what failed.

## Docker

The backend should be containerized and remain container-friendly.

Requirements:

- backend Dockerfile stays functional;
- environment variables remain configurable;
- generated artifacts use configurable local paths;
- local Docker runtime works without a database;
- the backend can be deployed as a container image.

Do not introduce machine-specific assumptions.

## Persistence

The MVP does not need persistent memory or a database.

It is acceptable for chats, evidence profiles, generated songs, and artifacts
to disappear when the process or container restarts.

Do not add a database unless the product requirements change.

## Testing

Prefer focused tests at the layer where behavior lives.

Backend:

- unit-test domain validation and converters;
- unit-test application use cases with fake ports;
- test architecture boundaries;
- test agent/graph behavior with mocked LLMs;
- avoid network-dependent tests.

Frontend:

- run TypeScript checks;
- keep pure UI logic testable outside React when practical;
- test mixer/playback calculations separately from browser audio APIs.

Standard checks:

```bash
cd apps/api
python -m pytest
```

```bash
cd apps/web
npm run typecheck
node --test lib/trackMixerLogic.test.mjs
```

## Simplicity First

Do not introduce:

- microservices;
- event buses;
- message queues;
- CQRS;
- complex auth;
- persistent databases;
- multi-tenant infrastructure;
- enterprise abstractions without clear value.

Prefer the simplest solution that satisfies `PRODUCT.md`.

## Git Rules

Never perform git operations unless explicitly requested.

Do not:

- create commits;
- amend commits;
- squash commits;
- rebase;
- push;
- merge;
- delete branches;

without user approval.

You may prepare changes and suggest commits.

## Commit Philosophy

When asked to create commits:

- one logical change per commit;
- small and incremental commits;
- descriptive commit messages.

Examples:

```text
docs: align Daft Prompt product truth
feat: add song knowledge contracts
feat: add Songsterr evidence connector
feat: build artist style profiles
feat: route chat through evidence and composition tools
feat: compose from evidence briefs
feat: render playable teaching views
feat: support generated song edits
feat: refine Daft Prompt UI
```

The commit history should clearly explain how the project moved from the older
local-audio MVP toward Daft Prompt.

## Security

Never commit:

- secrets;
- passwords;
- API keys;
- private audio files;
- commercial audio fixtures;
- cloud credentials;
- `.env` files.

Use local, generated, or explicitly permitted fixtures for tests.
