"""FastAPI service."""

from __future__ import annotations

from pathlib import Path
from typing import Iterator

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse

from .api_models import Artifacts, ComposeRequest, ComposeResponse, DoneEvent, sse_data
from .artifacts import LocalArtifactStore
from .agents.director import run_director
from .canned import canned_song
from .composition import CompositionService
from .config import get_settings
from .graph import iter_negotiation_events, run_negotiation
from .rendering import render_artifacts

OUTPUTS = Path(__file__).resolve().parent.parent / "outputs"
ARTIFACTS = LocalArtifactStore(OUTPUTS)

app = FastAPI(title="Multi-agent Band API", version="0.1.0")

# Dev-open CORS so the Next.js frontend (any origin in dev) can fetch artifacts.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/compose", response_model=ComposeResponse)
def compose(req: ComposeRequest, request: Request) -> ComposeResponse:
    job = ARTIFACTS.create_job()
    song, source = _composition_service().compose(req.style)
    render_artifacts(song, job.path)

    base = str(request.base_url).rstrip("/")
    return ComposeResponse(
        job_id=job.job_id,
        source=source,
        song=song,
        artifacts=Artifacts(
            midi=ARTIFACTS.url_for(base, job.job_id, "song.mid"),
            musicxml=ARTIFACTS.url_for(base, job.job_id, "song.musicxml"),
        ),
    )


def _composition_service() -> CompositionService:
    return CompositionService(
        settings_factory=get_settings,
        director=run_director,
        negotiator=run_negotiation,
        event_streamer=iter_negotiation_events,
        canned=canned_song,
    )


def _compose_stream_events(req: ComposeRequest, job_id: str, job_dir: Path, base: str) -> Iterator[dict]:
    artifacts = Artifacts(
        midi=ARTIFACTS.url_for(base, job_id, "song.mid"),
        musicxml=ARTIFACTS.url_for(base, job_id, "song.musicxml"),
    )
    for event, final_song, source in _composition_service().stream(req.style):
        if event:
            yield event
        if final_song is None:
            continue

        render_artifacts(final_song, job_dir)
        yield DoneEvent(job_id=job_id, source=source, song=final_song, artifacts=artifacts).model_dump(
            by_alias=True, mode="json"
        )


@app.post("/compose/stream")
def compose_stream(req: ComposeRequest, request: Request) -> StreamingResponse:
    job = ARTIFACTS.create_job()
    base = str(request.base_url).rstrip("/")

    def sse() -> Iterator[str]:
        for event in _compose_stream_events(req, job.job_id, job.path, base):
            yield sse_data(event)

    return StreamingResponse(sse(), media_type="text/event-stream")


@app.get("/artifacts/{job_id}/{filename}")
def artifact(job_id: str, filename: str) -> FileResponse:
    path = ARTIFACTS.path_for(job_id, filename)
    if path is None:
        raise HTTPException(status_code=400, detail="invalid path")
    if not path.is_file():
        raise HTTPException(status_code=404, detail="artifact not found")
    media = "audio/midi" if filename.endswith(".mid") else "application/octet-stream"
    return FileResponse(path, media_type=media, filename=filename)
