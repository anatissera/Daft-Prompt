# LLMinem

LLMinem is a conversational music workspace.

The product goal is a chat-first assistant that can analyze local songs with
music tools and compose new songs either from scratch or from an analyzed
reference.

The current repo already contains a working multi-agent composition prototype.
The next MVP plan extends it into the chat musical product described in
[`PRODUCT.md`](./PRODUCT.md).

## Source Of Truth

- [`PRODUCT.md`](./PRODUCT.md): product behavior and MVP scope.
- [`DESIGN.md`](./DESIGN.md): UX direction for the chat-first interface.
- [`docs/architecture.md`](./docs/architecture.md): technical boundaries and
  architecture notes.
- [`plans/chat-musical-mvp.md`](./plans/chat-musical-mvp.md): current
  implementation roadmap.
- [`plans/multiagent-band.md`](./plans/multiagent-band.md): historical plan for
  the composition engine.

## What Exists Today

Working prototype:

- Python FastAPI backend.
- Clean architecture layers: `domain`, `application`, `ports`,
  `infrastructure`, and `interfaces`.
- Canonical `SongState` Pydantic schema.
- Director, instrument, and arbiter agents.
- Bounded negotiation rounds through LangGraph shared state.
- Deterministic validation and rendering.
- MIDI and MusicXML artifact generation.
- SSE streaming for composition events.
- Next.js UI that can submit a style prompt, show roster/negotiation activity,
  render MusicXML, and play generated parts through a simple mixer.
- Tests for validators, converters, agents, negotiation, provider routing,
  streaming, and architecture boundaries.

Not implemented yet:

- Chat-first product flow.
- Local audio upload and real MIR analysis.
- Tempo/key/energy/section/chord extraction from audio.
- Evidence-grounded music Q&A over a `ReferenceProfile`.
- Reference-guided composition through chat.

## Product Direction

The MVP should support one conversational flow:

1. The user chats naturally.
2. The user can attach or select a local audio file.
3. The backend analyzes the file into a compact `ReferenceProfile`.
4. The assistant answers music questions using tool evidence.
5. The user can compose from scratch.
6. The user can compose from the analyzed reference.
7. The generated song is playable, exportable, and inspectable.

Chord estimates should be treated as probabilities, not facts. Good answer style:

> "Probably Am - F - C - G in this section."

By default, reference-guided composition should transfer tempo, structure, energy,
and mood. It should not copy estimated chords unless the user asks for harmonic
guidance.

## Architecture

Current backend layer map:

```text
llm_band/
  domain/          # SongState and ReferenceProfile/AudioProfile models
  application/     # compose/analyze/answer use cases
  ports/           # LLM, storage, audio analysis, transcription, stems
  infrastructure/  # provider/storage/MIR adapters and placeholders
  interfaces/      # FastAPI HTTP/SSE boundary
```

The existing composition pipeline:

```text
style request
  -> director (arrangement + roster)
  -> instrument agents compose
  -> negotiation rounds through shared SongState
  -> convergence / arbiter
  -> render
  -> song.mid + song.musicxml
```

The planned chat musical pipeline:

```text
chat message + optional local audio
  -> chat intent router
  -> local audio analysis and/or music Q&A and/or composition
  -> ReferenceProfile and/or SongState
  -> conversational answer + playable artifacts
```

Composition agents should consume compact `ReferenceProfile` summaries only.
They should not call MIR libraries, storage adapters, provider upload APIs, or
raw audio directly.

## Running Locally

Backend (`apps/api`):

```bash
cd apps/api
python -m venv .venv
.venv/bin/pip install -e ".[dev]"
cp .env.example .env
.venv/bin/uvicorn llm_band.api:app --reload
```

Runs on [http://localhost:8000](http://localhost:8000). Health check:
`/health`.

With no LLM key set, `/compose` falls back to a canned demo song, so the current
composition pipeline can run end-to-end without a provider.

Frontend (`apps/web`):

```bash
cd apps/web
npm install
cp .env.local.example .env.local
npm run dev
```

Runs on [http://localhost:3000](http://localhost:3000). Next.js may choose a
different port if 3000 is taken.

Docker Compose:

```bash
docker compose up --build
```

The compose runtime starts the FastAPI backend on
[http://localhost:8000](http://localhost:8000) and the Next.js frontend on
[http://localhost:3000](http://localhost:3000). The frontend talks to the API
through `API_BASE_URL=http://api:8000` inside the compose network. Backend
artifacts are written to `apps/api/outputs`.

## Verification

Backend:

```bash
cd apps/api
python -m pytest
```

Frontend:

```bash
cd apps/web
npm run typecheck
node --test lib/trackMixerLogic.test.mjs
```

## Deployment Direction

The MVP does not require persisted memory or a database. It is acceptable for
uploaded references, chats, songs, and generated artifacts to be lost when the
process or container restarts.

The backend is containerized early because Python music/audio libraries and
future MIR dependencies are better suited to a container host than to serverless
frontend functions.

Likely deployment shape:

- Next.js frontend on Vercel or a similar web host.
- FastAPI backend as a container on Render, Railway, Fly.io, Cloud Run, or
  similar.
- Local filesystem storage for MVP/local development.
- Optional object storage later for durable deployed artifacts.

## Branching

- `main` — stable / released.
- `develop` — integration branch.
- feature branches — individual slices of the MVP plan.
