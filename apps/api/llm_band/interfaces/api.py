"""FastAPI HTTP interface."""

from __future__ import annotations

from pathlib import Path
from typing import Iterator

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse

from llm_band.agents.director import run_director
from llm_band.application.compose_song import ComposeSong
from llm_band.canned import canned_song
from llm_band.config import get_settings
from llm_band.domain.song_state import Part
from llm_band.graph import iter_negotiation_events, run_negotiation
from llm_band.infrastructure.storage.render_artifacts import render_artifacts
from llm_band.infrastructure.storage.local_store import LocalArtifactStore
from llm_band.infrastructure.llm import LLMAllProvidersFailed, LLMError
from llm_band.interfaces.api_models import Artifacts, ComposeRequest, ComposeResponse, DoneEvent, ErrorEvent, sse_data

OUTPUTS = Path(__file__).resolve().parents[2] / "outputs"
ARTIFACTS = LocalArtifactStore(OUTPUTS)

app = FastAPI(title="Multi-agent Band API", version="0.1.0")

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
    try:
        song, source = _compose_song().compose(req.style)
    except LLMError as exc:
        raise HTTPException(status_code=503, detail=_llm_error_event(exc, partial=False)) from exc
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


def _compose_song() -> ComposeSong:
    return ComposeSong(
        llm_configured=lambda: get_settings().llm_configured,
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
    last_song = None
    last_source = "canned"
    last_agent_event = None
    try:
        stream = _compose_song().stream(req.style)
        for event, song_snapshot, source in stream:
            last_source = source
            if song_snapshot is not None:
                last_song = song_snapshot
            if event:
                if event.get("type") == "agent_pass":
                    last_agent_event = event
                yield event
            if event or song_snapshot is None:
                continue

            render_artifacts(song_snapshot, job_dir)
            yield DoneEvent(job_id=job_id, source=source, song=song_snapshot, artifacts=artifacts).model_dump(
                by_alias=True, mode="json"
            )
            return
    except LLMError as exc:
        yield _llm_error_event(exc, partial=last_song is not None)
        if last_song is None:
            return
        last_song.converged = False
        last_song.errors.append(exc.user_message)
        render_artifacts(last_song, job_dir)
        yield DoneEvent(job_id=job_id, source=last_source, song=last_song, artifacts=artifacts).model_dump(
            by_alias=True, mode="json"
        )
    except Exception:
        if last_song is None:
            raise
        if last_agent_event is not None:
            instrument_id = last_agent_event.get("instrument_id")
            if instrument_id and instrument_id not in last_song.parts:
                last_song.parts[instrument_id] = Part(
                    instrument_id=instrument_id,
                    notes=[],
                    notes_summary=last_agent_event.get("notes_summary", "fallback: agent failed"),
                )
        last_song.converged = False
        last_song.errors.append("composition stopped after an agent failed; returning partial result")
        render_artifacts(last_song, job_dir)
        yield {
            "type": "convergence",
            "round": last_song.round,
            "converged": False,
            "resolved_requests": [],
        }
        yield DoneEvent(job_id=job_id, source=last_source, song=last_song, artifacts=artifacts).model_dump(
            by_alias=True, mode="json"
        )


def _llm_error_event(exc: LLMError, *, partial: bool) -> dict:
    provider = exc.provider
    model = exc.model
    if isinstance(exc, LLMAllProvidersFailed) and exc.failures:
        last = exc.failures[-1]
        provider = last.provider
        model = last.model
    return ErrorEvent(
        code=exc.code,
        message=exc.user_message,
        provider=None if provider == "all" else provider,
        model=None if model == "all" else model,
        partial=partial,
    ).model_dump(mode="json")


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
