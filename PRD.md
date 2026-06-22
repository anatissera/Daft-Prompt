# Multi-agent Band — Product Requirements & Design Document (PRD)

## Context

**LLM Band** is a multi-agent music composition system. A user describes a style
("Bee Gees-style disco", "slow blues", "Argentine cumbia"). A **director agent**
interprets the request, *reasons about* which instruments the genre needs (not
hardcoded), and spawns one **instrument sub-agent** per part. Sub-agents compose
their parts and **negotiate with each other** ("bass asks drums to leave space in
bar 5", "guitar proposes a chord change in the bridge") over a shared song state.
Final output is a structured representation rendered to **sheet music** and
exported to **MIDI**.

This document is research + design only — no implementation code. Decisions:
- **Framework: LangGraph** (state-graph orchestration).
- **Output: JSON shared state (intermediate) → MIDI (final), plus sheet-music notation.**
- **Goal: production-leaning prototype** — care about validation, retries, caching/cost, and eval from the start.
- **LLM: a free, no-credit-card provider** — final pick TBD among **Google Gemini
  (`langchain-google-genai`)**, **Groq (`langchain-groq`)**, and **OpenRouter
  (OpenAI-compatible)**. LangGraph is provider-agnostic, so the choice only affects
  the `llm.py` factory. Gemini 2.5 Flash is the leading candidate (native
  structured output, generous free quota). See `README.md` for the comparison.

---

## Research Findings

### 1. Music representation formats

| Format | LLM-friendliness | Python tooling | Render / playback | Verdict for this system |
|---|---|---|---|---|
| **ABC notation** | **Best** — terse, line-oriented, lots of training data; easy for an LLM to emit a single monophonic part | `music21` parses ABC | Renders via abcjs/MuseScore; → MIDI via music21 | Great for *single-part* LLM emission, weak for multi-instrument coordination |
| **MusicXML** | Poor — verbose XML, easy to produce malformed | `music21` is the reference parser | Best notation interchange; opens in MuseScore/Finale | Excellent *interchange/export* target, bad *generation* target |
| **MIDI** | Poor — binary, not directly emittable | `mido`, `pretty_midi`, `music21` | Universal playback; not notation | **Final export only**, never the LLM's output |
| **LilyPond** | Medium — plaintext, version-controllable, but niche syntax, more hallucination risk | `music21` can export LilyPond | Best-engraved PDFs | Optional high-quality notation export |
| **JSON custom schema** | **Best for coordination** — strict schema = validatable, diffable, mergeable across agents | Native (`pydantic`) | Not directly; convert to music21 → MIDI/notation | **The shared state + agent I/O format** |

**Recommendation:** Use a **JSON/Pydantic schema as the canonical shared state and
the agents' structured output**, then convert to `music21` objects for
**MusicXML/sheet music** and **MIDI** export. JSON wins because agents must *read,
diff, and patch each other's parts* during negotiation — a structured object is
far more robust than re-parsing ABC/MusicXML every round. ABC stays available as
an *optional* compact representation if you want a model to sketch a single
melodic line, but the source of truth is JSON.

### 2. Python music libraries

| Library | Strength | Use here |
|---|---|---|
| **music21** | The Swiss-army knife: parse ABC/MusicXML, music theory (keys, chords, ranges, transposition), MusicXML + MIDI export, MuseScore/LilyPond rendering | **Primary** — conversion hub + notation + theory validation |
| **pretty_midi** | Clean MIDI construction, tempo/instrument handling, easy programmatic note insertion | **MIDI export** (simpler API than music21 for building tracks from JSON) |
| **mido** | Low-level MIDI messages | Only if you need byte-level control; otherwise skip |
| **midiutil** | Minimal MIDI writer | Redundant given pretty_midi |
| **mingus** | Music-theory helpers (scales/chords/progressions) | Optional — music21 already covers this; mingus useful for quick progression generation/validation if preferred |

**Recommendation:**
- **Parsing LLM output:** Pydantic (JSON) — not a music lib. Validate musical
  semantics with **music21** (note in range, valid duration, key membership).
- **Conversion hub & sheet music:** **music21** (JSON → `stream.Score` → MusicXML
  → MuseScore/LilyPond render).
- **MIDI export:** **pretty_midi** (cleanest JSON → multitrack `.mid`), or music21
  if you want a single library. Pick one; pretty_midi recommended for the export path.
- Drop midiutil and mido for this scope; mingus optional.

### 3. Multi-agent framework — why LangGraph (chosen)

| Framework | Shared state | Comms topology | Loop control | Notes |
|---|---|---|---|---|
| **LangGraph (chosen)** | First-class typed `State` object passed through nodes; reducers merge updates | Through the shared state graph; "peer-to-peer" is modeled as request/response entries in state, not direct calls | **Explicit** — nodes, conditional edges, cycles, recursion limit | Best fit for *negotiation rounds with a convergence gate*; production features (checkpointing, streaming, retries) |
| AutoGen | Conversation history shared | True multi-agent chat (group chat) | Conversation-driven, less deterministic | Good for free-form chat, harder to bound rounds |
| CrewAI | Task/role abstractions | Mostly orchestrator-mediated | Opaque internal loop | Fastest demo, least control |
| Raw provider SDK + tool use | You own a dict + the loop | Anything you build | Total control, more boilerplate | Most transparent; rejected in favor of LangGraph's built-in state/checkpointing for a production-leaning build |

**Key design consequence:** In LangGraph there is **no literal peer-to-peer
message bus** — agents coordinate by **reading and writing structured
`negotiation_requests` in the shared `SongState`**. The "bass asks drums to leave
space" interaction is: bass agent appends a request addressed to `drums` → the
graph routes a revision pass to the drums node → drums reads the request and
patches its part. This is the idiomatic and *more debuggable* LangGraph pattern
(every message is persisted in state) and supports checkpointing/replay.

### 4. Why this is genuinely agentic (not a prompt chain)

1. **Reasoned instrumentation, not a lookup table.** The director *infers* the
   ensemble from the style description via an LLM call returning a structured
   `Arrangement` (instruments + roles + section plan). "Argentine cumbia" →
   güira, accordion, bass, congas — derived, not switched on a hardcoded genre map.
   Unknown/novel requests ("space-jazz polka") still produce a sensible ensemble.
2. **Feedback-driven iteration.** Each instrument part is revised in response to
   *other agents' requests and the evolving global state* over multiple rounds —
   output depends on peers, not just the original prompt.
3. **Dynamic structure.** The graph's working set (which instrument nodes exist,
   how many negotiation rounds run) is determined at runtime by the director's
   output and a convergence check — the topology adapts to the request.
