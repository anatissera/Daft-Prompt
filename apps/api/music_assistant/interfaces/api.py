"""FastAPI HTTP interface."""

from __future__ import annotations

import json
import uuid
import re
import time
from functools import lru_cache
from importlib.util import find_spec
from dotenv import load_dotenv

load_dotenv()
from inspect import signature
from pathlib import Path
from queue import Empty, Queue
from threading import Thread
from typing import Iterator

from fastapi import BackgroundTasks, FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse

from music_assistant.application.analyze_reference import AnalyzeReference, enrich_profile_with_transcription
from music_assistant.application.answer_music_question import AnswerMusicQuestion, LLMGroundedMusicQuestionExplainer
from music_assistant.application.chat_music import ChatMusic
from music_assistant.application.compose_song import ComposeConfigurationError, ComposeSong
from music_assistant.application.language import is_spanish
from music_assistant.application.reference_instruments import ReferenceInstrumentProfileBuilder
from music_assistant.application.research_reference import ResearchReference
from music_assistant.canned import canned_song
from music_assistant.config import get_settings
from music_assistant.domain.audio_profile import ReferenceProfile, ReferenceSource
from music_assistant.domain.song_state import Part
from music_assistant.graph import iter_negotiation_events, revise_instrument_part, run_negotiation
from music_assistant.infrastructure.mir.deep_harmonic_analyzer import DeepHarmonicAnalyzer
from music_assistant.infrastructure.mir.demucs_separator import DemucsSeparator
from music_assistant.infrastructure.mir.basic_pitch_transcriber import BasicPitchTranscriber
from music_assistant.infrastructure.storage.in_memory_reference_store import InMemoryReferenceStore
from music_assistant.infrastructure.storage.in_memory_songsterr_tab_store import InMemorySongsterrTabStore
from music_assistant.infrastructure.storage.render_artifacts import render_artifacts
from music_assistant.infrastructure.storage.local_store import LocalArtifactStore
from music_assistant.infrastructure.web_research.researcher import ConnectorSongResearcher, DefaultSongResearcher
from music_assistant.infrastructure.web_research.search import BroadMusicWebSearch
from music_assistant.infrastructure.llm import LLMAllProvidersFailed, LLMError, make_llm
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

OUTPUTS = Path(__file__).resolve().parents[2] / "outputs"
REFERENCE_UPLOADS = Path(__file__).resolve().parents[2] / "uploads"
ARTIFACTS = LocalArtifactStore(OUTPUTS)
REFERENCE_STORE = InMemoryReferenceStore()
SONGSTERR_TAB_STORE = InMemorySongsterrTabStore()
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
    return {"status": "ok", "commit": _build_commit()}


def _build_commit() -> str:
    try:
        return str(json.loads(Path("/app/build-info.json").read_text())["commit"])
    except (OSError, KeyError, TypeError, ValueError):
        return "development-worktree"


@app.post("/references/analyze", response_model=ReferenceProfile)
async def analyze_reference_upload(file: UploadFile | None = File(None)) -> ReferenceProfile:
    _require_audio_analysis()
    source = await _store_reference_upload(file)
    try:
        profile = AnalyzeReference(_reference_analyzer(), transcriber=_reference_transcriber()).execute(source)
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
    _require_audio_analysis()
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


@app.get("/references/{reference_id}", response_model=ReferenceProfile)
def get_reference(reference_id: str) -> ReferenceProfile:
    profile = REFERENCE_STORE.get(reference_id)
    if profile is None:
        raise HTTPException(status_code=404, detail=f"reference_id not found: {reference_id}")
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


@app.get("/references/{reference_id}/instrument-profiles")
def reference_instrument_profiles(reference_id: str) -> dict:
    profile = REFERENCE_STORE.get(reference_id)
    if profile is None:
        raise HTTPException(status_code=404, detail=f"reference_id not found: {reference_id}")
    profiles = ReferenceInstrumentProfileBuilder(songsterr_tab_store=SONGSTERR_TAB_STORE).build(profile)
    return {
        "reference_id": reference_id,
        "profiles": [_compact_instrument_profile(item) for item in profiles.values()],
    }


