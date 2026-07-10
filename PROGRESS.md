# LLMinem progress

Last reviewed: 2026-07-10

## Phase 2 — Product polish (active; Priority 1 reopened)

Evidence states used below: `pending`, `reproduced`, `root cause identified`,
`fixed`, `verified`, and `committed`. A regression is not complete until its
fix has been tested thoroughly, committed atomically, and a push has been
attempted.

### Priority 1 — Existing regressions

#### Additional chat regressions reported 2026-07-10

- [x] Intent-specific progress states: research currently displays composition
  stages. Reproduce research, composition, and iterative-edit workflows; replace
  misleading shared states; cover with regression and browser validation.
  - Reproduced: live browser showed `Director arranging the band`, instrument
    agents, arbiter, and MIDI/score rendering 10.5 s into `Research Adiós by
    Gustavo Cerati`.
  - Root cause: `/chat` starts every request as `Thinking…`; after nine seconds
    `ChatThread` reveals one hard-coded composition timeline with no workflow or
    intent state.
  - Fix/test/browser: client classifies research/composition/edit/answer workflow
    before starting work and renders distinct stage contracts. Pure regression
    tests pass. Browser validation at 0.5 s showed `Researching reference…` plus
    the five research stages and no composition wording. Committed as
    `efa82de`; push attempted and rejected non-fast-forward.
- [x] Visible tablature: reproduce research/generation → guitar-tab request,
  verify meaningful visible tab content, and surface rendering failures clearly.
  - Reproduced: research loaded three meaningful 89-measure guitar tracks for
    `Adiós`, but the follow-up returned prose and `tab_excerpt: null`.
  - Root cause: the deterministic reference-answer shortcut invokes
    `AnswerMusicQuestion`, bypassing `get_tab_excerpt`; generated `SongState`
    has no tab projection; UI failure handling only renders text and provides no
    explicit tab-unavailable attachment state.
  - Fix/test/browser: reference and generated-song tab requests now create a
    native excerpt attachment, skip leading rest-only windows, and preserve an
    explicit error attachment. Fresh Adiós research followed by guitar tab
    returned four visible measures with 37 playable string/fret events;
    unavailable piano tab rendered a friendly alert. Backend regressions, UI
    tests, and Playwright pass. Committed as `2b075ff`; push attempted and
    rejected non-fast-forward.
- [x] Respectful conversation auto-follow: reproduce missing scroll-to-latest,
  follow progress/completion near the bottom, preserve manual upward scrolling,
  resume near-bottom/send behavior, and validate fixed-composer offset in browser.
  - Reproduced/root cause: `ChatThread` has no scroll container/anchor refs,
    near-bottom state, scroll listener, or effect responding to message/progress
    growth. No code accounts for the fixed composer height.
  - Fix/test/browser: thread now follows atomic content-height changes only while
    near bottom, forces follow on a new user send, pauses after manual upward
    scrolling, and resumes near bottom/send. The composer remains outside the
    scroll viewport. Playwright populates an overflowing conversation, checks
    send/response completion, manual-scroll protection, resume, and composer
    clearance; 1 browser test passes. Committed as `f7e9310`; push attempted and
    rejected non-fast-forward.
- [x] Reliable famous-song lookup and entity resolution: reproduce `Adiós` by
  Gustavo Cerati and `I Kissed a Girl` by Katy Perry; support featured artists,
  collaborations, multiple primaries, remixes/live versions, aliases, accents,
  punctuation, translated/alternate titles, and provider fallbacks. Build and
  report a 30-50-track multi-decade benchmark.
  - Reproduced: live lookups took 31.78 s and 43.97 s. Each returned claims from
    Songsterr only while every other provider failed/was empty; generic search
    shell results were counted as `tab` evidence without verified identity.
  - Root cause: resolver only parses `title by artist`; there is no Unicode/
    accent normalization, collaboration/version model, scored entity matching,
    neutral metadata provider, query variants, cross-provider acceptance rule,
    or reusable researcher cache.
  - Fix/test/browser: structured entity resolution now models primary,
    featured, collaborating, producer, remix, version, and alternate-title
    credits. Normalized variants feed bounded parallel providers; MusicBrainz
    supplies conservatively scored metadata with retry, other research sources
    and Songsterr remain independent fallbacks, and profiles are cached. Live
    chat returned 18 claims for Adiós, 31 for I Kissed a Girl, and 54 for Uptown
    Funk. The 40-track benchmark measured 97.5% identification, 97.5% correct
    artist resolution, 90% featured-artist resolution, 97.5% usable evidence,
    2.608 s average latency, 5% fallback frequency, and 2.5% false matches;
    provider usage was MusicBrainz 38, Songsterr 1, Wikipedia 1. Committed as
    `cc441db`; push attempted and rejected non-fast-forward.