4. **Goal-seeking with a stopping criterion.** Agents negotiate toward a
   musically coherent whole and *converge* (or are force-converged), rather than
   emitting one shot each. That loop + termination condition is the agentic core.

A pure chain would hardcode instruments, make one call per part, and never let
parts influence each other.

### 5. Inter-agent communication protocol

- **Mechanism:** a single shared `SongState` (the LangGraph state) holding the
  global plan, each instrument's part, and a `negotiation_requests` list.
- **A request** is a structured object an agent appends: who it's from, who it's
  for, what bar(s), the ask, and rationale (schema below). On its revision turn,
  the addressee reads pending requests targeting it and either *accepts* (patches
  its part, marks resolved) or *declines* (marks resolved with a reason).
- **Rounds & convergence (production-leaning):**
  - Run **up to 3 negotiation rounds** (configurable). Empirically, ensembles
    stabilize in 2–3; more rounds mostly thrash.
  - **Early exit** when a round produces **zero new requests** (fixed point).
  - **Force-convergence** at the cap: a final "arbiter" pass (director) resolves
    any still-open requests deterministically and freezes the score.
  - Guard with LangGraph's `recursion_limit` as a hard backstop.

### 6. LLM prompting strategy for a "musician agent"

- **System prompt structure (per instrument agent):**
  1. **Role & expertise** — "You are the bassist in a {genre} ensemble."
  2. **Hard musical constraints** — key, tempo, time signature, bar count,
     **this instrument's MIDI pitch range**, allowed note durations.
  3. **Genre/role idioms** — concise stylistic guidance for that instrument in
     that genre (from the director's arrangement notes).
  4. **Output contract** — must return the strict part schema (enforced via
     structured output / tool schema), nothing else.
  5. **Negotiation etiquette** — how to read others' requests and how to phrase
     its own (bar-indexed, specific, with rationale).
- **Context scoping (cost + focus):** give each agent the **global header**
  (key/tempo/meter/section map/roster) + **its own current part** + **pending
  requests addressed to it** + **compact summaries of peers' parts** (e.g.
  per-bar density/role), **not** every peer's full note list. This is both a
  quality and a token-cost decision.
