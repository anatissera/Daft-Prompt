# LLMinem progress

Last reviewed: 2026-07-10

## Phase 2 — Product polish (active)

Evidence states used below: `pending`, `reproduced`, `root cause identified`,
`fixed`, `verified`, and `committed`. A regression is not complete until its
fix has been tested thoroughly, committed atomically, and a push has been
attempted.

### Priority 1 — Existing regressions

- [x] Browser playback: reproduce remote soundfont/load failures.
  - Status: fixed and verified.
  - Root cause/evidence: `TrackMixer` creates one `Tone.Sampler` per row and
    blocks playback on sparse melodic anchors or the complete GM percussion
    range from `https://gleitz.github.io/midi-js-soundfonts/FluidR3_GM/`.
    Rejected sample promises escape `togglePlayback`; there is no local voice
    or fallback, so one unavailable external host makes every sketch silent.
  - Fix/tests/benchmark/commit/push: playback now uses local Web Audio
    `Tone.PolySynth` voices and makes zero soundfont/sample network requests
    (previously 5 requests per melodic track and up to 47 for a drum track).
    Mixer behavior tests, the no-remote-playback architecture regression test,
    TypeScript, and a production Next.js build pass. Commit/push pending.
- [x] Score rendering: reproduce complete score-generation failures and verify
  that missing notation can currently interrupt the product flow.
  - Status: fixed and verified.
  - Root cause/evidence: backend `render_artifacts` renders MIDI and MusicXML
    as one all-or-nothing operation. The client always mounts `ScoreViewer`
    when parts exist; its dynamic import/fetch/parse/render promise has no HTTP
    status validation, catch path, or user-facing unavailable state.
  - Fix/tests/benchmark/commit/push: MIDI and MusicXML now render independently;
    a notation failure preserves MIDI. The score UI validates HTTP responses,
    catches import/fetch/parse/render errors, explains that playback/MIDI remain
    available, and offers retry. Converter/resilience tests, TypeScript, and the
    production frontend build pass. Commit/push pending.
- [x] Chat keyboard behavior: reproduce Enter not sending and establish the
  current Shift+Enter behavior.
  - Status: fixed and verified.
  - Root cause/evidence: after filling `keyboard regression probe`, Enter made
    the textarea value `keyboard regression probe\n`; Shift+Enter added another
    newline. `ChatComposer` has no `onKeyDown` submission behavior.
  - Fix/tests/commit/push: Enter now requests form submission, Shift+Enter keeps
    its native newline, and IME composition is protected. TypeScript and 12
    focused frontend tests pass. Commit/push pending.
- [x] Chat-first asset workflow: reproduce notation/tab/MIDI/preview rendering
  interrupting or blocking continued conversation.
  - Status: fixed and verified.
  - Root cause/evidence: the synchronous `/chat` route calls
    `render_artifacts` after composition and before returning `ChatResponse`.
    MIDI conversion and MusicXML engraving therefore extend the chat request's
    critical path; the UI remains globally busy until both finish.
  - Fix/tests/benchmark/commit/push: `/chat` now returns canonical `SongState`
    and artifact attachment URLs before a FastAPI background task renders files.
    Local playback and client-side MIDI export are immediately usable. On a
    canned sketch, synchronous artifact rendering took 32.446 ms while task
    scheduling took 0.016 ms. Focused API/architecture/stream tests pass.
    Commit/push pending.
- [ ] Research conversation continuity: reproduce follow-up questions losing
  freshly gathered song/artist/album evidence.
  - Status: reproduced; root cause identified.
  - Root cause/evidence: research profiles are saved and their id is returned,
    but follow-up reuse depends on `_REFERENCE_TOPIC_RE`. A natural request such
    as `What evidence did you find?` matches neither that regex nor composition,
    is classified as `clarify`, and is sent back through the LLM tool selector
    despite a current stored profile. This makes continuity probabilistic.
  - Fix/tests/benchmark/commit/push: pending.

### Later priorities (do not start before Priority 1 is verified)

- [ ] Priority 2: non-destructive incremental composition editing.
- [ ] Priority 3: genre-aware, purpose-driven minimal instrumentation.
- [ ] Priority 4: research-pipeline evaluation and benchmarked Giner comparison.
- [ ] Full Phase 2 completion audit.

## Developer-experience phase

