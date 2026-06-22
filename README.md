# Multi-agent Band 🎵

A multi-agent music composition system. You describe a style — *"Bee Gees-style
disco"*, *"slow blues"*, *"Argentine cumbia"* — and a band of LLM agents composes
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
| Notation render | MuseScore or LilyPond |
| Tests | pytest |

## Status

Design phase. The full research and architecture write-up lives in
[`PRD.md`](./PRD.md). Implementation has not started yet.

## Pipeline

```
style request → director (arrangement + roster) → instrument agents compose
   → negotiation rounds (shared state) → validation → convergence / arbiter
   → render → song.mid + sheet music
```

## Roadmap

1. Pick the free LLM provider and wire up its LangChain integration.
2. Deterministic core: `schema` → `validators` → `to_music21` → `render_midi`
   (testable without any LLM calls).
3. Director + instrument agents and the LangGraph negotiation loop.
4. Sheet-music rendering + CLI.

See [`PRD.md`](./PRD.md) for the JSON schema, architecture diagram, folder
layout, failure modes, and verification plan.

## Branching

- `main` — stable / released.
- `develop` — integration branch; feature branches merge here.