- **Preventing musically invalid output (defense in depth):**
  1. **Structured output** — Pydantic/tool schema constrains shape (pitch as MIDI
     int, duration enum, bar index bounds).
  2. **Deterministic post-validation** — a `validators.py` checks every note:
     within instrument range, within key (or flagged as intentional chromaticism),
     durations sum correctly per bar, bar indices in range.
  3. **Repair loop** — on validation failure, return the specific errors to the
     agent for one bounded retry (don't silently drop notes).
  4. Keep tempo/meter/key **out of the agent's control** — they live in the
     immutable global header so agents can't contradict each other.

---

## Recommended Tech Stack

| Concern | Choice | Why |
|---|---|---|
| Orchestration | **LangGraph** | Typed shared state, cycles, conditional edges, checkpointing, streaming |
| LLM | **Free-tier provider (TBD)** via its LangChain integration — Gemini 2.5 Flash (`langchain-google-genai`), Groq Llama 3.3 (`langchain-groq`), or OpenRouter | No paid API; provider isolated behind `llm.py` |
| LLM model tier | Use the provider's **strong model for director/arbiter**, a **lighter/faster model for instrument passes** if the provider offers one | Cost/quota control on the many per-instrument calls |
| Structured output | **LangChain `.with_structured_output(PydanticModel)`** | Schema-enforced agent I/O (supported by Gemini; for providers without native support, fall back to JSON-mode + Pydantic parse) |
| Reasoning depth | Where supported (e.g. Gemini "thinking"), enable deeper reasoning on director/arbiter and keep instrument passes light | Quality where it matters, quota where it doesn't |
| Data model | **Pydantic v2** | Canonical `SongState` + parts; validation |
| Music theory + notation | **music21** | JSON → Score → MusicXML → MuseScore/LilyPond render |
| MIDI export | **pretty_midi** | Clean JSON → multitrack `.mid` |
| Notation render backend | **MuseScore** (preferred) or **LilyPond** | High-quality engraving from MusicXML |
| Config | **pydantic-settings / .env** | API keys, provider/model names, round caps |
| Backend API | **FastAPI** (wraps the LangGraph pipeline) | Exposes `POST /compose` with **SSE streaming** of negotiation events; serves artifacts |
| Frontend | **Next.js (App Router) + React + TypeScript**, deployed to **Vercel** | Style prompt UI, live negotiation feed, score viewer, MIDI player; preview URL per PR |
| In-browser score render | **OpenSheetMusicDisplay** (or VexFlow) | Renders MusicXML client-side — keeps the heavy MuseScore binary off the request path |
| In-browser playback | **Tone.js** / **html-midi-player** | Plays `song.mid` in the browser without a server round-trip |
| Backend hosting | **Render / Railway / Fly.io / HF Spaces** (container) | Long-running agent loop + native MuseScore/LilyPond binaries — **not** Vercel Functions (see Frontend & Deployment) |
| Artifact storage | **Vercel Blob** or S3-compatible | Stores `song.mid` / MusicXML / PDF; UI fetches by URL |
| Tests | **pytest** (backend) + **Vitest/Playwright** (frontend, optional) | Validators + converters deterministic; UI smoke tests optional |

**Quota/cost note:** free tiers are rate-limited (e.g. Gemini ~1,500 req/day, 10
RPM; Groq ~1,000 req/day). Keep the negotiation round cap low, send **compact peer
summaries** (not full note lists), and cache/reuse the stable global header in the
prompt so repeated rounds stay cheap. If the chosen provider supports prompt
caching, mark the stable header/system prompts cacheable and put volatile content
(current part, pending requests) after the cached prefix.

---

## JSON Schema — shared song state & instrument parts

Canonical model (Pydantic; serialized to JSON as the LangGraph state). Pitches are
**MIDI note numbers** (0–127); durations are **beats** (float) to stay
meter-agnostic and MIDI-friendly.

```jsonc
// SongState — the single source of truth, passed through the graph
{
  "request": "Bee Gees-style disco, upbeat",
  "header": {                         // IMMUTABLE after director sets it
    "genre": "disco",
    "key": "F# minor",
    "tempo_bpm": 116,
    "time_signature": [4, 4],
    "num_bars": 32,
    "sections": [                     // section map (form)
      {"name": "intro",  "start_bar": 0,  "end_bar": 4},
      {"name": "verse",  "start_bar": 4,  "end_bar": 12},
      {"name": "chorus", "start_bar": 12, "end_bar": 20},
      {"name": "bridge", "start_bar": 20, "end_bar": 24},
      {"name": "chorus", "start_bar": 24, "end_bar": 32}
    ],
    "chord_progression": [            // optional shared harmonic grid, per bar
      {"bar": 0, "chord": "F#m"}, {"bar": 1, "chord": "D"}
      // ...
    ]
  },
  "roster": [                         // director's reasoned instrumentation
    {
      "id": "bass",
      "instrument": "electric_bass",
      "midi_program": 33,             // General MIDI program
      "midi_range": [28, 55],         // [low, high] MIDI note bounds
      "role": "drives the groove; syncopated octave disco line",
      "is_drum": false
    },
    { "id": "drums", "instrument": "drum_kit", "midi_program": 0,
      "midi_range": [35, 81], "role": "four-on-the-floor", "is_drum": true }
    // guitar, strings, etc.
  ],
  "parts": {                          // keyed by roster id — agents write here
    "bass": {
      "instrument_id": "bass",
      "version": 2,
      "notes": [
        // pitch=MIDI int (null for rest), start=absolute beat, dur=beats, vel=0-127
        {"bar": 4, "start_beat": 0.0, "pitch": 42, "dur": 0.5, "velocity": 100},
        {"bar": 4, "start_beat": 0.5, "pitch": null, "dur": 0.5, "velocity": 0}
      ],
      "notes_summary": "verse: octave-pop on root, rest on beat 1 of bar 5",
      "self_notes": "left bar 5 beat 1 open per drums fill request"
    }
  },
  "negotiation_requests": [           // the inter-agent message bus
    {
      "id": "req_001",
      "from": "drums",
      "to": "bass",                   // or "all"
      "round": 1,
      "bars": [5],
      "request": "leave beat 1 of bar 5 open for a tom fill",
      "rationale": "sets up the chorus lift",
      "status": "resolved",           // pending | resolved | declined
      "resolution": "accepted; bass rests bar 5 beat 1"
    }
  ],
  "round": 2,                          // current negotiation round
  "converged": false,
  "errors": []                         // validation errors fed back for repair
}
```

Notes on schema choices:
- **`header` is immutable** post-director — prevents agents contradicting tempo/key/meter.
- **`parts[*].notes`** uses absolute `bar` + `start_beat` so converters and
  validators are simple; `is_drum` routes to MIDI channel 10.
- **`notes_summary`** is the compact peer-context other agents receive (token saver).
- **`negotiation_requests`** is the protocol from research §5; `status`+`resolution`
  make convergence observable and replayable.
- LangGraph **reducers**: `parts` merged per-key, `negotiation_requests` appended,
  `header`/`roster` write-once.

---

## Architecture (text diagram)

```
                          ┌──────────────────────────────┐
   user style request ───▶│        DIRECTOR NODE         │
                          │  (strong free-tier model)    │
                          │  reasons → Arrangement:      │
                          │  key/tempo/meter/sections/   │
                          │  chord grid + instrument     │
                          │  roster (NOT hardcoded)      │
                          └───────────────┬──────────────┘
                                          │ writes header + roster
                                          ▼
                          ┌──────────────────────────────┐
                          │      SHARED SongState         │◀───────────┐
                          │  header | roster | parts |    │            │
                          │  negotiation_requests | round │            │
                          └───────────────┬──────────────┘            │
                       fan-out (one node per roster instrument)        │
            ┌───────────────┬─────────────┴──────────────┐            │
            ▼               ▼                             ▼            │
     ┌────────────┐  ┌────────────┐               ┌────────────┐      │
     │ BASS AGENT │  │ DRUMS AGENT│   ...          │GUITAR AGENT│      │
     │ compose /  │  │ compose /  │                │ compose /  │      │
     │ revise part│  │ revise part│                │ revise part│      │
     └──────┬─────┘  └──────┬─────┘               └──────┬─────┘      │
            │ structured part + new negotiation_requests │             │
            └───────────────┬──────────────┬─────────────┘             │
                            ▼              ▼                            │
                  ┌────────────────┐ ┌────────────────┐                │
                  │  VALIDATOR     │ │  CONVERGENCE    │                │
                  │ (music21:      │ │  CHECK          │── new reqs? ───┘
                  │  range/key/    │ │ round<cap AND   │   (next round)
                  │  duration)     │ │ reqs pending?   │
                  │ errors→repair  │ └───────┬─────────┘
                  └────────────────┘         │ converged / cap hit
                                             ▼
                                  ┌────────────────────┐
                                  │   ARBITER NODE      │
                                  │ (strong model)      │
                                  │ resolve open reqs,  │
                                  │ freeze score        │
                                  └─────────┬───────────┘
                                            ▼
                       ┌──────────────────────────────────────┐
                       │           RENDER NODE                 │
                       │  JSON ──music21──▶ Score              │
                       │     ├─▶ MusicXML ─▶ MuseScore (sheet) │
                       │     └─▶ pretty_midi ─▶ song.mid       │
                       └──────────────────────────────────────┘
```

LangGraph edges: `director → (fan-out) instrument nodes → validator → convergence
check`; convergence check has a **conditional edge** back to the instrument nodes
(another round) or forward to `arbiter → render`. `recursion_limit` backstops the cycle.

---

## Frontend & Deployment

A web UI lets a user type a style, watch the band negotiate **live**, then view the
score and play the result. The project is a **monorepo**: a **Next.js** frontend on
**Vercel** and the existing **Python** pipeline behind a thin **FastAPI** service.

### Why the Python backend does *not* go "directly to Vercel"

Vercel is the right home for the Next.js frontend, but the composition pipeline
cannot run as a Vercel Function as designed — three hard blockers:

1. **Native render binaries.** `music21`'s sheet-music render path shells out to
   **MuseScore/LilyPond** (system packages installed via `apt`). Vercel Functions
   have a **read-only filesystem** (only `/tmp` is writable, ~500 MB) and no way to
   install system binaries — the engraving step can't run there.
2. **Execution duration.** A multi-round negotiation with per-instrument LLM calls
   can run for minutes. Vercel Function limits (Fluid Compute): **~300 s on Hobby**,
   **800 s GA on Pro/Enterprise**, up to **1800 s (30 min) in beta** — workable on
   paid tiers but fragile, and we're optimizing for a *free* stack.
3. **Bundle size & no persistence.** `music21` + scientific deps push the Python
   function toward the bundle-size ceiling, and there's no persistent disk for
   generated `.mid`/`.pdf` artifacts (only ephemeral `/tmp`).

### Chosen topology

```
   Browser ──▶ Next.js (Vercel)  ──HTTPS/SSE──▶  FastAPI + LangGraph (container host)
     ▲            │  app/api proxy                   │  director → agents → arbiter
     │            ▼                                   ▼  music21 → pretty_midi / MuseScore
     └──── score (OSMD) + MIDI (Tone.js) ◀── artifact URLs ◀── Vercel Blob / S3
```

- **Frontend — Vercel (Next.js App Router).** Style-prompt form, a live
  **negotiation feed** (rendered from the SSE event stream), a **roster view**, an
  in-browser **score viewer** (OpenSheetMusicDisplay renders MusicXML client-side),
  and a **MIDI player** (Tone.js / html-midi-player). Push-to-deploy with a
  **preview URL per PR**. A Next.js Route Handler (`app/api/compose`) proxies to the
  backend so the browser never holds the backend URL/secret directly.
- **Backend — container host (Render / Railway / Fly.io / Hugging Face Spaces).**
  Runs FastAPI wrapping `build_graph()`. `POST /compose` kicks off a run and
  **streams LangGraph node events over SSE** (director done → roster; each agent
  pass → negotiation feed; convergence → done). MuseScore/LilyPond are installed in
  the container image, so server-side PDF engraving works when needed.
- **Artifacts — object storage (Vercel Blob or S3-compatible).** The backend writes
  `song.mid` / `song.musicxml` / `song.pdf` and returns URLs; the UI fetches them.
- **"More Vercel-native" fallback.** Because the score renders (OSMD/VexFlow) and
  MIDI plays (Tone.js) **in the browser**, MuseScore is only needed for downloadable
  PDFs. If we ever drop server-side PDF, the backend's only native dependency goes
  away — but the duration/quota constraints still favor a separate backend over
  Vercel Functions.

---

## Suggested project structure

Monorepo: `apps/api/` is the Python pipeline + FastAPI service; `apps/web/` is the
Next.js frontend that deploys to Vercel. They share the `SongState` contract (the
TypeScript types in `web` mirror the Pydantic schema).

```
multiagent-band/
  README.md
  PRD.md
  apps/
    api/                            # Python backend (LangGraph pipeline + FastAPI)
      pyproject.toml
      .env.example                  # LLM_PROVIDER, <PROVIDER>_API_KEY, MODEL_DIRECTOR, MODEL_INSTRUMENT, MAX_ROUNDS
      Dockerfile                    # installs MuseScore/LilyPond — for the container host
      llm_band/
        __init__.py
        config.py                   # pydantic-settings: models, round caps, render backend
        schema.py                   # Pydantic: SongState, Header, RosterItem, Part, Note, NegotiationRequest
        state.py                    # LangGraph State typing + reducers
        graph.py                    # build_graph(): nodes, edges, conditional convergence edge
        agents/
          __init__.py
          director.py               # arrangement reasoning → header + roster
          instrument.py             # generic musician node (parametrized by roster id)
          arbiter.py                # force-convergence / final resolution
          prompts.py                # system-prompt templates (role/constraints/etiquette)
        music/
          validators.py             # music21-based range/key/duration/bar checks → errors
          to_music21.py             # SongState → music21.stream.Score
          render_midi.py            # SongState/Score → pretty_midi → .mid
          render_sheet.py           # Score → MusicXML → MuseScore/LilyPond render
          theory.py                 # helpers: GM programs, ranges, key membership, chord tones
        llm.py                      # provider-agnostic chat-model factory (Gemini/Groq/OpenRouter) + structured output
        api.py                      # FastAPI: POST /compose (SSE event stream), artifact endpoints
        cli.py                      # `llm-band "slow blues"` → outputs/song.mid + song.pdf
      outputs/                      # generated .mid / .musicxml / .pdf (gitignored; prod → object storage)
      tests/
        test_schema.py
        test_validators.py          # notes out of range, bad durations, bar overflow
        test_to_music21.py
        test_render_midi.py         # JSON fixture → valid .mid round-trip
        test_convergence.py         # zero-new-requests early exit; cap force-convergence
        fixtures/
          sample_songstate.json
    web/                            # Next.js frontend (App Router) — deploys to Vercel
      package.json
      next.config.ts
      tsconfig.json
      .env.local.example            # NEXT_PUBLIC_API_BASE_URL → FastAPI backend
      app/
        layout.tsx
        page.tsx                    # style-prompt entry → start a composition
        compose/[jobId]/page.tsx    # live negotiation view (consumes SSE stream)
        api/compose/route.ts        # Route Handler: proxies to backend, relays SSE
      components/
        StyleForm.tsx               # genre/style prompt input
        RosterView.tsx              # director's reasoned instrumentation
        NegotiationFeed.tsx         # live timeline of negotiation_requests
        ScoreViewer.tsx             # renders MusicXML via OpenSheetMusicDisplay
        MidiPlayer.tsx              # plays song.mid via Tone.js / html-midi-player
      lib/
        api.ts                      # typed client for the FastAPI backend
        types.ts                    # TS mirror of SongState (kept in sync with schema.py)
  vercel.json                       # Vercel project config (root dir = apps/web)
```

---

## Gotchas & failure modes to watch

1. **Schema drift between agents and converters.** One Pydantic schema is the
   contract; converters/validators import it. Don't let prompts describe a
   different shape than the code enforces.
2. **Time math is the #1 bug source.** Per-bar beat sums must equal the meter
   (e.g. 4.0 beats in 4/4). Validate and repair; a single wrong duration cascades
   the whole track. Decide a single convention (absolute `bar`+`start_beat`) and
   never mix it with delta-time.
3. **Drums vs pitched instruments.** Drums use GM channel 10 and percussion key
   map, not pitch ranges — `is_drum` must route differently in MIDI export and be
   exempt from key-membership validation.
4. **Instrument range hallucination.** LLMs cheerfully write notes below a bass's
   open string or above a guitar's neck. Enforce `midi_range` in validation, not
   just in the prompt.
5. **Negotiation non-termination / thrashing.** Agent A asks B to change, B's
   change makes A want to revert. Mitigate with the round cap + zero-new-requests
   early exit + arbiter freeze + `recursion_limit`. Track request IDs to detect
   ping-pong.
6. **Token cost blowup.** Naively sending every full part to every agent each
   round is O(instruments² × rounds × notes). Use `notes_summary` peer context +
   reuse/caching of the stable header/system prompts + a lighter model for
   instrument passes — and keep within the free tier's RPM/daily caps.
7. **"Peer-to-peer" expectation mismatch.** LangGraph has no direct agent-to-agent
   call; it's all via shared state. Design and explain the negotiation as
   request objects in state, or reviewers will expect a message bus that isn't there.
8. **Notation rendering depends on an external binary.** MuseScore/LilyPond must be
   installed and discoverable by music21 (`music21.environment`). Detect and fail
   with a clear message; keep MIDI export working even if notation render is
   unavailable.
9. **MusicXML quantization.** Float beat durations that aren't clean subdivisions
   (e.g. 0.333…) render as ugly tuplets or fail. Quantize to an allowed duration
   grid before notation export.
10. **Structured-output edge cases.** Empty parts, all-rest bars, or a model
    returning prose alongside JSON. Enforce via `.with_structured_output` and treat
    parse failure as a validation error → bounded repair, never a crash.
11. **Director under-/over-instrumenting.** Constrain the roster to a sane size
    (e.g. 3–8) so a single request doesn't spawn 20 agents; cap in the director schema.
12. **Don't deploy the Python pipeline as a Vercel Function.** Native MuseScore/
    LilyPond binaries, multi-minute run times, bundle-size limits, and the read-only
    filesystem all break there — host the backend in a container (see Frontend &
    Deployment). Vercel hosts only the Next.js frontend.
13. **SSE through the Vercel proxy + CORS.** The `app/api/compose` Route Handler must
    stream the backend's Server-Sent Events without buffering (no full-response
    buffering / disabled response caching), and the backend must allow the frontend's
    origin. Keep the proxy a pass-through so the live negotiation feed stays real-time.