- The default Docker stack was rebuilt from an environment with no root `.env`.
  `/health` and the web page started, but the first chat turn initially failed
  because Compose represented an unset `LLM_PROVIDER` as an empty string.
- `Settings` now treats a blank provider as the documented no-provider mode.
  This keeps default chat available while composition requests return the
  existing explicit configuration guidance.
- Local audio analysis is now an explicit runtime capability rather than a
  default dependency. The normal image keeps the Vertex AI Gemini adapter,
  while the large PyTorch/Demucs/MIR Python and system stacks are installed
  only with `docker-compose.audio.yml`. Disabled uploads return actionable
  opt-in guidance and the chat UI hides the attachment control.
- The dependency installation layer is isolated from application source, so
  ordinary backend edits reuse the provider dependency layer during Docker
  rebuilds. The default image also avoids `ffmpeg` and a compiler toolchain.
- A single root `.env.example` now documents the optional provider values and
  Compose forwards the matching API-key variables. The README is a concise
  clone-to-chat guide with Vertex ADC as the preferred provider and explicit
  default, Vertex, audio, and combined runtime commands.
- A clean default image build and `docker compose up --force-recreate` smoke
  check passed. The direct API and browser proxy both return useful no-provider
  chat guidance; the disabled audio endpoint returns the documented 503 opt-in
  guidance. The validated default image is about 1.63 GB locally, down from the
  previous 2.57 GB audio-included image while retaining Vertex support.
- Songsterr/web research is now enabled in the standard runtime, matching the
  named-song chat flow. `ENABLE_WEB_RESEARCH=false` is the explicit offline
  mode; its capability-aware prompt and tool guard return setup guidance
  without making a request.

## Completed milestones

- Chat-first local audio analysis, evidence-grounded questions, reference-guided composition, bounded session context, and generated-song playback/mixing are in place.
- Songsterr research and tab rendering are modular, bounded, and enabled by
  default; local audio analysis remains an independent opt-in capability.
- Deep listening covers tempo, key, harmony, sections, stems, timbre, rhythm, dynamics, ensemble, and optional bounded melody transcription.
- Chord charts, Songsterr tabs, and provisional melody previews render natively in chat.
- Generated MIDI remains canonical and independently editable per part; targeted generated-part revisions are supported.
- Spanish reference questions and reference-guided composition route through the same deterministic workflow as English.
- The local Docker API runtime builds and passes its `/health` smoke test without requiring machine-specific cloud credentials.
- Docker setup documentation now matches that self-contained runtime and explains how to opt into a provider through an uncommitted `.env` file.
- LLM sampling is provider-agnostic and role-specific: director/reviewer defaults favor stable planning, while instrument agents retain expressive variance. All three values are environment-configurable.
- Composition SSE events now include cumulative and per-stage elapsed time; artifact completion reports total elapsed time. This is the profiling baseline before any concurrency redesign.
- The compact negotiation detail now displays actual per-stage durations, keeping responsiveness visible without a dashboard-first workflow.
- Bass/lead/solo/melody parts receive deterministic overlap validation, allowing the existing repair loop to reject physically implausible monophonic note collisions without restricting harmony tracks.
- The default Gemini-to-OpenRouter provider fallback is now installable in the standard backend runtime, matching its default configuration instead of failing only after a Gemini outage or quota event.
- Vertex AI Gemini is verified against a real project through Application Default Credentials; no API key is required or stored by the repository.
- The director now explicitly batches independent rhythm instruments together, retaining dependency-ordered composition while avoiding needless one-instrument waves.
- Streamed agent passes carry their director-defined composition-group name, and the compact negotiation feed displays it beside round duration for dependency-aware latency diagnosis.
- An opt-in `docker-compose.vertex.yml` mounts existing host ADC read-only and requires an explicit project id, so the local Docker stack can use Vertex AI without committing credentials; its resolved configuration and `/health` startup were verified locally.
- Pydantic's protected-namespace configuration now preserves the existing `MODEL_*` environment contract without emitting distracting startup warnings.
- Comparable live Vertex graph benchmarks are recorded: a short funk sketch streamed its director plan at 8.6s and completed at 21.0s; an 8-bar, four-part sketch streamed its plan at the same stage, completed at 23.0s with no errors, and reached 0.858 overall harmonic fit. The small latency increase does not justify a graph-concurrency redesign.
- The live, bounded Songsterr research path was exercised against a public song query and returned 17 evidence records from one reachable source; the connector remains modular and preserves its existing graceful fallback behavior.