def _compact_instrument_profile(profile) -> dict:
    memory = profile.musical_memory
    return {
        "instrument_family": profile.instrument_family,
        "track_name": profile.track_name,
        "confidence": profile.confidence,
        "timbre": profile.timbre.model_dump(mode="json"),
        "pattern": profile.pattern.model_dump(mode="json"),
        "musical_memory_summary": memory.summary,
        "note_packs": [
            {
                "note_pack_id": pack.pack_id,
                "section_name": pack.section_name,
                "start_bar": pack.start_bar,
                "bar_count": pack.bar_count,
                "note_count": len(pack.notes),
            }
            for pack in memory.note_packs
        ],
        "motifs": [motif.model_dump(mode="json") for motif in memory.motifs],
        "harmonic_context": memory.harmonic_context.model_dump(mode="json"),
        "evidence": profile.evidence,
        "uncertainty_notes": profile.uncertainty_notes,
    }


@lru_cache(maxsize=1)
def _song_researcher() -> ConnectorSongResearcher:
    return ConnectorSongResearcher(
        songsterr_tab_store=SONGSTERR_TAB_STORE,
        broad_researcher=DefaultSongResearcher(search=BroadMusicWebSearch()),
    )


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

    def progress(
        stage: str,
        message: str,
        *,
        status: str = "started",
        elapsed_seconds: float | None = None,
        cache_hit: bool | None = None,
    ) -> None:
        events.put(
            AnalysisProgressEvent(
                type=stage,
                message=message,
                status=status,
                elapsed_seconds=elapsed_seconds,
                cache_hit=cache_hit,
            ).model_dump(mode="json")
        )

    def worker() -> None:
        analyzer = _reference_analyzer()
        try:
            # Same enrichment as the blocking endpoint (AnalyzeReference): the
            # streamed profile must also carry the SongKnowledgeProfile with
            # audio evidence claims, or chat Q&A falls back to legacy answers.
            profile = enrich_profile_with_transcription(
                _analyze_with_progress(analyzer, source, progress), source, _reference_transcriber()
            )
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
    settings = get_settings()
    upload_root = _reference_upload_root()
    configured_cache_root = getattr(settings, "reference_stem_cache_dir", None)
    separator = DemucsSeparator(
        output_root=upload_root,
        cache_enabled=bool(
            getattr(settings, "reference_stem_cache_enabled", False)
        ),
        cache_root=(
            Path(configured_cache_root).expanduser()
            if configured_cache_root
            else upload_root / ".stem-cache"
        ),
    )
    return DeepHarmonicAnalyzer(output_root=upload_root, separator=separator)


def _require_audio_analysis() -> None:
    setup = (
        "Start with `docker compose -f docker-compose.yml -f docker-compose.audio.yml up --build` "
        "to enable uploads, Demucs, and MIR analysis."
    )
    if not bool(getattr(get_settings(), "enable_audio_analysis", False)):
        raise HTTPException(
            status_code=503,
            detail=f"Local audio analysis is optional and is not enabled in this runtime. {setup}",
        )
    required_modules = ("librosa", "soundfile", "demucs", "torch", "torchaudio")
    missing = [name for name in required_modules if find_spec(name) is None]
    if missing:
        raise HTTPException(
            status_code=503,
            detail=(
                f"Local audio analysis is enabled but its optional runtime is incomplete ({', '.join(missing)}). "
                f"{setup}"
            ),
        )


def _reference_transcriber() -> BasicPitchTranscriber | None:
    if not bool(getattr(get_settings(), "enable_melody_transcription", False)):
        return None
    return BasicPitchTranscriber()


