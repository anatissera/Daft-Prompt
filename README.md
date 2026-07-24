<p align="center">
  <img src="apps/web/public/helmet-icon.png" alt="Daft Prompt helmet" width="120" />
</p>

<h1 align="center">Daft Prompt</h1>

<p align="center"><strong>Upload. Analyze. Compose. Understand.</strong></p>

Daft Prompt is a chat-first musical workspace. You talk to an assistant that analyzes real audio with music information retrieval (MIR) tools, researches known songs on the web, answers music questions grounded in evidence, and composes new songs with a team of LLM agents. Generated songs can be played in the browser, inspected as a piano roll or score, and exported as MIDI or MP3.

Built as a monorepo: a Python FastAPI backend (`apps/api`) and a Next.js frontend (`apps/web`).

## What it does

Everything happens in one chat. The assistant infers your intent and picks the right tools:

1. **Analyze a local track.** Upload an audio file and real MIR extracts stems, tempo, key, per-bar chords, and song structure.
2. **Research a known song.** Ask about a famous track and the backend gathers evidence from web sources (search, MusicBrainz, tab and chord sites) and fuses it into a reference profile.
3. **Ask music questions.** Answers are grounded in the analyzed or researched evidence, not just LLM recall.
4. **Compose.** Ask for a song from scratch ("compose a disco track") or guided by an analyzed reference ("something with this energy, but do not copy it"). A director agent sets key, tempo, form, and roster; instrument agents write their parts in parallel and negotiate; an arbiter resolves disagreements.
5. **Listen and export.** Play the result with a SoundFont synth in the browser, mix per instrument (volume, mute, solo), view the piano roll and the score, and export MIDI or MP3.

## Architecture

### Repository layout

```text
apps/
  api/                      FastAPI + LangGraph backend
    music_assistant/
      domain/               SongState, ReferenceProfile, AudioProfile models
      application/          Use cases: compose, analyze, research, answer, chat
      ports/                Interfaces: LLM, storage, MIR, stems, transcription
      infrastructure/
        mir/                Demucs, librosa, tempo grid, key, chords, structure
        web_research/       Search, MusicBrainz, parsers, evidence fusion
        storage/            Artifact store and song rendering
        llm.py              Provider routing (Gemini, Groq, OpenRouter, Vertex AI)
      agents/               Director, instrument, and arbiter agents
      music/                Validation and symbolic rendering helpers
      interfaces/           FastAPI HTTP and SSE boundary
    tests/
  web/                      Next.js App Router UI (React 19, TypeScript)
    app/                    Pages and API proxy routes
    components/             Chat, piano roll, mixer, score viewer, players
    lib/                    Pure view logic with node:test unit tests
docs/                       Architecture notes and learnings
plans/                      Roadmaps and implementation plans
PRODUCT.md                  Product source of truth
DESIGN.md                   UX direction
AGENTS.md                   Rules for coding agents working on this repo
```

The backend follows clean architecture boundaries: `domain` and `application` never import infrastructure directly, everything crosses through `ports`. Composition code never touches audio libraries; it only sees compact domain summaries such as `ReferenceProfile`. These boundaries are enforced by tests.

### Analysis pipeline

```text
audio file
  -> Demucs stem separation (drums / bass / vocals / other)
  -> harmonic source (bass + other preferred, HPSS fallback, raw mix last resort)
  -> tempo grid (beats and bars, drum-preferred onset detection)
  -> key candidates (Krumhansl-Schmuckler profiles, relative ambiguity flag)
  -> per-bar triad chords (major / minor / diminished, smoothed)
  -> structure detection (A/B/C sections from chord patterns)
  -> ReferenceProfile
```

Each stage degrades gracefully: if separation is unavailable or the bar grid is weak, confidence drops and an analysis note explains why.

### Composition pipeline

```text
prompt (+ optional ReferenceProfile)
  -> director: key, tempo, meter, form, instrumentation, rhythm commitments
  -> instrument agents compose parts in parallel into a shared SongState
  -> negotiation rounds through structured requests in shared state
  -> arbiter resolves remaining conflicts at the round cap
  -> deterministic rendering to MIDI and MusicXML
  -> SSE events stream progress to the UI
```

`SongState` is the canonical representation: MIDI pitches, durations in beats, notes anchored to absolute bar and beat. MIDI, MusicXML, and notation are exports, not the source of truth.

### API endpoints

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/health` | Liveness check |
| POST | `/references/analyze` | Analyze an uploaded audio file |
| POST | `/references/analyze/stream` | Same, with SSE progress events |
| POST | `/references/research` | Research a known song from web evidence |
| POST | `/references/research/stream` | Same, with SSE progress events |
| POST | `/chat` | Chat with intent routing (questions, compose, edits) |
| POST | `/chat/stream` | Same, with SSE progress events |
| POST | `/compose` | Compose a song |
| POST | `/compose/stream` | Same, with SSE progress events |
| GET | `/artifacts/{job_id}/{filename}` | Download rendered MIDI / MusicXML |

The frontend never calls the backend directly from the browser. Next.js API routes under `apps/web/app/api/` proxy requests to `API_BASE_URL` (default `http://localhost:8000`).

