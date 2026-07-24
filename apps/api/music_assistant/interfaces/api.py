"""FastAPI HTTP interface."""

from __future__ import annotations

import uuid
from dotenv import load_dotenv

load_dotenv()
from inspect import signature
from pathlib import Path
from queue import Empty, Queue
from threading import Thread
from typing import AsyncIterator, Iterator, Optional

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse

from music_assistant.application.analyze_reference import AnalyzeReference
from music_assistant.application.answer_music_question import AnswerMusicQuestion
from music_assistant.application.chat_music import ChatMusic, _style_with_reference
from music_assistant.domain.cancellation import (
    CancelToken,
    CancelledCompose,
    set_cancel_token,
)
from music_assistant.application.compose_song import ComposeConfigurationError, ComposeSong
from music_assistant.application.research_reference import ResearchReference
from music_assistant.canned import canned_song
from music_assistant.config import get_settings
from music_assistant.domain.audio_profile import ReferenceProfile, ReferenceSource
from music_assistant.domain.song_state import Part, SongState
from music_assistant.graph import iter_negotiation_events, run_negotiation
from music_assistant.band_agent import stream_compose as band_agent_stream
from music_assistant.infrastructure.mir.deep_harmonic_analyzer import DeepHarmonicAnalyzer
from music_assistant.infrastructure.storage.in_memory_reference_store import InMemoryReferenceStore
from music_assistant.infrastructure.storage.render_artifacts import render_artifacts
from music_assistant.infrastructure.storage.local_store import LocalArtifactStore
from music_assistant.infrastructure.web_research.researcher import DefaultSongResearcher
from music_assistant.infrastructure.llm import LLMAllProvidersFailed, LLMError
from music_assistant.interfaces.api_models import (
    AnalysisDoneEvent,
    AnalysisErrorEvent,
    AnalysisProgressEvent,
    Artifacts,
    ChatRequest,
    ChatResponse,
    ComposeRequest,
    ComposeResponse,
    DoneEvent,
    ErrorEvent,
    ResearchRequest,
    sse_data,
)

DEFAULT_OUTPUTS = Path(__file__).resolve().parents[2] / "outputs"
REFERENCE_UPLOADS = Path(__file__).resolve().parents[2] / "uploads"


def _artifacts_root() -> Path:
    """Where rendered MIDI/MusicXML land.

    Configurable so container hosts with a read-only or memory-backed
    filesystem can point it at a writable path (ARTIFACTS_DIR=/tmp/outputs on
    Cloud Run). Mirrors ``_reference_upload_root`` below.
    """
    configured = getattr(get_settings(), "artifacts_dir", None)
    return Path(configured).expanduser() if configured else DEFAULT_OUTPUTS


OUTPUTS = _artifacts_root()
ARTIFACTS = LocalArtifactStore(OUTPUTS)
REFERENCE_STORE = InMemoryReferenceStore()
SUPPORTED_REFERENCE_EXTENSIONS = {".wav", ".mp3", ".flac", ".m4a", ".ogg", ".aiff", ".aif"}
UPLOAD_CHUNK_SIZE = 1024 * 1024
ANALYSIS_KEEPALIVE_SECONDS = 15.0

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


@app.post("/references/analyze", response_model=ReferenceProfile)
async def analyze_reference_upload(file: UploadFile | None = File(None)) -> ReferenceProfile:
    source = await _store_reference_upload(file)
    try:
        profile = AnalyzeReference(_reference_analyzer()).execute(source)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=422,
            detail=f"could not analyze uploaded audio: {exc}",
        ) from exc
    REFERENCE_STORE.save(profile)
    return profile


@app.post("/references/analyze/stream")
async def analyze_reference_upload_stream(file: UploadFile | None = File(None)) -> StreamingResponse:
    source = await _store_reference_upload(file)

    def sse() -> Iterator[str]:
        for event in _reference_analysis_stream_events(source):
            yield sse_data(event)

    return StreamingResponse(sse(), media_type="text/event-stream")


@app.post("/references/research", response_model=ReferenceProfile)
def research_reference(req: ResearchRequest) -> ReferenceProfile:
    """Research a song from public web sources (no audio upload) and persist it so
    follow-up chat questions can find it by reference_id."""
    try:
        profile = ResearchReference(_song_researcher()).execute(req.query)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"could not research song: {exc}") from exc
    REFERENCE_STORE.save(profile)
    return profile


