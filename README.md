<div style="display: flex; align-items: center; gap: 32px; margin-bottom: 48px; padding: 24px; background: linear-gradient(135deg, rgba(3,3,5,0.8), rgba(11,11,18,0.8)); border: 1px solid rgba(0,212,255,0.2); border-radius: 12px; backdrop-filter: blur(10px);">
  <img src="./apps/web/public/helmet-icon.png" alt="Daft Punk Helmet" style="width: 120px; height: 120px; object-fit: contain; filter: drop-shadow(0 0 20px rgba(0,212,255,0.4));" />
  <div>
    <h1 style="margin: 0; font-family: 'Orbitron', monospace; font-size: 48px; font-weight: 900; color: #a8a8c0; text-shadow: 0 0 30px rgba(168,168,192,0.4); letter-spacing: 4px;">DAFT PROMPT</h1>
    <p style="margin: 12px 0 0; color: #8888a8; font-size: 16px; letter-spacing: 2px; font-family: monospace;">Upload • Analyze • Compose • Understand</p>
  </div>
</div>

Upload a track for harmonic analysis. Ask music questions grounded in evidence. Compose new sketches inspired by references. All from one chat.

Powered by multi-agent LLMs, real music information retrieval, and a retro-futuristic UI.

---

## What This Is

Daft Prompt is a conversational music workspace that bridges AI agents with real music analysis.

**The flow**
1. Upload a local audio file
2. Real MIR extracts tempo, key, chord progressions, and structure (bar-aligned)
3. Ask musical questions → evidence-grounded answers
4. Compose from scratch or guided by the analyzed reference
5. Play, inspect, and export your generated song

**The tech stack**
* Python FastAPI backend with clean architecture
* Demucs + librosa for stem separation and harmonic analysis
* Krumhansl-Schmuckler key estimation with relative ambiguity detection
* Per-bar triad chord estimation and A/B/C structure detection
* LangGraph multi-agent composition with negotiation rounds
* Next.js UI with Daft Punk retro-futuristic aesthetic

---

## Current Status

### Working Now (MVP Foundation)

Backend analysis
* Stem separation (drums, bass, vocals, other) via Demucs htdemucs
* Harmonic source extraction (bass + other stems preferred, HPSS fallback)
* Tempo grid with beat and bar boundaries (assumed 4/4)
* Key candidates via Krumhansl-Schmuckler profiles
* Per-bar triad chord estimation (major/minor/diminished) with smoothing
* A/B/C structure detection from chord patterns
* Analysis notes for degradation cases (separation unavailable, weak bar grid)
* Full orchestration → `ReferenceProfile` with legacy compat fields

UI
* Chat-first workspace with reference context sidebar
* File upload for local audio analysis
* Realtime analysis progress (SSE) → future streaming
* Music question answering over `ReferenceProfile` (deterministic)
* Composition from scratch or reference-guided
* Song playback, MIDI inspection, export

Composition engine
* Director agent picks arrangement and roster
* Instrument agents compose parts via negotiation
* Arbiter resolves ties through shared song state
* MIDI and MusicXML rendering
* SSE event streaming for UI feedback

Tests
* 112 unit tests for analysis (phases 2-7)
* Feature module tests with injectable fakes (fast, no heavy audio)
* Orchestrator tests for full assembly
* HTTP boundary tests for upload/analysis/composition routes
* Architecture boundary tests (clean layers)

### Not Yet (Post-MVP Backlog)

From [`plans/deep-music-analysis.md`](./plans/deep-music-analysis.md) (future vision)
* Melodic transcription and voice-leading analysis
* Per-stem spectral timbre and dynamics
* Groove/rhythm micro-timing
* Ensemble view with cross-stem relationships
* UI components for timeline, spectrogram, voice-leading viz

From Phase 8-10 of [`plans/deep-harmonic-analysis.md`](./plans/deep-harmonic-analysis.md)
* Analysis progress streaming (SSE events per stage)
* Frontend rendering of harmony/structure with key candidates and progressions
* Evidence-grounded Q&A deterministic logic (probabilistic language)

---

## Source Of Truth

* [`PRODUCT.md`](./PRODUCT.md) → Product behavior and MVP scope
* [`DESIGN.md`](./DESIGN.md) → UX direction and chat-first flow
* [`AGENTS.md`](./AGENTS.md) → Agent responsibilities, constraints, security boundaries
* [`docs/architecture.md`](./docs/architecture.md) → Technical layers and boundaries
* [`plans/deep-harmonic-analysis.md`](./plans/deep-harmonic-analysis.md) → Phases 0-7 (MVP) with checkboxes
* [`plans/deep-music-analysis.md`](./plans/deep-music-analysis.md) → Future vision (post-MVP tracks)
* [`plans/chat-musical-mvp.md`](./plans/chat-musical-mvp.md) → Chat product roadmap

---

## Architecture

### Backend Layers

```
apps/api/llm_band/
  domain/           → AudioProfile, ReferenceProfile, SongState models
  application/      → AnalyzeReference, ComposeSong, AnswerMusicQuestion
  ports/            → LLM, StemSeparator, AudioAnalyzer, TranscriptionService
  infrastructure/
    mir/            → DeepHarmonicAnalyzer (Phases 2-7), feature modules
    storage/        → ArtifactStore (local/S3), song rendering
    llm/            → LLM provider routing (Gemini, Groq, OpenRouter)
  interfaces/       → FastAPI routes, SSE streaming, models
```