## Current architecture

```text
Next.js chat UI
  -> FastAPI routes/SSE
  -> application use cases and ChatMusic
  -> compact domain models (ReferenceProfile, CompositionBrief, SongState)
  -> ports
  -> MIR, storage, research, and LLM adapters

Composition: director -> grouped instrument agents -> structured negotiation -> arbiter -> MIDI/MusicXML/playback.
```

`SongState` is the canonical generated-music representation. Analysis is kept
separate from composition and supplies compact summaries only.

## giner branch review (2026-07-09)

`origin/giner` was fetched for review only; it was not merged.

| Area | Decision |
| --- | --- |
| Architecture | Keep current. `giner` adds a second `band_agent` pipeline beside the established clean composition flow, duplicating orchestration and HTTP behavior. |
| Composition | Keep current negotiation and bounded repair loop. `giner`'s skeleton-plus-parallel-fills concept is useful only as an optional future strategy because it loses peer negotiation and can silently leave tracks empty. |
| Style grounding | Do not import its web/Lakh corpus runtime: it is slow, requires large external data and web access, and conflicts with the local-first MVP. Retain the idea of compact, optional style guidance only. |
| Agent orchestration | Keep current LangGraph director/instrument/arbiter workflow, which is transparent and tested. |
| UI/player | Keep current lightweight Tone.js player and chat-first UI. `giner`'s SpessaSynth/MP3 path is richer but substantially heavier and needs a separate performance and browser-compatibility evaluation. |
| LLM reliability | Adapt only independently justified ideas: role-specific sampling for stable planning and bounded concurrency/timing if profiling proves it valuable. |
| Performance | Keep streamed, bounded groups and local fallbacks. Avoid `giner`'s web/corpus work on the interactive composition path. |
| Testability/maintainability | Keep current focused contracts and avoid raw MIDI/corpus code in runtime composition. |

## Current highest-priority task

Phase 2 Priority 1 regression reproduction. All five named regressions must be
reproduced before the first product-code fix.

## Remaining milestones

Complete Phase 2 priorities 1 through 4 in order, followed by a
requirement-by-requirement completion audit.

## Completion audit (current evidence)

| Requirement area | Evidence | Status |
| --- | --- | --- |
| Chat-first local analysis and Q&A | FastAPI routes, bounded chat context, deterministic profile answers, 555 backend tests | Verified locally |
| Compact music rendering | Native tab, chord, melody, generated-song, mixer, MIDI, and score components; frontend build/test suite | Verified locally |
| Canonical editable MIDI and targeted revisions | `SongState`, renderer, mixer/export, targeted-revision tests | Verified locally |
| Multi-agent composition | Director/grouped instrument/negotiation/arbiter flow, stream timing, repair and quality tests | Verified structurally |
| Bilingual conversation | Spanish routing, answer and revision tests | Verified locally |
| Songsterr integration | Modular loader/store, normalized tab contracts and fixtures; bounded live connector probe returned 17 evidence records from one source | Verified locally and against a reachable live source; external availability still varies by source/query |
| Optional transcription | Basic Pitch adapter and graceful unavailable path tests | Verified at adapter/contract level; runtime model not installed here |
| Container runtime | Compose config, API image build, and no-build `/health` smoke | Verified locally |
| Real composition quality and latency | Vertex AI Gemini (`daft-promt`, ADC) benchmarked a short funk graph at 21.0s (director 8.6s) and an 8-bar four-part graph at 23.0s, with no errors and 0.858 overall harmonic fit | Verified for comparable paid-Vertex runs; retain the current grouped LangGraph orchestration because no graph-level bottleneck was observed |

## Known technical debt and risks

- Optional Basic Pitch requires an extra dependency and model runtime; unavailable transcription is deliberately nonfatal.
- Deep audio analysis can be slow for long songs and stem separation is best-effort.
- Existing Pydantic/third-party deprecation warnings should be addressed separately from product work.
- The default image excludes the local MIR stack; audio-enabled images remain
  intentionally heavier because they include Torch, Demucs, `ffmpeg`, and
  native build tools.
- Short Vertex results are encouraging but are not a full latency SLO: real performance varies with arrangement size, group dependencies, and Vertex service latency. Preserve the current bounded negotiation unless a future benchmark shows a graph-level bottleneck.