## Getting started

### Prerequisites

* Python 3.10+
* Node.js 18+
* Around 4 GB of disk for Python dependencies (torch and Demucs are heavy)

### Backend

```bash
cd apps/api

python3 -m venv venv
source venv/bin/activate
pip install -e ".[dev]"

cp .env.example .env   # then edit .env (see LLM configuration below)

uvicorn music_assistant.interfaces.api:app --reload --port 8000
```

The API runs at http://localhost:8000. It starts fine with no LLM configured: analysis, research, and evidence-grounded Q&A work without one, and composition returns a clear error asking for a provider.

### Frontend

```bash
cd apps/web

npm install
npm run dev
```

The UI runs at http://localhost:3000. If the backend is not on the default address, set `API_BASE_URL` before `npm run dev`.

### Docker

```bash
docker-compose up
# API: http://localhost:8000
# UI:  http://localhost:3000
```

## Deployment

The frontend runs on Vercel, the backend as a container on Google Cloud Run.

```text
BROWSER ──upload, up to 32 MiB, no time cap──► Cloud Run  /references/analyze/stream
BROWSER ──► Vercel proxy ──X-API-Key─────────► Cloud Run  /chat/stream
BROWSER ──► Vercel rewrite ──────────────────► Cloud Run  /artifacts/*
```

Audio uploads bypass the proxy because a Vercel function caps request bodies at
4.5 MB — 25 seconds of WAV — and caps its own duration at 300s, which is less
than stem separation takes. Chat and compose keep the proxy, which holds the
shared secret so the browser never sees it.

Going direct raises the ceiling rather than removing it: Cloud Run rejects
HTTP/1 requests over **32 MiB** at its edge. That is roughly 3 minutes of stereo
WAV, 6 of FLAC, or 13 of a 320 kbps MP3, so it only bites lossless files. The UI
checks the size first, because the rejection arrives as an HTML error page.

Measured on the deployed service against the same 2:30 stereo WAV:

| Stage | 4 vCPU | 8 vCPU |
|---|---|---|
| Demucs stem separation | 171s | 94s |
| Harmonic source | 44s | 32s |
| Tempo grid, key, chords, structure | 25s | 17s |
| **Total** | **244s** | **157s** |

Separation dominates and scales close to linearly with cores, so the service
runs on 8 vCPU: it costs twice as much per second but finishes in a bit over
half the time, which comes out roughly cost-neutral. Extrapolated to a 4-minute
track that is still around four minutes of waiting — which is why analysis
cannot go through a function capped at 300s.

A Cloud Storage bucket is mounted at `/mnt/artifacts`, so analysed references
and rendered songs persist across restarts, scale-to-zero and multiple
instances — a user can analyse a track, come back later, and still ask about it.
Raw audio uploads and Demucs stems stay on local `/tmp`: they are large and
disposable, and GCS FUSE latency would only slow separation down.

### Environment

Backend (Cloud Run):

| Variable | Purpose |
|---|---|
| `ARTIFACTS_DIR` | Rendered songs (MIDI/MusicXML); points at the mounted bucket so they persist |
| `REFERENCE_STORE_DIR` | Analysed references (JSON); the mounted bucket. Unset falls back to an in-memory dict |
| `REFERENCE_UPLOAD_DIR` | Raw audio and stems; local `/tmp`, deliberately not persisted |
| `LLM_PROVIDER` + provider keys | See LLM configuration below |
| `API_KEY` | Shared secret required on the chat and compose routes |
| `CORS_ALLOW_ORIGINS` | The frontend's production origin |
| `CORS_ALLOW_ORIGIN_REGEX` | Preview deployments, whose hostnames are generated |

Frontend (Vercel), all three needed in Production and Preview:

| Variable | Purpose |
|---|---|
| `API_BASE_URL` | Backend URL for the proxy routes and the `/artifacts/*` rewrite |
| `NEXT_PUBLIC_API_BASE_URL` | Same URL, exposed to the browser for uploads |
| `API_KEY` | Must match the backend's |

`NEXT_PUBLIC_*` is inlined at build time, so changing it requires a redeploy.

### Redeploying

Merging to `main` with changes under `apps/api/` triggers
`.github/workflows/deploy-api.yml`, which builds the image, pushes it to Artifact
Registry and rolls out a new Cloud Run revision. Authentication uses Workload
Identity Federation, so no service-account key lives in the repository.

By hand:

```bash
gcloud run deploy daft-prompt-api --source apps/api --region us-east1
```

Environment variables, sizing, secrets and the bucket mount live on the service,
not in the workflow, so they can be changed with `gcloud run services update`
without a rebuild. The bucket was attached once with:

