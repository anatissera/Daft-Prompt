# Multiagent Band 🎵

A multi-agent music composition system. You describe a style and a band of LLM agents composes
a full song for it.

## How it works

A **director agent** interprets the request and *reasons about* which instruments
the genre needs (it is **not** a hardcoded genre→instrument table). It then spawns
one **specialized sub-agent per instrument**. Each sub-agent composes its part and
**negotiates with the others** during composition — the bass can ask the drums to
leave space for a fill, the guitar can propose a chord change in the bridge — over
a shared, structured song state. The final song is exported to **MIDI** and
rendered as **sheet music**.

## Why it's agentic (not just a chain of LLM calls)

- **Reasoned instrumentation** — the ensemble is inferred from the style, not looked up.
- **Feedback-driven iteration** — each part is revised in response to other agents.
- **Dynamic structure** — which agents exist and how many negotiation rounds run is
  decided at runtime and adapts to the request.
- **Goal-seeking with convergence** — agents negotiate toward a coherent whole and
  stop at a fixed point (or are force-converged), rather than emitting one shot each.

## LLM provider — free tier (not decided yet)

To avoid paid API usage, the project targets a **free, no-credit-card LLM API**.
Three candidates are on the table; the final pick is **TBD**:

| Provider | Model | LangChain integration | Free tier (≈) | Notes |
|---|---|---|---|---|
| **Google Gemini** (AI Studio) | Gemini 2.5 Flash | `langchain-google-genai` → `ChatGoogleGenerativeAI` | ~1,500 req/day, 10 RPM | Native structured output, best LangGraph fit |
| **Groq** | Llama 3.3 70B | `langchain-groq` → `ChatGroq` | ~1,000 req/day | Extremely fast (LPU) |
| **OpenRouter** | free models (DeepSeek, Gemini, …) | OpenAI-compatible base URL | ~200 req/day/model | Wide model choice |

> All free tiers may use prompts for training — fine for a course project, not for
> sensitive data. Set the key via env var (`GEMINI_API_KEY` / `GROQ_API_KEY` /
> `OPENROUTER_API_KEY`); never commit keys.

## Related work

Two academic systems do something similar — worth reading and differentiating against:

- **ComposerX** ([arXiv:2404.18081](https://arxiv.org/abs/2404.18081)) — leader +
  melody/harmony/instrument + review + arrangement agents over conversation chains.
- **CoComposer** ([arXiv:2509.00132](https://arxiv.org/abs/2509.00132)) — 5 agents,
  fewer rounds; found a separate per-instrument-agent design *less* efficient.

Our angle differs: the director **reasons the instrumentation from the genre**,
agents do **peer negotiation via shared state**, and we target **MIDI + engraved
sheet music**. CoComposer's efficiency caveat is handled by our round cap +
convergence gate (see `PRD.md`).

## Tech stack

| Concern | Choice |
|---|---|
| Orchestration | [LangGraph](https://langchain-ai.github.io/langgraph/) (typed shared state, cycles, checkpointing) |
| LLM | Free-tier provider — **Gemini / Groq / OpenRouter** (TBD), via its LangChain integration |
| Data model | Pydantic v2 (canonical `SongState` + parts) |
| Music theory & notation | [music21](https://web.mit.edu/music21/) (→ MusicXML → sheet music) |
| MIDI export | [pretty_midi](https://github.com/craffel/pretty-midi) |
| Notation render | MuseScore or LilyPond (server) · OpenSheetMusicDisplay (browser) |
| Backend API | [FastAPI](https://fastapi.tiangolo.com/) (SSE-streamed negotiation) |
| Frontend | [Next.js](https://nextjs.org/) + React + TypeScript, deployed to [Vercel](https://vercel.com/) |
| Hosting | Vercel (frontend) + container host for the Python backend (Render / Railway / Fly.io) |
| Tests | pytest |

## Status

Working prototype. The backend has the canonical `SongState` schema,
deterministic validation/rendering, director/instrument/arbiter agents,
bounded negotiation rounds, FastAPI endpoints, and SSE streaming. The Next.js UI
can submit a style, show the roster/negotiation feed, render MusicXML, and play
the MIDI artifact.

The listening/reference-analysis feature is **not implemented yet**. The codebase
now has an architectural boundary for it (`reference_analysis`) so future audio
analysis can be added without coupling provider details, MIR libraries, downloads,
or raw audio artifacts to composition, rendering, or the existing API.

## Pipeline

```
style request → director (arrangement + roster) → instrument agents compose
   → negotiation rounds (shared state) → validation → convergence / arbiter
   → render → song.mid + sheet music
```

The pipeline is a Python (FastAPI) backend; a **Next.js** web UI on **Vercel**
streams the negotiation live and plays the result. See [`PRD.md`](./PRD.md) →
*Frontend & Deployment* for why the Python backend runs on a container host rather
than directly on Vercel.

## Running locally

**Backend** (`apps/api`):

```bash
cd apps/api
python -m venv .venv && .venv/bin/pip install -e ".[dev]"
cp .env.example .env   # optional: uncomment LLM_PROVIDER + an API key to use a real director
.venv/bin/uvicorn llm_band.api:app --reload
```

Runs on http://localhost:8000 (health check: `/health`). With no LLM key set, `/compose`
falls back to a canned demo song — no provider required to try the pipeline end-to-end.

**Frontend** (`apps/web`):

```bash
cd apps/web
npm install
cp .env.local.example .env.local   # points at http://localhost:8000
npm run dev
```

Runs on http://localhost:3000 (Next.js picks another free port if 3000 is taken).

## Roadmap

1. Harden the current composition prototype: provider selection, prompt quality,
   validation repairs, artifact storage, deployment, and observability.
2. Keep `SongState` mirrored between Pydantic and TypeScript, preferably generated
   from JSON schema in CI.
3. Build real `reference_analysis` adapters later: authorized source resolution,
   MIR/audio profiling, optional Gemini audio explanations, and storage.
4. Add a listening UI only after the reference-analysis use cases exist behind
   fakes and provider adapters.
5. Let composition consume only compact `ReferenceProfile` summaries, never raw
   URLs/audio/provider internals.

See [`PRD.md`](./PRD.md) for the JSON schema, architecture diagram, folder
layout, failure modes, and verification plan.

## Branching

- `main` — stable / released.
- `develop` — integration branch; feature branches merge here.
