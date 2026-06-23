# Plan: Multi-agent Band

> Source PRD: [`PRD.md`](../PRD.md) — multi-agent LLM music composition system.

## How to work this plan

- **Branch per phase**, always cut from `develop`:
  `git switch develop && git pull && git switch -c feat/<phase>`
- **`main` is protected** (PR-only, no direct push, no force-push, no deletion).
  Integrate via PR into `develop`; cut a release PR `develop → main` at milestones.
- Each phase is a **vertical slice**: it cuts through every layer it touches and is
  demoable/verifiable on its own. Prefer merging a thin working slice over a thick
  unfinished one.
- Open a PR into `develop` per phase; squash or merge as you like. Tick the
  acceptance criteria in the PR description.

## Architectural decisions

Durable decisions that apply across all phases:

- **Monorepo**: `apps/api` (Python: LangGraph + FastAPI + music21 + pretty_midi) and
  `apps/web` (Next.js App Router + React + TypeScript, deploys to Vercel).
- **Shared contract**: `SongState` is the single source of truth. Pydantic in
  `apps/api/llm_band/schema.py`; mirrored as TypeScript in `apps/web/lib/types.ts`
  (keep in sync; prefer generating TS from the JSON schema in CI).
- **API surface**: `POST /compose` starts a run and **streams Server-Sent Events**
  (director done → roster; each agent pass → negotiation feed; convergence → done).
  Artifact endpoints serve/redirect to `song.mid` / `song.musicxml` / `song.pdf`.
- **Music conventions**: pitches are MIDI ints (0–127, `null` = rest); durations in
  beats (float); notes use absolute `bar` + `start_beat`. `header`
  (key/tempo/meter/sections) is **immutable** after the director sets it.
- **LLM provider**: free-tier, isolated behind `apps/api/llm_band/llm.py`. Pick is
  TBD among Gemini (`langchain-google-genai`), Groq (`langchain-groq`), OpenRouter.
- **Deployment split**: `apps/web` on Vercel; `apps/api` on a container host
  (Render / Railway / Fly.io / HF Spaces) because of native MuseScore/LilyPond
  binaries, multi-minute runs, bundle-size and read-only-FS limits. Artifacts go to
  object storage (Vercel Blob or S3-compatible).
- **Rendering**: score renders in the browser (OpenSheetMusicDisplay/VexFlow), MIDI
  plays in the browser (Tone.js / html-midi-player); MuseScore is server-side only
  for downloadable PDF.

---

## Phase 1: Walking skeleton (tracer bullet)

**Branch**: `feat/tracer-skeleton`
**User stories**: US1 (describe a style → get a song), US4 (play + view in browser)

### What to build

The thinnest end-to-end path with **no LLM**. A hardcoded/trivial `SongState` is
rendered to `song.mid` + `song.musicxml` by the deterministic core. `POST /compose`
returns this canned result. A minimal Next.js page submits a style string, then
plays the MIDI (Tone.js) and renders the score (OSMD). Proves web → api → render →
artifact → browser playback/score works before any agent exists.

### Acceptance criteria

- [ ] `apps/api` runs FastAPI locally; `POST /compose` returns a valid canned `SongState` + artifact URLs.
- [ ] A fixture `SongState` renders to a re-parseable `.mid` and a valid `.musicxml`.
- [ ] `apps/web` page submits a style, plays the returned MIDI, and renders the score.
- [ ] `apps/web/lib/types.ts` defines `SongState` matching the Pydantic model.
- [ ] README/PRD repo structure matches what actually exists for these two apps.

---

## Phase 2: Deterministic core

**Branch**: `feat/core-schema-render`
**User stories**: US1

### What to build

Harden the Python core with **no LLM**: full `schema.py`, `validators.py`
(range/key/duration/bar checks → structured errors), `to_music21.py`,
`render_midi.py`, `render_sheet.py`, and `theory.py` helpers. Unit-tested against a
fixtures `SongState`. This is the trustworthy foundation every agent writes into.

### Acceptance criteria

- [ ] `pytest` covers validators (out-of-range notes, bad bar sums, drums exempt from key check) and converters.
- [ ] Fixture `SongState` → valid round-trippable `.mid` (pretty_midi/music21) in tests.
- [ ] MusicXML quantization handles non-grid float durations without crashing.
- [ ] Drums route to GM channel 10; pitched instruments validated against `midi_range`.
- [ ] `render_sheet` degrades gracefully when MuseScore/LilyPond is absent (MIDI still works).

---

## Phase 3: Director agent

**Branch**: `feat/director`
**User stories**: US2 (see the reasoned instrumentation)

### What to build

