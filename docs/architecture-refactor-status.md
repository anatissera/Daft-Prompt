# Architecture Refactor Status

This status reflects the current chat-musical MVP baseline on `develop`.
`PRODUCT.md` remains the product source of truth.

## Done

- Reorganized the backend into clean architecture layers:
  `domain`, `application`, `ports`, `infrastructure`, and `interfaces`.
- Moved `SongState` models into `domain/song_state.py` and reference/listening
  models into `domain/audio_profile.py`.
- Moved composition orchestration into `application/compose_song.py` and
  reference use cases into `application/analyze_reference.py` and
  `application/answer_music_question.py`.
- Added explicit ports for LLMs, artifact storage, audio analysis,
  transcription, and stem separation.
- Moved FastAPI and SSE models into `interfaces/`; `music_assistant.api:app` remains a
  compatibility entrypoint only.
- Added local storage plus MIR/Gemini/S3 placeholders under `infrastructure/`.
- Added a local librosa-based analyzer for uploaded files that returns compact
  `ReferenceProfile` data with tempo, key, energy, sections, probable chords,
  and confidence values.
- Added a `/references/analyze` FastAPI upload route and a Next.js proxy route.
- Added a chat-first frontend shell with local audio attachment, contextual
  reference analysis, and generated-song playback/mixer after composition.
- Added architecture tests for dependency direction and removal of legacy root
  modules such as `schema.py`, `api_models.py`, `composition.py`, and the old
  `reference_analysis/` package.

## Not Done

- No YouTube download, conversion, search, or real resolution.
- No Gemini audio integration.
- No connection from `/compose` to reference analysis.
- No reference-guided composition.
- No full conversational backend router yet; the frontend currently handles a
  small local reference Q&A helper while the planned chat use case is still
  pending.

## Next

- Improve the local MIR/audio profiling quality behind the existing
  `AudioAnalyzer` port.
- Add an explainer adapter that answers questions from `ReferenceProfile`
  evidence, not raw provider internals.
- Move chat routing and reference Q&A orchestration into the backend application
  layer.
- Add optional reference-guided composition by passing only compact
  `ReferenceProfile` summaries into the composition graph.
