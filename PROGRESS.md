# Daft Prompt progress

Last reviewed: 2026-07-09

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

Run a configured-provider composition benchmark that captures the new stage
timings and checks generated MIDI quality. This is required before deciding on
parallelism or declaring end-to-end composition responsiveness verified.

## Remaining milestones

1. Run a configured-provider composition benchmark and use its timing data to decide whether bounded parallelism is justified.
2. Evaluate optional, local-only style-card/groove providers only if they can improve an observed quality gap without becoming a required runtime dependency.
3. Exercise optional Basic Pitch and live Songsterr behavior when their respective runtimes/permissions are available.

## Completion audit (current evidence)

| Requirement area | Evidence | Status |
| --- | --- | --- |
| Chat-first local analysis and Q&A | FastAPI routes, bounded chat context, deterministic profile answers, 555 backend tests | Verified locally |
| Compact music rendering | Native tab, chord, melody, generated-song, mixer, MIDI, and score components; frontend build/test suite | Verified locally |
| Canonical editable MIDI and targeted revisions | `SongState`, renderer, mixer/export, targeted-revision tests | Verified locally |
| Multi-agent composition | Director/grouped instrument/negotiation/arbiter flow, stream timing, repair and quality tests | Verified structurally |
| Bilingual conversation | Spanish routing, answer and revision tests | Verified locally |
| Songsterr integration | Modular loader/store, normalized tab contracts and fixtures | Verified with fixtures; live availability remains external |
| Optional transcription | Basic Pitch adapter and graceful unavailable path tests | Verified at adapter/contract level; runtime model not installed here |
| Container runtime | Compose config, API image build, and no-build `/health` smoke | Verified locally |
| Real composition quality and latency | Requires a configured LLM provider and representative runs | Unverified: credentials/provider runtime unavailable in this session |

## Known technical debt and risks

- Optional Basic Pitch requires an extra dependency and model runtime; unavailable transcription is deliberately nonfatal.
- Deep audio analysis can be slow for long songs and stem separation is best-effort.
- Existing Pydantic/third-party deprecation warnings should be addressed separately from product work.
- The Docker image is necessarily large because local MIR depends on Torch/Demucs.
