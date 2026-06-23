# Architecture Refactor Status

## Done

- Split the FastAPI layer away from composition, rendering, artifact paths, and
  SSE serialization.
- Added a local artifact storage boundary that can later be replaced by object
  storage without changing composition.
- Added typed API/SSE contract models for the current `/compose` and
  `/compose/stream` payloads.
- Added `llm_band.reference_analysis` as a separate bounded context with domain
  models, ports, use cases, and fake adapters for tests.
- Added boundary tests proving reference analysis can run with fakes and that
  composition modules do not import reference-analysis internals.

## Not Done

- No listening to songs.
- No YouTube download, conversion, search, or real resolution.
- No Gemini audio integration.
- No MIR analysis with librosa, Essentia, Basic Pitch, or Demucs.
- No listening UI.
- No connection from `/compose` to reference analysis.

## Next

- Add real reference source adapters behind the existing ports, starting with
  authorized uploads or local fixtures.
- Add MIR/audio profiling adapters that produce compact `ReferenceProfile` data
  with confidence values.
- Add an explainer adapter that answers questions from `ReferenceProfile`
  evidence, not raw provider internals.
- Add a separate API/UI flow for listening after the backend use cases are tested
  with fakes.
- Add optional reference-guided composition by passing only compact
  `ReferenceProfile` summaries into the composition graph.
