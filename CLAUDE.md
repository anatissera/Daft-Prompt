# CLAUDE.md — Daft Prompt

## Git rules (non-negotiable)
- **Never add Claude signatures/co-author trailers to commits.** Commits are authored by the repo owner (Naomi Couriel) only — no `Co-Authored-By: Claude` lines, no "Generated with Claude Code" footers.
- **Use gitflow/conventional-commit style matching the existing history**: `feat(api): ...`, `fix(web): ...`, `perf(api): ...`, `chore: ...`, `docs: ...`, `style(web): ...`, `refactor: ...`, `ci: ...`. Scope is the area (`api`, `web`, `compose`, `mir`, `ci`); subject is lowercase, imperative.
- **Never delete branches or anyone else's work.** A collaborator is actively implementing `docs/product-direction.md` on the `product-direction` branch.
- **`product-direction` is the freshest integration branch** (develop + composition-efficiency + roadmap doc). Base new feature branches on it, and merge `origin/product-direction` into your feature branch frequently (every few minutes while the collaborator is pushing) to avoid drift/conflicts.
- `main` is a stale snapshot (old `llm_band` package name). Don't base work on it.

## What this project is
Conversational music workspace, monorepo:
- `apps/api` — Python FastAPI, clean architecture (`domain/ → ports/ → application/ → infrastructure/ → interfaces/`), package `music_assistant` (renamed from `llm_band`; branches cut from old main still use the old name).
  - **Analysis pipeline** (`infrastructure/mir/deep_harmonic_analyzer.py`): Demucs stems → harmonic source → tempo/bar grid → Krumhansl-Schmuckler key → per-bar triad chords → A/B/C structure (multimodal per-stem detection with audit trail) → `ReferenceProfile`. Every stage injectable, degrades to analysis notes instead of raising. **Deep listening** (`listening_features.py`, `ensemble_features.py`, docs in `docs/deep-listening.md`): per-stem timbre/groove/bar-dynamics + mix timbre + section×stem arrangement timeline; feeds evidence claims and chat answers. Bars in profiles are 1-based.
  - **Composition** (`graph.py` + `agents/`): LangGraph batched sequential composer — director (arrangement/roster/chords/groups) → instrument agents with negotiation → arbiter → MIDI/MusicXML render (`music/`, `infrastructure/storage/render_artifacts.py`). Harmonic-fit validation + bass-downbeat enforcement in `music/validators.py` / `music/finalize.py`.
  - **Web research** (`infrastructure/web_research/`): shallow generic scraper producing `ReferenceProfile` from web evidence; sharpening is a roadmap item.
  - LLM providers: gemini/groq/openrouter/Vertex, fallback chains + rate limiter in `config.py` + `infrastructure/llm.py`.
- `apps/web` — Next.js 15 / React 19, chat-first UI, SSE streaming via Next route handlers proxying FastAPI, Daft Punk theme, GM-soundfont playback, mute/solo mixer, MIDI/MusicXML export. Pure logic lives in testable `lib/*.mjs` modules with co-located `.test.mjs`.

## Source of truth docs
`PRODUCT.md`, `DESIGN.md`, `AGENTS.md`, `docs/architecture.md`, `plans/*.md`, and `docs/product-direction.md` (on `product-direction`) — the phased roadmap (evidence-claim profiles, LLM tool-using chat orchestrator, CompositionBrief-driven composition).

## Branch audit (2026-07-04)
- Merged/redundant (do NOT delete, just don't mine them): `feat/graph-redesign`, `fix/compose-error-handling-and-drum-kit`, web-research half of `feat/scraping-analysis`, `chore/vercel-config`.
- **Unmerged value to carry forward**:
  - `feat/multimodal-section-detection` — per-stem multimodal structure detection with audit trail + Demucs stem cache + progress checklist UI. Not in develop/product-direction. `feat/scraping-analysis`'s tree holds the same work already on `music_assistant` names (best porting source).
  - `feat/composition-skills` — deterministic theory toolbelt (`progression/harmony/melody` + 38 tests) and the never-built `@tool`/`bind_tools` agent wiring. Reference/spec; based on stale main.
  - Composition-efficiency work is already on `product-direction`, but left 5 negotiation tests skipped (`apps/api/tests/test_negotiation.py`) — rewrite them when touching negotiation.
- Unbuilt plans: `plans/mert-stem-harmony-analysis.md`, `plans/deep-music-analysis.md` (both greenfield).

## Verification
- Backend: `cd apps/api && python -m pytest -q` (needs `pip install -e ".[dev]"`).
- Frontend: `cd apps/web && npm run typecheck && node --test lib/*.test.mjs`.
- CI (`.github/workflows/ci.yml`, on develop+) runs both on push/PR to develop and main.