@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest, request: Request, background_tasks: BackgroundTasks) -> ChatResponse:
    if req.reference_id and REFERENCE_STORE.get(req.reference_id) is None:
        raise HTTPException(status_code=404, detail=f"reference_id not found: {req.reference_id}")
    try:
        response = _chat_music().handle(req)
    except ComposeConfigurationError as exc:
        event = _compose_configuration_error_event(exc)
        return ChatResponse(intent="clarify", reply=event["message"], clarification=event["message"], error=event)
    except LLMError as exc:
        event = _llm_error_event(exc, partial=False)
        message = _chat_error_reply(req.message, event)
        return ChatResponse(intent="clarify", reply=message, clarification=message, error=event)

    # If the orchestrator composed a song, render audio/score artifacts and
    # attach URLs so the chat UI can play / score / download — same contract
    # the dedicated /compose endpoint uses.
    if response.compose is not None:
        from music_assistant.application.chat_music import ChatArtifacts
        job = ARTIFACTS.create_job()
        base = str(request.base_url).rstrip("/")
        response = response.model_copy(update={
            "compose": response.compose.model_copy(update={
                "artifacts": ChatArtifacts(
                    midi=ARTIFACTS.url_for(base, job.job_id, "song.mid"),
                    musicxml=ARTIFACTS.url_for(base, job.job_id, "song.musicxml"),
                ),
            }),
        })
        # FastAPI runs this after the response has been sent. SongState powers
        # immediate local playback; notation/export generation is an attachment.
        background_tasks.add_task(_render_artifacts_safely, response.compose.song, job.path)
    return response


def _render_artifacts_safely(song, job_path: Path) -> None:
    try:
        render_artifacts(song, job_path)
    except Exception:
        # MIDI is best-effort here too: the response still carries canonical
        # SongState, which the browser can play and export independently.
        return


def _chat_music() -> ChatMusic:
    chat_model = _chat_model()
    explainer = (
        LLMGroundedMusicQuestionExplainer(chat_model, songsterr_tab_store=SONGSTERR_TAB_STORE)
        if chat_model is not None
        else None
    )
    return ChatMusic(
        compose_song=_compose_song(),
        answer_music_question=AnswerMusicQuestion(explainer, songsterr_tab_store=SONGSTERR_TAB_STORE),
        reference_store=REFERENCE_STORE,
        chat_model=chat_model,
        song_researcher=_song_researcher(),
        songsterr_tab_store=SONGSTERR_TAB_STORE,
        enable_web_research=bool(getattr(get_settings(), "enable_web_research", False)),
    )


def _chat_model():
    try:
        return make_llm("chat")
    except RuntimeError:
        return None


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
    return ComposeSong(
        llm_configured=lambda: get_settings().llm_configured,
        negotiator=run_negotiation,
        event_streamer=iter_negotiation_events,
        instrument_reviser=revise_instrument_part,
        canned=canned_song,
    )


def _compose_stream_events(req: ComposeRequest, job_id: str, job_dir: Path, base: str) -> Iterator[dict]:
    started_at = time.monotonic()
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
            yield DoneEvent(
                job_id=job_id,
                source=source,
                song=song_snapshot,
                artifacts=artifacts,
                elapsed_seconds=round(time.monotonic() - started_at, 3),
            ).model_dump(
                by_alias=True, mode="json"
            )
            return
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
        yield DoneEvent(
            job_id=job_id,
            source=last_source,
            song=last_song,
            artifacts=artifacts,
            elapsed_seconds=round(time.monotonic() - started_at, 3),
        ).model_dump(
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
        yield DoneEvent(
            job_id=job_id,
            source=last_source,
            song=last_song,
            artifacts=artifacts,
            elapsed_seconds=round(time.monotonic() - started_at, 3),
        ).model_dump(
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


_COMPOSE_CHAT_RE = re.compile(
    r"\b(compose|generate|make|write|create|sketch|produce|compon[eé]|gener[aá]|cre[aá]|hac[eé])\b",
    re.IGNORECASE,
)


def _chat_error_reply(message: str, event: dict) -> str:
    if _COMPOSE_CHAT_RE.search(message):
        return (
            "No pude componer porque el proveedor LLM no está disponible."
            if is_spanish(message)
            else "I could not compose because the LLM provider is unavailable."
        )
    return str(event["message"])


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