Prior completion audit gap: Priority 1 was marked complete from focused source
and unit evidence without browser-validating these full chat workflows. That
claim is withdrawn until all four items above have reproduction evidence, root
causes, fixes, regression tests, end-to-end browser validation, atomic commits,
and push attempts.

Priority 1 completion audit: verified again 2026-07-10 after reopening. Full
backend suite: 587 passed, 1 skipped. Full frontend suite: TypeScript clean, 64
tests passed, 2 Playwright browser tests passed, and the production Next.js
build completed. Each fix is committed locally and each push was attempted; all
pushes were rejected because the remote branch is ahead.

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
    TypeScript, and a production Next.js build pass. Committed as `b1e1f27`;
    push attempted and rejected non-fast-forward.
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
    production frontend build pass. Committed as `7192005`; push attempted and
    rejected non-fast-forward.
- [x] Chat keyboard behavior: reproduce Enter not sending and establish the
  current Shift+Enter behavior.
  - Status: fixed and verified.
  - Root cause/evidence: after filling `keyboard regression probe`, Enter made
    the textarea value `keyboard regression probe\n`; Shift+Enter added another
    newline. `ChatComposer` has no `onKeyDown` submission behavior.
  - Fix/tests/commit/push: Enter now requests form submission, Shift+Enter keeps
    its native newline, and IME composition is protected. TypeScript and 12
    focused frontend tests pass. Committed as `572fc25`; push attempted and
    rejected non-fast-forward.
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
    Committed as `7192005`; push attempted and rejected non-fast-forward.
- [x] Research conversation continuity: reproduce follow-up questions losing
  freshly gathered song/artist/album evidence.
  - Status: fixed and verified.
  - Root cause/evidence: research profiles are saved and their id is returned,
    but follow-up reuse depends on `_REFERENCE_TOPIC_RE`. A natural request such
    as `What evidence did you find?` matches neither that regex nor composition,
    is classified as `clarify`, and is sent back through the LLM tool selector
    despite a current stored profile. This makes continuity probabilistic.
  - Fix/tests/benchmark/commit/push: question-shaped follow-ups with a current
    reference now deterministically query the stored profile without another
    LLM routing call. Evidence/findings questions summarize the five strongest
    source-backed claims. A full research-then-follow-up regression test passes
    with an LLM stub that raises if invoked; 68 focused chat/query/answer tests
    pass. Committed as `e02208d`; push attempted and rejected non-fast-forward.

### Later priorities

### Priority 2 — Human iteration (complete)

Priority 2 completion audit: full backend suite 571 passed, 1 skipped; full
frontend suite 60 passed with clean TypeScript and production build.

- [x] Enforce non-destructive revision invariants at the application boundary.
  - Status: fixed and verified.
  - Root cause/evidence: `ComposeSong.revise_instrument` returns an adapter's
    complete candidate `SongState` without a merge/postcondition. A malformed or
    over-broad reviser can change header/harmony/roster and drop unrelated parts.
  - Fix/tests/benchmark/commit/push: application merge accepts only the named
    part and preserves header, request, roster, harmony, peer parts, negotiation
    history, and errors. A deliberately destructive fake reviser is contained.
    Merge-guard overhead averages 218.29 μs. Committed as `fd70d57`; push
    attempted and rejected non-fast-forward.
- [x] Make targeted sound/timbre edits change the named instrument only.
  - Status: fixed and verified.
  - Root cause/evidence: all current edits call the note-revision agent. Roster
    `instrument`, `midi_program`, and `playing_style` remain unchanged, so a
    request for a different sound cannot affect playback identity.
  - Fix/tests/benchmark/commit/push: explicit clean/acoustic/distorted/synth/piano
    requests update only the target roster entry; unspecified sound requests ask
    one clarification. Local playback maps program families to distinct local
    oscillator timbres. Committed as `fd70d57`; push attempted and rejected
    non-fast-forward.
