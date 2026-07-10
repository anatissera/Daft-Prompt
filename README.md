# Daft Prompt

Daft Prompt is a chat-first music workspace. Ask it to compose an original
sketch, explore a musical idea, or—when explicitly enabled—analyze a local
audio reference. Generated songs are playable and exportable as MIDI and
MusicXML.

The normal runtime favors responsive composition: it includes the Vertex AI
Gemini provider, but leaves the large local audio-analysis stack out of the
image. Audio analysis is available as a deliberate opt-in.

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

Now ask for a composition in the chat, for example: “Compose an eight-bar
French-house groove with a warm bassline.” The credential directory is mounted
read-only; no key or credential is copied into the image or repository.

If your ADC lives elsewhere, set `GCP_ADC_HOST_PATH` to that directory. Use
`gcloud config get-value project` to discover the active project ID.

### 3. Enable local audio analysis only if you need it

Audio uploads install PyTorch, Demucs, MIR libraries, `ffmpeg`, and native build
tools. That makes the image much slower and larger, so it is intentionally
separate:

```bash
docker compose -f docker-compose.yml -f docker-compose.audio.yml up --build
```

To use Vertex and uploads together, include both overlays:

```bash
export GCP_ADC_HOST_PATH="$HOME/.config/gcloud"
docker compose \
  -f docker-compose.yml \
  -f docker-compose.vertex.yml \
  -f docker-compose.audio.yml \
  up --build
```

The attachment control appears only in this audio-enabled runtime. Calling an
upload endpoint without it returns a clear opt-in instruction rather than a
missing-dependency error.

## Configuration

[.env.example](./.env.example) is the single configuration template. Copy it
to a root `.env` only when a provider or optional feature is needed; `.env` is
ignored by Git.

The supported provider choices are `vertexai`, `gemini`, `groq`, and
`openrouter`. The Compose runtime forwards their documented key variables. For
the non-Vertex alternatives, select `LLM_PROVIDER` and set its matching key in
the root `.env`, then run `docker compose up --build`.

For a non-Docker backend workflow, copy the same template to `apps/api/.env`,
install the desired extras, and run the API from `apps/api`:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[vertexai]"
uvicorn music_assistant.interfaces.api:app --reload --port 8000
```

Install local analysis dependencies only when required:

```bash
pip install -e ".[audio-analysis]"
```

## What it does

- Conversational composition from a text prompt or compact analyzed reference.
- Vertex/Gemini-backed director, instrument, negotiation, and arbiter agents.
- Browser playback, per-track mute/solo, MIDI export, and MusicXML export.
- Optional local audio analysis with clearly probabilistic chord, key, tempo,
  and section estimates.
- Optional web research that remains separate from the interactive composition
  pipeline.

## Architecture

```text
Next.js chat UI
  -> FastAPI HTTP/SSE boundary
  -> application use cases
  -> domain models and ports
  -> provider, storage, research, and optional MIR adapters

Composition: director -> grouped instrument agents -> negotiation -> arbiter
             -> canonical SongState -> MIDI/MusicXML/playback
```

The architecture keeps raw audio adapters out of composition. Agents receive a
compact `ReferenceProfile`, never provider clients or audio-analyzer details.

## Validation

```bash
cd apps/api && python -m pytest
cd apps/web && npm run typecheck && node --test lib/*.test.mjs && npm run build
```

The backend suite uses fakes for expensive local MIR work, so it does not need
Demucs models or network access.

## Further documentation

- [Product behavior](./PRODUCT.md)
- [Chat-first UX direction](./DESIGN.md)
- [Architecture boundaries](./docs/architecture.md)
- [Implementation roadmap](./plans/chat-musical-mvp.md)
- [Current engineering progress](./PROGRESS.md)