@app.post("/references/research/stream")
def research_reference_stream(req: ResearchRequest) -> StreamingResponse:
    def sse() -> Iterator[str]:
        yield sse_data(AnalysisProgressEvent(type="accepted", message="Research request accepted."))
        yield sse_data(AnalysisProgressEvent(type="searching_sources", message="Searching public music sources."))
        yield sse_data(AnalysisProgressEvent(type="fetching_pages", message="Fetching candidate pages."))
        yield sse_data(AnalysisProgressEvent(type="extracting_claims", message="Extracting musical claims."))
        try:
            profile = ResearchReference(_song_researcher()).execute(req.query)
            REFERENCE_STORE.save(profile)
            yield sse_data(AnalysisProgressEvent(type="fusing_evidence", message="Fusing source evidence."))
            yield sse_data(AnalysisDoneEvent(profile=profile, message="Research ready."))
        except Exception as exc:
            yield sse_data(AnalysisErrorEvent(message=f"could not research song: {exc}"))

    return StreamingResponse(sse(), media_type="text/event-stream")


def _song_researcher() -> DefaultSongResearcher:
    return DefaultSongResearcher()


async def _store_reference_upload(file: UploadFile | None) -> ReferenceSource:
    if file is None:
        raise HTTPException(status_code=400, detail="missing audio file")

    filename = Path(file.filename or "").name
    if not filename:
        raise HTTPException(status_code=400, detail="empty filename")

    suffix = Path(filename).suffix.lower()
    if suffix not in SUPPORTED_REFERENCE_EXTENSIONS:
        raise HTTPException(
            status_code=415,
            detail=f"unsupported audio file extension: {suffix or 'none'}",
        )

    reference_id = f"ref_{uuid.uuid4().hex[:12]}"
    upload_root = _reference_upload_root()
    upload_dir = upload_root / reference_id
    upload_dir.mkdir(parents=True, exist_ok=True)
    audio_path = upload_dir / filename

    total_bytes = 0
    try:
        with audio_path.open("wb") as handle:
            while chunk := await file.read(UPLOAD_CHUNK_SIZE):
                total_bytes += len(chunk)
                if total_bytes > _reference_upload_max_bytes():
                    audio_path.unlink(missing_ok=True)
                    raise HTTPException(
                        status_code=413,
                        detail="uploaded audio file is too large",
                    )
                handle.write(chunk)
    finally:
        await file.close()

    if total_bytes == 0:
        audio_path.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail="uploaded audio file is empty")

    source = ReferenceSource(
        reference_id=reference_id,
        kind="upload",
        label=filename,
        uri=str(audio_path),
        authorized=True,
    )
    return source


def _reference_analysis_stream_events(source: ReferenceSource) -> Iterator[dict]:
    events: Queue[dict | None] = Queue()

    def progress(stage: str, message: str) -> None:
        events.put(AnalysisProgressEvent(type=stage, message=message).model_dump(mode="json"))

    def worker() -> None:
        analyzer = _reference_analyzer()
        try:
            profile = _analyze_with_progress(analyzer, source, progress)
            REFERENCE_STORE.save(profile)
            events.put(AnalysisDoneEvent(profile=profile).model_dump(mode="json"))
        except Exception as exc:
            events.put(
                AnalysisErrorEvent(
                    message=f"could not analyze uploaded audio: {exc}",
                ).model_dump(mode="json")
            )
        finally:
            events.put(None)

    yield AnalysisProgressEvent(type="accepted", message="File accepted. Starting analysis.").model_dump(mode="json")
    thread = Thread(target=worker, daemon=True)
    thread.start()
    while True:
        try:
            event = events.get(timeout=ANALYSIS_KEEPALIVE_SECONDS)
        except Empty:
            yield AnalysisProgressEvent(
                type="analysis_keepalive",
                message="Still analyzing. This can take a few minutes for longer songs.",
            ).model_dump(mode="json")
            continue
        if event is None:
            break
        yield event


def _analyze_with_progress(analyzer, source: ReferenceSource, progress) -> ReferenceProfile:
    analyze = analyzer.analyze
    if "progress" in signature(analyze).parameters:
        return analyze(source, progress=progress)
    return analyze(source)


def _reference_analyzer() -> DeepHarmonicAnalyzer:
    return DeepHarmonicAnalyzer(output_root=_reference_upload_root())