14. **Keep `lib/types.ts` in sync with `schema.py`.** The frontend mirrors
    `SongState`; drift between the Pydantic schema and the TS types silently breaks
    the UI. Prefer generating the TS types from the JSON schema in CI.

---

## Verification (how to test end-to-end)

1. **Unit (deterministic core):** `pytest` over `validators.py`, `to_music21.py`,
   `render_midi.py` using `fixtures/sample_songstate.json` — assert out-of-range
   notes and bad bar sums are caught, and a fixture state produces a valid,
   re-parseable `.mid` (round-trip with pretty_midi/music21).
2. **Convergence logic:** unit-test the convergence node — (a) a round with zero
   new requests exits early; (b) hitting the round cap routes to the arbiter and
   freezes. Mock the LLM nodes so this is deterministic.
3. **Integration (live, small):** run `llm-band "slow blues"` with a low round cap;
   assert a roster was produced, all parts pass validation, and `outputs/song.mid`
   + `outputs/song.(pdf|musicxml)` exist.
4. **Musical sanity (manual):** open the MIDI in any player and the sheet in
   MuseScore — confirm tempo/key/meter match the header, drums on channel 10,
   each instrument within range, and that at least one negotiation request shows a
   visible accommodation (e.g. the requested rest is present).
5. **Cost/observability:** log per-node token usage and request counts; confirm a
   full run stays within the chosen free tier's daily/RPM limits (and that prompt
   caching, if the provider supports it, is hitting on the stable header).
6. **Adversarial prompts:** feed a novel style ("space-jazz polka") and confirm the
   director still yields a coherent roster and the pipeline completes — evidence of
   the agentic, non-hardcoded behavior.
7. **End-to-end web flow:** with the backend running, submit a style in the Next.js
   UI and assert the **SSE stream** drives the live negotiation feed (roster appears,
   requests scroll in, convergence fires), the **score viewer** renders the MusicXML,
   and the **MIDI player** plays `song.mid`. Verify a **Vercel preview deploy** of
   `apps/web` builds and points at the backend via `NEXT_PUBLIC_API_BASE_URL`.
