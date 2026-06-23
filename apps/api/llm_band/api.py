"""FastAPI service — Phase 1 walking skeleton.

`POST /compose` returns a canned `SongState` plus URLs to rendered artifacts
(`song.mid`, `song.musicxml`). No LLM and no streaming yet; later phases turn this
into an SSE stream driven by the LangGraph pipeline.
"""

from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

from .canned import canned_song
from .music.render_midi import render_midi
from .music.render_sheet import render_musicxml
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

    song = canned_song(req.style)
    render_midi(song, str(job_dir / "song.mid"))
    render_musicxml(song, str(job_dir / "song.musicxml"))

    base = str(request.base_url).rstrip("/")
    return ComposeResponse(
        job_id=job_id,
        song=song,
        artifacts=Artifacts(
            midi=f"{base}/artifacts/{job_id}/song.mid",
            musicxml=f"{base}/artifacts/{job_id}/song.musicxml",
        ),
    )


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