@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest, request: Request) -> ChatResponse:
    if req.reference_id and REFERENCE_STORE.get(req.reference_id) is None:
        raise HTTPException(status_code=404, detail=f"reference_id not found: {req.reference_id}")
    try:
        response = _chat_music().handle(req)
    except ComposeConfigurationError as exc:
        raise HTTPException(status_code=503, detail=_compose_configuration_error_event(exc)) from exc
    except LLMError as exc:
        raise HTTPException(status_code=503, detail=_llm_error_event(exc, partial=False)) from exc

    # If the orchestrator composed a song, render audio/score artifacts and
    # attach URLs so the chat UI can play / score / download — same contract
    # the dedicated /compose endpoint uses.
    if response.compose is not None:
        from music_assistant.application.chat_music import ChatArtifacts
        job = ARTIFACTS.create_job()
        try:
            render_artifacts(response.compose.song, job.path)
            base = str(request.base_url).rstrip("/")
            response = response.model_copy(update={
                "compose": response.compose.model_copy(update={
                    "artifacts": ChatArtifacts(
                        midi=ARTIFACTS.url_for(base, job.job_id, "song.mid"),
                        musicxml=ARTIFACTS.url_for(base, job.job_id, "song.musicxml"),
                    ),
                }),
            })
        except Exception:
            # Artifact rendering is best-effort; the song state is still usable.
            pass
    return response


@app.post("/chat/stream")
async def chat_stream(req: ChatRequest, request: Request) -> StreamingResponse:
    """Streaming variant of /chat. Emits SSE events so the UI can drive a real
    pipeline visualisation from actual backend milestones instead of a fake
    time-based one:

      - ``intent``       — classifier result (``compose``, ``answer_reference``, …)
      - ``director``     — director produced a header + roster
      - ``agent_pass``   — one instrument turn completed
      - ``convergence``  — arbiter finalised the arrangement
      - ``done``         — artifacts rendered (with URLs)
      - ``reply``        — for non-compose intents, the full ChatResponse
      - ``error``        — LLM or config failure
    """
    # Scope a CancelToken for this request so any LLM call inside the sync
    # generator (which runs in a threadpool) can be aborted mid-flight when
    # the browser hits Stop and the SSE connection drops.
    token = CancelToken()
    set_cancel_token(token)

    def sse_body() -> Iterator[str]:
        profile = None
        if req.reference_id:
            profile = REFERENCE_STORE.get(req.reference_id)
            if profile is None:
                yield sse_data(
                    ErrorEvent(
                        code="reference_not_found",
                        message=f"reference_id not found: {req.reference_id}",
                        provider=None,
                        model=None,
                        partial=False,
                    ).model_dump(mode="json")
                )
                return

        chat_music = _chat_music()
        message = req.message.strip()
        prev_song_path = (
            ARTIFACTS.path_for(req.edit_job_id, "song.json") if req.edit_job_id else None
        )
        has_previous = bool(prev_song_path and prev_song_path.exists())
        intent = chat_music._classify(
            message, has_reference=profile is not None, has_previous=has_previous
        )
        yield sse_data({"type": "intent", "intent": intent})

        if intent == "edit_song":
            from music_assistant.band_agent.edit_song import (
                apply_additions,
                apply_edit,
                plan_edit,
            )

            prev = SongState.model_validate_json(prev_song_path.read_text())
            yield sse_data({
                "type": "progress", "stage": "edit",
                "message": "planning the edit over the previous song",
            })
            plan = plan_edit(message, prev)
            if plan is None:
                yield sse_data({"type": "reply", "response": {
                    "intent": "edit_song",
                    "reply": (
                        "No pude traducir ese pedido a una edición concreta. "
                        "Probá algo como 'reemplazá el piano por un rhodes' o "
                        "'subí el pitch del bajo una octava'."
                    ),
                    "reference_id": None, "answer": None, "compose": None,
                    "clarification": None, "usage": None,
                }})
                return
            edited, changes = apply_edit(prev, plan)
            yield sse_data({
                "type": "progress", "stage": "edit",
                "message": plan.summary or "; ".join(changes) or "applying edit",
            })
            edited, add_changes = apply_additions(edited, plan)
            if add_changes:
                yield sse_data({
                    "type": "progress", "stage": "edit",
                    "message": "; ".join(add_changes),
                })
            job = ARTIFACTS.create_job()
            base = str(request.base_url).rstrip("/")
            render_artifacts(edited, job.path)
            yield sse_data({
                "type": "director",
                "source": "director",
                "header": edited.header.model_dump(mode="json"),
                "roster": [r.model_dump(mode="json") for r in edited.roster],
            })
            yield sse_data(DoneEvent(
                job_id=job.job_id,
                source="director",
                song=edited,
                artifacts=Artifacts(
                    midi=ARTIFACTS.url_for(base, job.job_id, "song.mid"),
                    musicxml=ARTIFACTS.url_for(base, job.job_id, "song.musicxml"),
                ),
            ).model_dump(by_alias=True, mode="json"))
            return

        if intent not in ("compose", "compose_from_reference"):
            try:
                response = chat_music.handle(req)
            except ComposeConfigurationError as exc:
                yield sse_data(_compose_configuration_error_event(exc))
                return
            except LLMError as exc:
                yield sse_data(_llm_error_event(exc, partial=False))
                return
            yield sse_data({"type": "reply", "response": response.model_dump(mode="json")})
            return

        if intent == "compose_from_reference":
            assert profile is not None
            style = _style_with_reference(message, profile)
        else:
            style = message or "demo"

        job = ARTIFACTS.create_job()
        base = str(request.base_url).rstrip("/")
        compose_req = ComposeRequest(style=style)
        try:
            for event in _compose_stream_events(compose_req, job.job_id, job.path, base):
                yield sse_data(event)
        except CancelledCompose:
            yield sse_data({
                "type": "error",
                "code": "cancelled",
                "message": "compose cancelled by client",
                "provider": None,
                "model": None,
                "partial": True,
            })

    return StreamingResponse(
        _sse_with_cancel(request, sse_body(), token),
        media_type="text/event-stream",
    )