```bash
gcloud run services update daft-prompt-api --region us-east1 \
  --add-volume=name=artifacts,type=cloud-storage,bucket=daft-prompt-udesa-artifacts \
  --add-volume-mount=volume=artifacts,mount-path=/mnt/artifacts
```

## LLM configuration

The backend is provider-agnostic. Pick one provider via environment variables (or `.env` in `apps/api`, see `.env.example` for the full list):

| Provider | Env vars | Notes |
|----------|----------|-------|
| Gemini | `LLM_PROVIDER=gemini`, `GEMINI_API_KEY` | Default. Free tier works |
| Groq | `LLM_PROVIDER=groq`, `GROQ_API_KEY` | |
| OpenRouter | `LLM_PROVIDER=openrouter`, `OPENROUTER_API_KEY` | Also any OpenAI-compatible server (llama-server, vLLM, OpenCode Go) via `OPENROUTER_BASE_URL` |
| Vertex AI | `LLM_PROVIDER=vertexai`, `GOOGLE_CLOUD_PROJECT` | Uses Application Default Credentials, no API key |

The deployed backend uses OpenCode Go through the OpenRouter slot — a flat-fee
gateway, so a live demo can't run out of quota mid-compose:

```bash
LLM_PROVIDER=openrouter
OPENROUTER_BASE_URL=https://opencode.ai/zen/go/v1
OPENROUTER_MODEL_DIRECTOR=minimax-m3      # one call per compose, highest stakes
OPENROUTER_MODEL_INSTRUMENT=minimax-m2.7  # 10-21 calls in parallel
OPENROUTER_MODEL_ARBITER=minimax-m3
LLM_FALLBACK_PROVIDERS=gemini,groq
```

Useful knobs:

* `MODEL_DIRECTOR`, `MODEL_INSTRUMENT`, `MODEL_ARBITER` set the model per agent role.
* `GEMINI_MODEL_FALLBACKS` and `LLM_FALLBACK_PROVIDERS` define fallback chains when a model or provider hits quota. Note that structured-output failures do *not* escalate to the next provider — a model that truncates its tool call falls through to the deterministic fill instead.
* `LLM_RPM_LIMIT`, `LLM_MAX_RETRIES`, `LLM_FAIL_FAST_ON_QUOTA` are free-tier guardrails: quota errors surface in the UI instead of producing empty instrument parts.
* `MAX_ROUNDS` caps negotiation rounds during composition.
* `LANGSMITH_TRACING=true` plus `LANGSMITH_API_KEY` enables LangSmith tracing (optional).

## Testing

Backend:

```bash
cd apps/api
export PYTEST_DISABLE_PLUGIN_AUTOLOAD=1
pytest
```

The suite covers the MIR feature modules (with injectable fakes, so no heavy audio processing), the composition agents, HTTP and SSE boundaries, and the clean architecture rules themselves. Real Demucs separation is skipped in tests because it is slow.

Frontend:

```bash
cd apps/web
npm run typecheck
node --test lib/*.test.mjs
```

## Development workflow

* `main` holds the stable, releasable state.
* `develop` is the integration branch. Feature branches (`feat/*`, `fix/*`) come off `develop` and merge back via PR.
* `AGENTS.md` defines the rules for AI coding agents contributing to this repo, including the requirement to keep the in-app architecture diagram (`apps/web/components/PipelineGraphs.tsx`) in sync with pipeline changes.

## Documentation map

* [`PRODUCT.md`](PRODUCT.md): product behavior and MVP scope (source of truth)
* [`DESIGN.md`](DESIGN.md): chat-first UX direction
* [`AGENTS.md`](AGENTS.md): agent responsibilities, constraints, and security boundaries
* [`docs/architecture.md`](docs/architecture.md): technical layers and boundaries
* [`plans/`](plans/): implementation phases and future vision

## Troubleshooting

**pytest fails or behaves oddly on startup.** Set `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`. On systems with ROS installed, its `launch_testing` plugin interferes with plugin auto-discovery.

**Composition returns an LLM configuration error.** Set `LLM_PROVIDER` and the matching API key (see LLM configuration above). Analysis and Q&A work without an LLM; composition does not.

**Demucs is slow or runs out of memory.** Stem separation is the heaviest stage. It runs on CPU but benefits greatly from a GPU. Analysis falls back to HPSS on the raw mix when separation is unavailable.

**Port 3000 is taken.** Next.js falls back to the next free port automatically; check the terminal output for the actual URL.

## Credits

Built for the NLP course at Universidad de San Andres by:

* [Ana Paula Tissera](https://github.com/anatissera)
* [Franco Amato de Lusarreta](https://github.com/famatodlr)
* [Juan Cruz Giner Pulero](https://github.com/ginerJuanUdesa)
* [Valentino Arbelaiz Alberti](https://github.com/varbelaiz)
* [Naomi Couriel](https://github.com/naomicouriel)

Music analysis meets multi-agent reasoning.
