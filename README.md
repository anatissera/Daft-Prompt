# Daft Prompt

Daft Prompt is a chat-first AI music assistant. Ask it about songs from public
evidence, learn playable parts through tabs/keys/rolls, compose original MIDI
sketches, or edit a generated song in natural language.

Song knowledge comes from evidence connectors such as Songsterr, tab/chord
pages, metadata pages, artist/album information, and style or corpus references.
The app keeps source attribution and uncertainty visible instead of claiming
perfect analysis.

User-uploaded file analysis and local audio analysis are not supported product
paths for Daft Prompt.

## Quick Start

### 1. Start the app

Install [Docker Desktop](https://www.docker.com/products/docker-desktop/), then
run this from the cloned repository:

```bash
docker compose up --build
```

Open [http://localhost:3000](http://localhost:3000). The chat is usable with
no account configuration and explains how to enable composition when a provider
has not been configured. API health is available at
[http://localhost:8000/health](http://localhost:8000/health).

### 2. Enable your preferred Vertex AI Gemini provider

Vertex is the first-class provider in the default image; it uses your existing
Google Application Default Credentials (ADC), not an API key.

```bash
gcloud auth application-default login
cp .env.example .env
```

Set `GOOGLE_CLOUD_PROJECT` in the uncommitted root `.env` to your project ID,
then start the Vertex-enabled stack:

```bash
export GCP_ADC_HOST_PATH="$HOME/.config/gcloud"
docker compose -f docker-compose.yml -f docker-compose.vertex.yml up --build
```

Now ask for a composition in the chat, for example: "Compose an eight-bar
French-house groove with a warm bassline." The credential directory is mounted
read-only; no key or credential is copied into the image or repository.

If your ADC lives elsewhere, set `GCP_ADC_HOST_PATH` to that directory. Use
`gcloud config get-value project` to discover the active project ID.

## Configuration

[.env.example](./.env.example) is the single configuration template. Copy it
to a root `.env` only when a provider or optional feature is needed; `.env` is
ignored by Git.

The supported provider choices are `vertexai`, `gemini`, `groq`, and
`openrouter`. The Compose runtime forwards their documented key variables. For
the non-Vertex alternatives, select `LLM_PROVIDER` and set its matching key in
the root `.env`, then run `docker compose up --build`.

Songsterr/web research is enabled by default. Set
`ENABLE_WEB_RESEARCH=false` in `.env` if you need an offline runtime; named-song
requests will then explain how to restore it instead of making a network call.

For a non-Docker backend workflow, copy the same template to `apps/api/.env`,
install dependencies, and run the API from `apps/api`:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[vertexai]"
uvicorn music_assistant.interfaces.api:app --reload --port 8000
```

## What It Does

- Conversational answers about known songs from attributed public evidence.
- Songsterr/tab/chord/metadata research with uncertainty and source visibility.
- Playable teaching views such as guitar tab, bass tab, drum tab, piano keys,
  chord charts, and piano roll as the implementation converges.
- Composition from a text prompt, song evidence, artist/band style profile,
  album, or genre traits.
- Natural-language edits over generated MIDI/SongState.
- Vertex/Gemini-backed director, instrument, negotiation, and arbiter agents.
- Browser playback, per-track mute/solo, MIDI export, and audio export where
  the playback path supports it.

## Architecture

```text
Next.js chat UI
  -> FastAPI HTTP/SSE boundary
  -> application use cases
  -> domain models and ports
  -> provider, source connector, storage, render, and deployment adapters

Composition: CompositionBrief -> director/orchestrator
             -> dynamic instrument agents -> negotiation -> arbiter
             -> canonical SongState -> MIDI/audio/playable views
```

The architecture keeps raw scraped pages, provider responses, and connector
details out of composition. Agents receive compact domain summaries such as
`SongKnowledgeProfile`, `ArtistStyleProfile`, and `CompositionBrief`.

## Validation

```bash
cd apps/api && python -m pytest
cd apps/web && npm run typecheck && node --test lib/trackMixerLogic.test.mjs
```

Backend tests use fakes for connector and provider boundaries where possible,
so they should not depend on network access.

## Further Documentation

- [Product behavior](./PRODUCT.md)
- [Chat-first UX direction](./DESIGN.md)
- [Architecture boundaries](./docs/architecture.md)
- [Daft Prompt convergence plan](./plans/daft-prompt-convergence.md)
- [Superseded local-audio MVP plan](./plans/chat-musical-mvp.md)
- [Current engineering progress](./PROGRESS.md)