- [x] Verify instrumentation, arrangement, harmony, rhythm, and musical identity
  preservation across repeated edits to the internal current composition.
  - Status: verified by repeated-edit sequence tests. Timbre persists into a
    later note edit; all unrequested notes, peer parts, header, original request,
    and roster state remain unchanged.

### Priority 3 — Genre-aware instrumentation (complete)

Priority 3 completion audit: 574 backend tests passed, 1 skipped.

- [x] Allow the smallest ensemble that can authentically satisfy the request.
  - Status: fixed and verified. The contract now permits 1-8 instruments,
    explicitly accepts solos/duos and silence, and directs the ensemble decision
    before agent selection.
  - Root cause/evidence: the director schema/prompt forces 3-8 instruments even
    for solo/duo music, making unnecessary roles structurally mandatory.
- [x] Reject unrequested electronic textures in acoustic/roots genres.
  - Status: fixed and verified. A narrow normalization guard removes synth/pad/
    electronic programs from the named roots genres unless explicitly requested,
    repairing composition groups at the same time. The grunge fixture falls from
    4 agents to 3 (25% less agent work) without losing an idiomatic role.
  - Root cause/evidence: grunge, punk, blues, folk, garage rock, and acoustic
    plans containing synth/pad/electronic roster items pass normalization.
- [x] Require a defined purpose and stylistic justification per instrument.
  - Status: fixed and verified. Schema fields reject empty purpose/style and the
    director prompt requires a distinct musical purpose and genre justification.
  - Root cause/evidence: role and playing-style fields were required keys but
    accepted empty strings; the prompt did not make ensemble choice a first step.

### Priority 4 — Research pipeline (complete)

Priority 4 completion audit: 577 backend tests passed, 1 skipped. Full rationale
and benchmark evidence: `docs/phase2-research-pipeline-evaluation.md`.

- [x] Inspect `origin/giner` without merging it.
  - Evidence: 83 changed files, +14,223/-635 lines; adds a parallel 666-line
    `band_agent` pipeline, 10-21 concurrent fill units, a required optional
    ~1.6 GB Lakh corpus, web excerpts, and deterministic fallbacks. Its manual
    evaluation results are unfilled; its handoff notes duplicate exemplars and
    mislabeled corpus genre/key rows.
- [x] Benchmark current and Giner approaches on latency, evidence, and runtime
  complexity; document the decision.
  - Result: current hybrid keeps zero-LLM research, two broad production
    candidates, four-worker bound, no corpus requirement, and one canonical
    composer. Giner has an 8-second excerpt ceiling, 10-21 concurrent fill units,
    ~1.6 GB optional corpus, and no completed quality results.
- [x] Add scope-aware artist/album/style/genre/era retrieval without replacing
  the source-backed song connector pipeline.
  - Result: explicit scope classifier preserves specialized song connectors and
    routes broad context through bounded provider-free candidates.
- [x] Verify broad research becomes reusable conversation evidence and remains
  bounded/offline-safe.
  - Result: production/timbre/instrument/groove sentences become knowledge claims;
    follow-up evidence queries pass. Four simulated 30 ms fetches finish under
    90 ms versus ~120 ms sequential. Existing offline guard remains upstream.

### Phase 2 completion audit

- [x] Priority 1: all five named regressions were reproduced before fixes;
  root causes, tests, benchmarks, atomic commits, and push attempts are recorded.
- [x] Priority 2: current-song edits are incremental and preserve all unrequested
  composition state across repeated edits.
- [x] Priority 3: ensemble selection is minimal, purpose-driven, and guarded
  against unrequested electronic textures in named roots genres.
- [x] Priority 4: Giner was inspected and benchmarked without merge; only bounded
  broad-context retrieval was integrated into the existing architecture.
- [x] Final verification: backend 577 passed/1 skipped; frontend TypeScript clean,
  60 tests passed, production build passed; repository search finds no remaining
  remote soundfont or legacy MIDI-player dependency.
- [x] Every implementation iteration is committed locally and a push was
  attempted. Pushes were rejected non-fast-forward because the remote branch is
  one commit ahead; per goal instructions, work continued locally without merge.

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

Phase 2 Priority 3: audit director ensemble selection and enforce genre-aware,
purpose-driven minimal instrumentation.

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
