# Phase 2 research-pipeline evaluation

Date: 2026-07-10

## Decision

Keep LLMinem's current connector/fusion architecture and add a bounded broad
research route for artist, album, production-style, genre, and era questions.
Do not merge `origin/giner`'s parallel `band_agent` or corpus runtime.

## Comparison

| Criterion | Current + Phase 2 hybrid | `origin/giner` | Decision |
| --- | --- | --- | --- |
| Song evidence | Four source-specific connectors, normalized claims, conflicts, missing-data records, Songsterr tab contract | General web titles/excerpts plus optional corpus | Keep current |
| Broad context | Scope classifier routes artist/album/style/genre/era queries to two bounded broad candidates; production sentences become reusable claims | Up to three fetched excerpts plus web-title genre inference | Adapt the bounded excerpt idea |
| Interactive research calls | Zero LLM calls; at most two broad fetch candidates, up to four workers | Web search, up to three page fetches, corpus retrieval, then composition calls | Keep current boundary |
| Composition calls | Existing director plus dependency-grouped instrument agents with negotiation | One skeleton plus 10-21 concurrent section/instrument fill units and deterministic fallbacks | Reject second pipeline |
| Local data | No database or corpus required | Optional Lakh download documented at about 1.6 GB plus indexes | Reject for local-first default |
| Evaluation evidence | 575+ automated backend tests; source-backed live connector probe recorded in `PROGRESS.md` | Manual eval document has no results; handoff records duplicated exemplars and mislabeled genre/key rows | Current evidence is stronger |
| Change surface | Extends existing researcher/parser/fuser boundary | 83 files, +14,223/-635 lines relative to the current branch | Avoid merge/rewrite |

## Benchmarks

The broad-research regression benchmark uses four deterministic 30 ms page
fetches. Bounded parallel digestion completes below 90 ms; sequential work would
take about 120 ms before parsing/fusion. Production uses only two candidate pages,
so its request count is smaller than the benchmark fixture.

The Giner design documents an 8 second excerpt wait ceiling and 10-21 concurrent
fill units for a five-to-seven-instrument, two-to-three-section composition. It
does not contain completed quality or latency results, so no quality improvement
can be claimed. Its corpus setup also adds a roughly 1.6 GB download. These are
architectural measurements from the branch source and its own evaluation plan,
not inferred production timings.

## Integrated improvements

- Research scope is classified as song, artist, album, style, genre, or era.
- Song queries retain specialized connectors and tab loading.
- Broader queries use provider-free, bounded candidates and parallel fetches.
- Generic pages extract tempo/key/chords plus production, timbre,
  instrumentation, and groove sentences.
- Broad claims are materialized as `SongKnowledgeProfile` evidence, so later
  chat questions reuse them through the same deterministic query tools.
- Offline mode still blocks research before any researcher is invoked.

## Rejected ideas

- A second composition graph beside the established director/instrument/arbiter
  graph.
- Runtime dependence on a large external MIDI corpus.
- Silent fallback fills that can hide failed instrument generation.
- High fan-out fill calls without evidence that they improve musical quality.
- Importing the 40 MB SF3 player as part of research work; Phase 2 playback now
  has a zero-network local baseline.
