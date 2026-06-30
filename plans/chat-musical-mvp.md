# Chat Musical MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build LLMinem as a chat-first musical workspace that analyzes local songs and composes from scratch or from a reference profile.

**Architecture:** Keep the existing clean backend layers and multi-agent composition engine. Add a conversational application layer that routes chat intents to local audio analysis, music explanation, composition from scratch, or composition from reference. Containerize the backend early so MIR/audio dependencies run consistently.

**Tech Stack:** FastAPI, Pydantic v2, LangGraph, music21, pretty_midi, local MIR adapters, Next.js App Router, React, TypeScript, Docker.

---

## Source Documents

- `PRODUCT.md`: product behavior and MVP scope.
- `DESIGN.md`: UX direction.
- `docs/architecture.md`: technical boundaries and gotchas.
- `docs/architecture-refactor-status.md`: current backend refactor status.
- `plans/multiagent-band.md`: historical composition-engine plan.

## File Map

Planned files and responsibilities:

- `apps/api/Dockerfile`: backend runtime image for FastAPI and Python music/audio dependencies.
- `docker-compose.yml`: local orchestration for backend and frontend.
- `apps/api/music_assistant/domain/audio_profile.py`: extend reference profile models with energy, chords, and confidence.
- `apps/api/music_assistant/application/analyze_reference.py`: local reference analysis use case.
- `apps/api/music_assistant/application/answer_music_question.py`: evidence-grounded answers over `ReferenceProfile`.
- `apps/api/music_assistant/application/chat_music.py`: intent routing and conversational orchestration.
- `apps/api/music_assistant/application/compose_song.py`: support optional reference-guided composition.
- `apps/api/music_assistant/ports/audio_analyzer.py`: structured MIR analyzer contract.
- `apps/api/music_assistant/infrastructure/mir/librosa_analyzer.py`: local MIR implementation for tempo/key/energy/sections/chords.
- `apps/api/music_assistant/interfaces/api_models.py`: chat, upload, analysis, and composition response models.
- `apps/api/music_assistant/interfaces/api.py`: FastAPI routes for chat, local uploads, analysis, and composition.
- `apps/api/tests/`: tests for contracts, analysis fakes, chat routing, and reference-guided composition.
- `apps/web/lib/types.ts`: TypeScript mirrors for chat events and reference profile.
- `apps/web/app/page.tsx`: chat-first UI shell.
- `apps/web/components/`: chat, context, playback, mixer, tool detail, and generated-song components.
- `README.md`: local setup, Docker, and current product direction.

## Phase 0: Documentation And Baseline

**Files:**
- Modify: `README.md`
- Modify: `plans/multiagent-band.md`
- Remove: legacy root requirements document if still present

- [ ] Update `README.md` so it points to `PRODUCT.md`, `DESIGN.md`, `docs/architecture.md`, and `plans/chat-musical-mvp.md`.
- [ ] Remove references that describe any legacy requirements document as the source of truth.
- [ ] Update `plans/multiagent-band.md` header so it is clearly a historical composition-engine plan.
- [ ] Run `rg -n "source of truth|requirements document" README.md plans docs apps PRODUCT.md DESIGN.md`.
- [ ] Expected: only `PRODUCT.md` is described as the product source of truth.
- [ ] Run backend and frontend checks:

```bash
cd apps/api
python -m pytest
```

```bash
cd apps/web
npm run typecheck
node --test lib/trackMixerLogic.test.mjs
```

## Phase 1: Backend Docker Baseline

**Files:**
- Create: `apps/api/Dockerfile`
- Create: `apps/api/.dockerignore`
- Create: `docker-compose.yml`
- Modify: `README.md`

- [ ] Add a backend Dockerfile that installs Python dependencies and runs `uvicorn music_assistant.api:app --host 0.0.0.0 --port 8000`.
- [ ] Keep system packages minimal at first; add MIR/rendering packages only when adapters require them.
- [ ] Add `.dockerignore` for `.venv`, caches, outputs, and test artifacts.
- [ ] Add root `docker-compose.yml` with `api` and `web` services.
- [ ] Mount local artifact/upload directories for development.
- [ ] Document `docker compose up --build` in `README.md`.
- [ ] Verify:

```bash
docker compose config
docker compose build api
docker compose up api
```

- [ ] Expected: `GET http://localhost:8000/health` returns `{"status":"ok"}`.

## Phase 2: ReferenceProfile Contract

**Files:**
- Modify: `apps/api/music_assistant/domain/audio_profile.py`
- Modify: `apps/api/music_assistant/ports/audio_analyzer.py`
- Modify: `apps/api/tests/test_reference_analysis_boundary.py`
- Modify: `apps/web/lib/types.ts`

- [ ] Extend audio domain models with section energy, chord estimates, time ranges, and confidence.
- [ ] Keep the model compact; avoid raw arrays, FFT bins, or provider internals.
- [ ] Update fake analyzer tests to include tempo, key, sections, energy, and probable chords.
- [ ] Add TypeScript interfaces mirroring the backend models.
- [ ] Verify:

```bash
cd apps/api
python -m pytest tests/test_reference_analysis_boundary.py
```

```bash
cd apps/web
npm run typecheck
```

