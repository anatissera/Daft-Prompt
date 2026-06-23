"""FastAPI service.

`POST /compose` returns a canned/director-composed `SongState` plus URLs to
rendered artifacts (`song.mid`, `song.musicxml`) in one shot. `POST
/compose/stream` runs the same pipeline but streams director/agent_pass/
convergence/done events over SSE as the LangGraph negotiation progresses.
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Iterator

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

from .agents.director import run_director
from .canned import canned_song
from .config import get_settings
from .graph import iter_negotiation_events, run_negotiation
from .music.render_midi import render_midi
from .music.render_sheet import render_musicxml
from .music.validators import errors_only, validate_song
from .schema import SongState

OUTPUTS = Path(__file__).resolve().parent.parent / "outputs"
OUTPUTS.mkdir(exist_ok=True)

app = FastAPI(title="Multi-agent Band API", version="0.1.0")

# Dev-open CORS so the Next.js frontend (any origin in dev) can fetch artifacts.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class ComposeRequest(BaseModel):
    style: str = "demo"


class Artifacts(BaseModel):
    midi: str
    musicxml: str


class ComposeResponse(BaseModel):
    job_id: str
    source: str  # "director" (LLM) | "canned" (no LLM configured)
    song: SongState
    artifacts: Artifacts


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/compose", response_model=ComposeResponse)
def compose(req: ComposeRequest, request: Request) -> ComposeResponse:
    job_id = uuid.uuid4().hex[:12]
    job_dir = OUTPUTS / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    # Director (LLM) when a provider is configured; otherwise the canned demo so
    # the app still runs with no key. Instrument agents then compose + negotiate
    # `parts` across bounded rounds (Phase 5) before the round cap force-converges.
    settings = get_settings()
    if settings.llm_configured:
        song = run_director(req.style)
        song = run_negotiation(song)
        source = "director"
    else:
        song = canned_song(req.style)
        source = "canned"

    _render_artifacts(song, job_dir)

    base = str(request.base_url).rstrip("/")
    return ComposeResponse(
        job_id=job_id,
        source=source,
        song=song,
        artifacts=Artifacts(
            midi=f"{base}/artifacts/{job_id}/song.mid",
            musicxml=f"{base}/artifacts/{job_id}/song.musicxml",
        ),
    )


def _render_artifacts(song: SongState, job_dir: Path) -> None:
    song.errors = [i.message for i in errors_only(validate_song(song))]
    render_midi(song, str(job_dir / "song.mid"))
    render_musicxml(song, str(job_dir / "song.musicxml"))


def _compose_stream_events(req: ComposeRequest, job_id: str, job_dir: Path, base: str) -> Iterator[dict]:
    settings = get_settings()
    if settings.llm_configured:
        song = run_director(req.style)
        source = "director"
        yield {"type": "director", "source": source, "header": song.header.model_dump(), "roster": [r.model_dump() for r in song.roster]}
        yield from iter_negotiation_events(song)
    else:
        song = canned_song(req.style)
        source = "canned"
        yield {"type": "director", "source": source, "header": song.header.model_dump(), "roster": [r.model_dump() for r in song.roster]}
        yield {"type": "convergence", "round": song.round, "converged": True, "resolved_requests": []}

    _render_artifacts(song, job_dir)
    yield {
        "type": "done",
        "job_id": job_id,
        "source": source,
        "song": song.model_dump(by_alias=True),
        "artifacts": {"midi": f"{base}/artifacts/{job_id}/song.mid", "musicxml": f"{base}/artifacts/{job_id}/song.musicxml"},
    }


@app.post("/compose/stream")
def compose_stream(req: ComposeRequest, request: Request) -> StreamingResponse:
    job_id = uuid.uuid4().hex[:12]
    job_dir = OUTPUTS / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    base = str(request.base_url).rstrip("/")

    def sse() -> Iterator[str]:
        for event in _compose_stream_events(req, job_id, job_dir, base):
            yield f"data: {json.dumps(event)}\n\n"

    return StreamingResponse(sse(), media_type="text/event-stream")


@app.get("/artifacts/{job_id}/{filename}")
def artifact(job_id: str, filename: str) -> FileResponse:
    # guard against path traversal
    if "/" in filename or ".." in filename or "/" in job_id or ".." in job_id:
        raise HTTPException(status_code=400, detail="invalid path")
    path = OUTPUTS / job_id / filename
    if not path.is_file():
        raise HTTPException(status_code=404, detail="artifact not found")
    media = "audio/midi" if filename.endswith(".mid") else "application/octet-stream"
    return FileResponse(path, media_type=media, filename=filename)
