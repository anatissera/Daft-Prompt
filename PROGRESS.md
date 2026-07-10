# Daft Prompt progress

Last reviewed: 2026-07-10

## Completed milestones

- Chat-first local audio analysis, evidence-grounded questions, reference-guided composition, bounded session context, and generated-song playback/mixing are in place.
- Songsterr research and tab rendering are modular and remain secondary to the local-audio MVP.
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

Completion audit is complete: the current implementation covers the project
objective with local and live evidence. Keep optional adapters as non-blocking
enhancements rather than expanding the MVP without an observed quality gap.

## Remaining milestones

No required milestones remain. Optional follow-up work is deliberately deferred
until it addresses an observed quality gap:

1. Evaluate local-only style-card/groove providers without making them a required runtime dependency.
2. Exercise the optional Basic Pitch model runtime where it is installed.

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
- The Docker image is necessarily large because local MIR depends on Torch/Demucs.
- Short Vertex results are encouraging but are not a full latency SLO: real performance varies with arrangement size, group dependencies, and Vertex service latency. Preserve the current bounded negotiation unless a future benchmark shows a graph-level bottleneck.