## Phase 3: Local Audio Analysis Adapter

**Files:**
- Modify: `apps/api/pyproject.toml`
- Modify: `apps/api/music_assistant/infrastructure/mir/librosa_analyzer.py`
- Create: `apps/api/tests/test_librosa_analyzer.py`
- Add fixture: `apps/api/tests/fixtures/audio/`

- [ ] Add local MIR dependencies needed for the first adapter.
- [ ] Implement duration and tempo extraction.
- [ ] Implement key estimation with confidence.
- [ ] Implement energy curve and simple section segmentation.
- [ ] Implement chord estimates by coarse time window with confidence language.
- [ ] Mark chord output as estimated/probable in the returned profile.
- [ ] Test with a short generated or committed-safe fixture.
- [ ] Verify:

```bash
cd apps/api
python -m pytest tests/test_librosa_analyzer.py tests/test_reference_analysis_boundary.py
```

## Phase 4: Music Question Answering

**Files:**
- Modify: `apps/api/music_assistant/application/answer_music_question.py`
- Create: `apps/api/tests/test_answer_music_question.py`

- [ ] Add a deterministic fallback explainer for tests and local no-key runs.
- [ ] Ensure answers cite profile evidence: tempo, key, section, energy, and probable chords.
- [ ] Ensure uncertain chords are phrased as "probably" or equivalent.
- [ ] Verify:

```bash
cd apps/api
python -m pytest tests/test_answer_music_question.py
```

## Phase 5: Conversational Orchestration

**Files:**
- Create: `apps/api/music_assistant/application/chat_music.py`
- Modify: `apps/api/music_assistant/interfaces/api_models.py`
- Modify: `apps/api/music_assistant/interfaces/api.py`
- Create: `apps/api/tests/test_chat_music.py`

- [ ] Define chat request/response models that carry message text, optional local reference id, and optional song context.
- [ ] Implement simple intent routing for MVP:
  - analyze attached/local audio;
  - answer question from existing `ReferenceProfile`;
  - compose from scratch;
  - compose from reference;
  - ask one clarification for ambiguous requests.
- [ ] Add tests using fake analyzer, fake explainer, and fake composer.
- [ ] Keep chat orchestration in `application/`, not in FastAPI route handlers.
- [ ] Verify:

```bash
cd apps/api
python -m pytest tests/test_chat_music.py tests/test_api_architecture.py
```

## Phase 6: Compose From Reference

**Files:**
- Modify: `apps/api/music_assistant/application/compose_song.py`
- Modify: `apps/api/music_assistant/agents/director.py`
- Modify: `apps/api/music_assistant/agents/instrument.py`
- Modify: `apps/api/music_assistant/graph.py`
- Create: `apps/api/tests/test_compose_from_reference.py`

- [ ] Add optional `ReferenceProfile` input to composition.
- [ ] Pass only compact summary fields to director and instrument prompts.
- [ ] Default to tempo, form, energy, and mood.
- [ ] Use key only when confidence is reasonable.
- [ ] Do not use chord estimates unless the chat intent explicitly requests harmonic guidance.
- [ ] Test composition with no reference, fake reference, low-confidence key, and requested chord guidance.
- [ ] Verify:

```bash
cd apps/api
python -m pytest tests/test_compose_from_reference.py tests/test_compose_director_path.py tests/test_negotiation.py
```

## Phase 7: Chat-First UI

**Files:**
- Modify: `apps/web/app/page.tsx`
- Create/modify: `apps/web/components/ChatThread.tsx`
- Create/modify: `apps/web/components/ComposerInput.tsx`
- Create/modify: `apps/web/components/ReferenceContext.tsx`
- Create/modify: `apps/web/components/GeneratedSongPanel.tsx`
- Modify: `apps/web/components/TrackMixer.tsx`
- Modify: `apps/web/lib/types.ts`

- [ ] Replace the form-first page with a chat-first shell.
- [ ] Keep local audio attachment and send controls visible.
- [ ] Show analysis details only after a reference exists.
- [ ] Show generated song playback/mixer only after a song exists.
- [ ] Move agent/tool details into compact expandable sections.
- [ ] Keep notation optional or hidden behind details.
- [ ] Verify:

```bash
cd apps/web
npm run typecheck
node --test lib/trackMixerLogic.test.mjs
```

## Phase 8: End-To-End Local Flow

**Files:**
- Modify: `README.md`
- Optional create: `docs/demo-script.md`

- [ ] Document a local demo:
  - start backend;
  - start frontend;
  - analyze a local audio fixture;
  - ask for likely chorus chords;
  - compose from scratch;
  - compose from reference;
  - play and mute/solo generated tracks.
- [ ] Run all checks:

```bash
cd apps/api
python -m pytest
```

```bash
cd apps/web
npm run typecheck
node --test lib/trackMixerLogic.test.mjs
```

```bash
docker compose config
docker compose build api
```

## Open Decisions

- Final visual style is intentionally not locked by this plan.
- Exact MIR implementation for chord estimation can change if the adapter returns
  the `ReferenceProfile` contract and confidence language.
- Persistent storage is out of scope for MVP.
- YouTube/reference search is out of scope for MVP.
