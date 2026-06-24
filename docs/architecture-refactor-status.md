# Architecture Refactor Status

## Done

- Reorganized the backend into clean architecture layers:
  `domain`, `application`, `ports`, `infrastructure`, and `interfaces`.
- Moved `SongState` models into `domain/song_state.py` and future listening
  models into `domain/audio_profile.py`.
- Moved composition orchestration into `application/compose_song.py` and future
  reference use cases into `application/analyze_reference.py` and
  `application/answer_music_question.py`.
- Added explicit ports for LLMs, artifact storage, audio analysis,
  transcription, and stem separation.
- Moved FastAPI and SSE models into `interfaces/`; `llm_band.api:app` remains a
  compatibility entrypoint only.
- Added local storage plus MIR/Gemini/S3 placeholders under `infrastructure/`
  without implementing listening or adding new provider dependencies.
- Added architecture tests for dependency direction and removal of legacy root
  modules such as `schema.py`, `api_models.py`, `composition.py`, and the old
  `reference_analysis/` package.

## Not Done

- No listening to songs.
- No YouTube download, conversion, search, or real resolution.
- No Gemini audio integration.
- No MIR analysis with librosa, Essentia, Basic Pitch, or Demucs.
- No listening UI.
- No connection from `/compose` to reference analysis.
- No reference-guided composition.

## Next

- Add real reference source adapters behind the existing ports, starting with
  authorized uploads or local fixtures.
- Add MIR/audio profiling adapters that produce compact `ReferenceProfile` data
  with confidence values.
- Add an explainer adapter that answers questions from `ReferenceProfile`
  evidence, not raw provider internals.
- Add a separate API/UI flow for listening after the backend use cases are tested
  through ports and fake adapters.
- Add optional reference-guided composition by passing only compact
  `ReferenceProfile` summaries into the composition graph.
