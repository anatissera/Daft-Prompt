# Daft Prompt

Daft Prompt is a chat-first musical assistant. In this experimental branch, the
product researches known songs from public web sources instead of accepting
local audio uploads.

The flow:

1. Ask about a song by artist/title.
2. The backend searches candidate music pages, fetches HTML, extracts compact
   musical claims, and fuses conflicting evidence.
3. The chat answers with cited, probabilistic musical summaries.
4. The composer can generate new MIDI/MusicXML sketches using traits from one
   or more researched references.

The app never plays commercial songs and does not store full tabs or lyrics.

## Stack

- FastAPI + Pydantic backend in `apps/api/music_assistant`
- Web research adapters under `infrastructure/web_research`
- LangGraph multi-agent composition
- Next.js chat UI
- Docker Compose for local development

## Run Locally

Backend:

```bash
cd apps/api
python3 -m venv venv
source venv/bin/activate
pip install -e ".[dev]"
uvicorn music_assistant.interfaces.api:app --reload --port 8000
```

Frontend:

```bash
cd apps/web
npm install
npm run dev
```

Docker:

```bash
docker compose up --build
```

## Tests

```bash
cd apps/api
python -m pytest
```

```bash
cd apps/web
npm run typecheck
node --test lib/analysisProgress.test.mjs lib/chatActionAdapter.test.mjs lib/referenceProfileView.test.mjs lib/trackMixerLogic.test.mjs
```

## Source Of Truth

- `PRODUCT.md`
- `DESIGN.md`
- `docs/architecture.md`
- `plans/mert-stem-harmony-analysis.md` is paused for this branch.