Introduce `llm.py` (one free-tier provider wired via its LangChain integration) and
the director node: from a style string it reasons a structured `Arrangement` →
`header` + `roster` (3–8 instruments, not a hardcoded genre map). `POST /compose`
now runs the director; parts remain empty/stubbed. UI shows the roster.

### Acceptance criteria

- [ ] `.env.example` documents `LLM_PROVIDER` + `<PROVIDER>_API_KEY`; key read from env, never committed.
- [ ] Director returns a schema-valid `header` + `roster` via structured output.
- [ ] Roster size is capped (3–8); novel styles ("space-jazz polka") still yield a coherent roster.
- [ ] `RosterView` in the UI lists instruments + roles from a live `/compose` call.
- [ ] `header` is immutable downstream (enforced in state reducers).

---

## Phase 4: Instrument agents (one-shot)

**Branch**: `feat/instrument-agents`
**User stories**: US1

### What to build

Fan-out one generic instrument node per roster entry. Each composes its part **once**
from the header + its role + compact peer summaries, constrained by structured output
and the immutable header. Deterministic post-validation with a **bounded repair loop**
on failure. `song.mid` now reflects real composition. No negotiation yet.

### Acceptance criteria

- [ ] LangGraph graph fans out to one node per instrument and merges parts via reducers.
- [ ] Each part passes validation (or is repaired within the bounded retry); failures never crash the run.
- [ ] Generated `song.mid` plays a coherent multi-instrument arrangement for a test style.
- [ ] Peer context uses `notes_summary`, not full note lists (token cost).
- [ ] `test_convergence`-style scaffolding mocks the LLM so graph logic is deterministic in tests.

---

## Phase 5: Negotiation + convergence

**Branch**: `feat/negotiation`
**User stories**: US3 (agents negotiate)

### What to build

The agentic core: agents append `negotiation_requests` (from/to/bars/ask/rationale);
addressees accept (patch + mark resolved) or decline (reason) on their revision turn.
Loop with **round cap**, **zero-new-requests early exit**, **arbiter** force-convergence
at the cap, and `recursion_limit` backstop. Request IDs tracked to detect ping-pong.

### Acceptance criteria

- [ ] Negotiation requests are created, routed, and resolved/declined through shared state.
- [ ] Round with zero new requests exits early; hitting the cap routes to the arbiter and freezes.
- [ ] A demo run shows at least one visible accommodation (e.g. requested rest is present in the output).
- [ ] No infinite loops; `recursion_limit` and round cap both verified in tests.

---

## Phase 6: SSE live UI

**Branch**: `feat/sse-live-ui`
**User stories**: US3, US4

### What to build

Stream LangGraph node events over SSE from `POST /compose`; the Next.js
`app/api/compose` Route Handler proxies the stream pass-through (no buffering, CORS
allowed). UI renders a live `NegotiationFeed`, `RosterView`, `ScoreViewer`, and
`MidiPlayer` that update as the run progresses, ending on the final artifacts.

### Acceptance criteria

- [ ] Backend emits SSE events for director/roster, each agent pass, and convergence/done.
- [ ] The Vercel Route Handler relays SSE in real time without buffering.
- [ ] UI shows the negotiation feed updating live, then the final score + MIDI player.
- [ ] CORS configured so the frontend origin can reach the backend.

---

## Phase 7: Deploy

**Branch**: `feat/deploy`
**User stories**: US6 (use it on a deployed URL)

### What to build

`apps/api/Dockerfile` installs MuseScore/LilyPond and runs FastAPI on a container
host. `apps/web` deploys to Vercel (`vercel.json`, root dir `apps/web`,
`NEXT_PUBLIC_API_BASE_URL` → backend). Artifacts written to object storage and served
by URL. PR preview deploys verified.

### Acceptance criteria

- [ ] Backend image builds and runs; server-side PDF engraving works in the container.
- [ ] `apps/web` deploys on Vercel and talks to the deployed backend via env var.
- [ ] Generated artifacts persist to object storage and load in the deployed UI.
- [ ] A Vercel **preview deploy** builds on PR and points at a reachable backend.

---

## Phase 8: Eval + observability

**Branch**: `feat/eval-observability`
**User stories**: US5 (stays within free-tier limits; observable)

### What to build

Per-node token/request logging; assert a full run stays within the chosen provider's
free daily/RPM caps. Adversarial-prompt suite confirming non-hardcoded behavior.
Optional caching of the stable header/system prompts if the provider supports it.

### Acceptance criteria

- [ ] Per-node token usage and request counts are logged for a full run.
- [ ] A standard run is measured against the free-tier limits and documented.
- [ ] Adversarial styles complete end-to-end with coherent rosters.
- [ ] (If supported) prompt caching hits on the stable header across rounds.
