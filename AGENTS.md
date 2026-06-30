# AGENTS.md

This repository contains LLMinem, a chat-first musical workspace for analyzing
local songs and composing new songs from scratch or from an analyzed reference.

The application should stay focused. The goal is not to demonstrate every
possible agent pattern or music library; the goal is to deliver a clean,
production-minded MVP that feels coherent and works locally.

Before implementing any change, read:

1. `PRODUCT.md`
2. `DESIGN.md`
3. `docs/architecture.md`
4. `plans/chat-musical-mvp.md` when working on MVP implementation

`PRODUCT.md` is the product source of truth. `DESIGN.md` defines UX direction.
`docs/architecture.md` preserves technical boundaries. The plan in
`plans/chat-musical-mvp.md` is the current roadmap.

## Repository

LLMinem is a monorepo with a Python backend and a Next.js frontend.

```text
apps/
  api/                    # FastAPI, LangGraph, music/audio processing
    music_assistant/
      domain/             # SongState, ReferenceProfile, AudioProfile
      application/        # compose/analyze/answer/chat use cases
      ports/              # LLM, storage, audio analysis, transcription, stems
      infrastructure/     # provider, storage, MIR, and deployment adapters
      interfaces/         # FastAPI HTTP/SSE boundary
      agents/             # director, instrument, arbiter agents
      music/              # validation and symbolic rendering helpers
    tests/
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
- local MIR/audio analysis adapters
- Next.js
- React
- TypeScript
- Docker

## Before Implementing Anything

Always follow this process:

1. Read `PRODUCT.md`.
2. Read `DESIGN.md`.
3. Read `docs/architecture.md` if touching backend boundaries.
4. Inspect the existing implementation.
5. Identify existing patterns.
6. Extend existing patterns whenever possible.
7. Only then implement changes.

Do not introduce new patterns without a clear reason.

## Product Rules

The MVP is chat-first.

The user should mostly type what they want:

- analyze a local audio file;
- ask a question about a song;
- compose from scratch;
- compose from an analyzed reference.

Avoid turning the product into:

- a dashboard-first app;
- a form-heavy generator;
- a full DAW;
- a notation-first product;
- a YouTube ingestion tool.

Use local files for analysis in the MVP. YouTube search, download, conversion,
and commercial-song acquisition are out of scope.

Chord analysis is probabilistic. Use language like:

> "Probably Am - F - C - G in this section."

Do not present estimated chords, key, beats, or sections as certain when the
tools cannot support that certainty.

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

- compose a song;
- analyze a local reference;
- answer a music question from a `ReferenceProfile`;
- route a chat message to analysis, explanation, or composition.

Domain models represent stable concepts.

Examples:

- `SongState`;
- `ReferenceProfile`;
- `AudioProfile`;
- sections;
- chord estimates;
- negotiation requests.

Ports define dependencies.

Examples:

- LLM provider;
- audio analyzer;
- transcription;
- stem separation;
- artifact storage.

Infrastructure adapters implement ports. They should not leak provider or library
details into `application/`, `domain/`, `agents/`, or `music/`.

## Composition Rules

The existing multi-agent composer is valuable and should remain isolated.

Composition flow:

```text
director
  -> instrument agents
  -> negotiation through shared SongState
  -> arbiter
  -> render artifacts
```

Agent communication happens through structured `negotiation_requests` in shared
state. Do not add a separate message bus unless there is a strong reason.

Composition agents may consume a compact `ReferenceProfile` summary. They must
not call audio analyzers, storage adapters, YouTube resolvers, or raw provider
APIs directly.

Do not copy estimated reference chords by default. Use them only when the user
explicitly asks for harmonic guidance or accepts it in chat.

## UI Rules

The UI should be conversational first.

Components and pages are responsible for:

- rendering;
- user interaction;
- local UI state;
- calling API routes.

UI should not contain business logic for musical analysis, chat routing, or
composition decisions.

Prefer:

- one main chat surface;
- local audio attachment;
- contextual analysis details;
- contextual generated-song playback;
- compact tool/agent details;
- playback and mute/solo only after a song exists.

Avoid:

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

- unsupported audio file;
- analyzer failure;
- low-confidence analysis;
- missing reference context;
- LLM quota/provider failure;
- no playable parts generated;
- invalid composition output;
- unavailable artifact.

Never silently ignore errors. Surface partial results when useful and explain
what failed.

## Docker

The backend should be containerized early and remain container-friendly.

Requirements:

- backend Dockerfile stays functional once added;
- environment variables remain configurable;
- generated artifacts and uploads use configurable local paths;
- local Docker runtime works without a database;
- the backend can be deployed as a container image.

Do not introduce machine-specific assumptions.

## Persistence

The MVP does not need persistent memory or a database.

It is acceptable for chats, uploaded references, generated songs, and artifacts
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
docs: add product direction
docs: define chat-first design rules
chore: add backend docker runtime
feat: add reference profile contract
feat: analyze local audio files
feat: route chat intents
feat: compose from reference profile
feat: redesign UI around chat
```

The commit history should clearly explain how the project moved from the
composition prototype toward the chat musical MVP.

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