async def _sse_with_cancel(
    request: Request,
    body: Iterator[str],
    token: CancelToken,
) -> AsyncIterator[str]:
    """Bridge sync SSE generator → async iterator, polling the client socket
    in parallel. When the browser disconnects the CancelToken fires, which
    tears down any in-flight LLM socket via the httpx clients we registered.
    """
    import asyncio

    queue: asyncio.Queue[Optional[str]] = asyncio.Queue()
    loop = asyncio.get_running_loop()

    def pump() -> None:
        try:
            for chunk in body:
                loop.call_soon_threadsafe(queue.put_nowait, chunk)
                if token.cancelled:
                    break
        except Exception as exc:
            loop.call_soon_threadsafe(
                queue.put_nowait,
                sse_data({
                    "type": "error",
                    "code": "compose_crashed",
                    "message": str(exc),
                    "provider": None,
                    "model": None,
                    "partial": True,
                }),
            )
        finally:
            loop.call_soon_threadsafe(queue.put_nowait, None)

    producer = asyncio.create_task(asyncio.to_thread(pump))

    async def watch_disconnect() -> None:
        try:
            while not producer.done():
                if await request.is_disconnected():
                    token.cancel()
                    return
                await asyncio.sleep(0.5)
        except asyncio.CancelledError:
            return

    watcher = asyncio.create_task(watch_disconnect())

    try:
        while True:
            chunk = await queue.get()
            if chunk is None:
                break
            yield chunk
    finally:
        token.cancel()  # idempotent — belt-and-suspenders for the finally path
        watcher.cancel()
        try:
            await watcher
        except Exception:
            pass
        try:
            await producer
        except Exception:
            pass
        set_cancel_token(None)


def _chat_music() -> ChatMusic:
    return ChatMusic(
        compose_song=_compose_song(),
        answer_music_question=AnswerMusicQuestion(),
        reference_store=REFERENCE_STORE,
    )


def _reference_upload_root() -> Path:
    configured = getattr(get_settings(), "reference_upload_dir", None)
    return Path(configured).expanduser() if configured else REFERENCE_UPLOADS


def _reference_upload_max_bytes() -> int:
    return int(getattr(get_settings(), "reference_upload_max_bytes", 50 * 1024 * 1024))


@app.post("/compose", response_model=ComposeResponse)
def compose(req: ComposeRequest, request: Request) -> ComposeResponse:
    job = ARTIFACTS.create_job()
    try:
        song, source = _compose_song().compose(req.style)
    except ComposeConfigurationError as exc:
        raise HTTPException(status_code=503, detail=_compose_configuration_error_event(exc)) from exc
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
    # Non-stream path (`/compose`) still uses the legacy negotiator so a POST
    # that expects a full ComposeResponse keeps working. All streaming clients
    # (the UI's `/chat/stream`) go through the from-scratch band agent below.
    return ComposeSong(
        llm_configured=lambda: get_settings().llm_configured,
        negotiator=run_negotiation,
        event_streamer=_band_agent_event_streamer,
        canned=canned_song,
    )


def _band_agent_event_streamer(style: str) -> Iterator[tuple[dict, Optional[Part]]]:
    """Adapter: bridge `band_agent.stream_compose` (yields `(event, SongState)`)
    to the `ComposeSong.event_streamer` signature. The wrapper's contract is
    "any snapshot object", so passing SongState through is fine."""
    yield from band_agent_stream(style)


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
    except CancelledCompose:
        raise
    except ComposeConfigurationError as exc:
        yield _compose_configuration_error_event(exc)
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


def _compose_configuration_error_event(exc: ComposeConfigurationError) -> dict:
    return ErrorEvent(
        code=exc.code,
        message=exc.user_message,
        partial=False,
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