### Analysis Pipeline (Phases 2-7)

```
ReferenceSource (local file path)
  → Phase 1: Demucs stem separation (4 stems: drums/bass/vocals/other)
  → Phase 2: Harmonic source (bass+other preferred, HPSS fallback, mix last resort)
  → Phase 3: Tempo grid (beat + bar boundaries, drum-preferred onset detection)
  → Phase 4: Key profile (Krumhansl-Schmuckler, 8 candidates, relative ambiguity flag)
  → Phase 5: Chord spans (per-bar triads, confidence weighted by separation)
  → Phase 6: Structure (A/B/C labels from chord patterns, 4-bar phrases)
  → Phase 7: Assembly → ReferenceProfile (harmony + structure + legacy compat)
```

### Composition Pipeline

```
style prompt + optional ReferenceProfile
  → director (arrangement intent + roster)
  → instrument agents compose via negotiation rounds
  → shared SongState consensus
  → convergence or arbiter tiebreak
  → MIDI + MusicXML rendering
  → SSE event stream to UI
```

---

## Quick Start

### Frontend (Next.js + React)

```bash
cd apps/web
npm install
npm run dev        # http://localhost:3001
```

### Backend (Python FastAPI)

```bash
cd apps/api

# Create venv
python3 -m venv venv
source venv/bin/activate

# Install
pip install -e .

# Optional: Add an LLM provider
pip install -e ".[gemini]"    # or [groq], [openrouter]

# Set env
export LLM_PROVIDER=gemini
export GOOGLE_API_KEY=xxx

# Run
uvicorn llm_band.interfaces.api:app --reload --port 8000
```

### Docker (both services)

```bash
docker-compose up
# API: http://localhost:8000
# UI:  http://localhost:3000
```

---

## Testing

```bash
cd apps/api

# All tests (unit + integration)
pytest

# Just analysis features (fast, no heavy audio)
pytest tests/test_*_features.py tests/test_deep_harmonic_analyzer.py

# With coverage
pytest --cov=llm_band tests/
```

Key test strategy: All feature modules accept injectable fakes for speed. The test suite skips real Demucs separation (too slow) but covers fallback paths, confidence adjustments, and graceful degradation.

---

## Key Concepts

### Bar-Aligned Representation

All harmonic and structural features use `start_bar` / `end_bar` (integer indices) instead of seconds. This matches the composer's intent and makes synchronization with the tempo grid trivial.

**Example**: A chord span at bars 5-8 covers exactly 4 bars of the song, regardless of tempo variations or fractional beats.

### Harmonic Source Strategy

For accurate key and chord estimation, we blend stems:
* **Preferred**: bass + other stems (vocals and drums removed for cleaner pitch)
* **Fallback 1**: HPSS harmonic component from mix
* **Fallback 2**: Raw mix as last resort

Each fallback adjusts confidence accordingly. Analysis notes flag when degradation happens.

### Key Estimation: Krumhansl-Schmuckler

We profile the chroma vector against 12 major and 12 minor profiles. Relative major/minor ambiguity is flagged when the top two candidates are within 0.04 confidence margin.

### Chord Smoothing

Single-bar outliers between two identical, high-confidence neighbors get corrected automatically. This handles spurious transcription errors without losing real harmonic movement.

### Structure from Chords

A/B/C labels come from 4-bar phrase windows. Same chord-tuple signature within a window = same letter. Consecutive same-letter windows merge into a single structural section.

---

## Development Workflow

Branches
* `main` → Deployable, protected (PR-only)
* `develop` → Integration branch, frequent commits
* `feat/*` → Feature branches off develop, merged via PR

Typical flow
```bash
git checkout develop
git pull origin develop
git checkout -b feat/your-feature
# ... code ...
git push -u origin feat/your-feature
# → create PR to develop
# → review + merge
```

Environment
* Python 3.10+
* Node.js 18+
* Demucs requires torch (installed via pip)
* PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 required (ROS launch_testing plugin conflict on some systems)

---

## Docs

* [`PRODUCT.md`](./PRODUCT.md) → What users can do and why
* [`DESIGN.md`](./DESIGN.md) → Chat UX flows and interaction patterns
* [`AGENTS.md`](./AGENTS.md) → Agent rules, tools, constraints, security
* [`docs/architecture.md`](./docs/architecture.md) → Clean layers, ports, boundaries
* [`plans/`](./plans/) → Implementation phases, roadmaps, vision

---

## Troubleshooting

**Port 3000 already in use?**
Dev server falls back to 3001 automatically. Check http://localhost:3001.

**Librosa import error?**
```bash
pip install librosa>=0.10
```

**Demucs slow or OOM?**
Demucs (4.0+) uses about 6GB VRAM. On limited hardware, tests skip real separation (use fakes).

**PYTEST_DISABLE_PLUGIN_AUTOLOAD not set?**
```bash
export PYTEST_DISABLE_PLUGIN_AUTOLOAD=1
pytest
```
(ROS launch_testing plugin interferes; this disables auto-discovery.)

**LLM provider not configured?**
```bash
export LLM_PROVIDER=gemini
export GOOGLE_API_KEY=your-key
```
Fallback is no LLM (composition will fail gracefully).

---

Built by [UdeSA NLP Group](https://udesa.edu.ar). Music analysis meets multi-agent reasoning. Retro-futuristic vibes guaranteed.

**[ DIGITAL STUDIO // AI MUSIC LAB ]**
