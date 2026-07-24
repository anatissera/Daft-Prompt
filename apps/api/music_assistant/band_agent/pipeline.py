"""Research → Skeleton → Fill (parallel) → Compose pipeline.

Implemented as a LangGraph state graph. Emits SSE-compatible dict events
that the FastAPI layer wraps with `sse_data`. The event shapes are
identical to those the frontend already consumes.

Nodes:

  1. `do_research`  — deterministic: DDG search + corpus retrieval. No LLM.
  2. `do_skeleton`  — small LLM call: header + roster + chord progression.
  3. `do_fills`     — one LLM call per non-drum instrument, in parallel.
                      Drums are left empty (synthesised in compose).
  4. `do_compose`   — deterministic: BandSpec (skeleton + fills) → SongState.

Rationale for splitting: the local llama-server flakes when asked to emit a
single 500+-note structured output, and the total decode time scales with
the largest single call, not the sum. Splitting into ~4 smaller parallel
calls both keeps each response reliable and hides the per-instrument
decode behind the slowest one (with `-np N` slots on llama-server).
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Iterator, Optional, TypedDict

_log = logging.getLogger(__name__)

from langgraph.graph import END, StateGraph
from langchain_core.messages import HumanMessage, SystemMessage

from music_assistant.domain.song_state import SongState
from music_assistant.infrastructure.llm import make_llm

from .band_spec import (
    BandSkeleton,
    BandSpec,
    InstrumentDecl,
    InstrumentFill,
    IntentDecision,
    NotePlan,
    spec_from_skeleton,
)
from .prompts import (
    FILL_SYSTEM_PROMPT,
    INTENT_SYSTEM_PROMPT,
    SKELETON_SYSTEM_PROMPT,
    fill_user_prompt,
    intent_user_prompt,
    skeleton_user_prompt,
)
from .tools import (
    compose_band,
    deterministic_fill,
    download_midi,
    import_midi,
    infer_genre_from_titles,
    retrieve_corpus,
    search_midi_online,
    search_web,
)
from .tools.fallback_fill import llm_seeded_fill
from .tools.song_evidence import gather_song_evidence
from .tools.style_research import fetch_style_excerpts


class _AgentState(TypedDict, total=False):
    style: str
    intent: IntentDecision
    research: list[dict[str, Any]]
    excerpts: list[dict[str, Any]]
    song_evidence: dict[str, Any]
    corpus: dict[str, Any]
    inferred_genre: str
    skeleton: BandSkeleton
    fills: dict[str, list[NotePlan]]
    spec: BandSpec
    song: SongState
    replicate_failed: bool
    events: list[dict[str, Any]]


def _text_signals(hits: list[dict[str, Any]]) -> list[str]:
    """Flatten titles + host names from a search-hit list so `infer_genre_from_titles`
    can scan both. URLs of curated sites (e.g. `edm.com`) often carry the genre
    keyword even when the title doesn't."""
    out: list[str] = []
    for h in hits:
        out.append(h.get("title", "") or "")
        out.append(h.get("site", "") or "")
    return out


def _research_node(state: _AgentState) -> _AgentState:
    style = state.get("style", "")
    research = search_web(style)
    # Fetch the top result pages in a worker thread so it overlaps with the
    # corpus retrieval below. These excerpts are the ONLY real prose the
    # skeleton call sees about the style — titles alone tell the LLM nothing
    # about instrumentation. NOTE: not a `with` block — the context manager's
    # __exit__ joins all workers, which silently turned the 8s result timeout
    # into "wait for the slowest page anyway".
    pool = ThreadPoolExecutor(max_workers=2)
    excerpts_fut = pool.submit(fetch_style_excerpts, research)
    # Known-song evidence (MusicBrainz + tab/chord scrapers): only bites when
    # the prompt names a real song; genre prompts fail the match threshold
    # after one cheap API call.
    evidence_fut = pool.submit(gather_song_evidence, style)
    pool.shutdown(wait=False)
    corpus = retrieve_corpus(style)
    inferred_genre: str | None = None
    # The Lakh index is genre-tagged, not artist-tagged, so a prompt like
    # "marshmello" scores 0 overlap. Scan the web-result titles for a known
    # genre keyword and re-query — this typically recovers a real groove and
    # tempo prior without adding an LLM call.
    if not corpus.get("examples"):
        # The USER'S OWN WORDS win first: if the prompt names a known genre
        # ("tango", "reggaeton"), use it directly. Only then scan web titles
        # — title scanning used to let production-blog noise ("electronic
        # music production…") overrule an explicit "tango" in the prompt,
        # which filled the corpus with electronic exemplars.
        inferred_genre = infer_genre_from_titles([style])
        if inferred_genre is None:
            inferred_genre = infer_genre_from_titles(_text_signals(research))
        if inferred_genre is None:
            extra = search_web(f"{style} genre", decorate=False)
            inferred_genre = infer_genre_from_titles(_text_signals(extra))
        if inferred_genre:
            corpus = retrieve_corpus(inferred_genre)
    try:
        excerpts = excerpts_fut.result(timeout=8.0)
    except Exception:
        excerpts = []
    try:
        song_evidence = evidence_fut.result(timeout=14.0) or {}
    except Exception:
        song_evidence = {}
    events = state.get("events", []) + [
        {
            "type": "progress",
            "stage": "research",
            "message": (
                f"found {len(research)} web hits, read {len(excerpts)} pages; "
                f"{len(corpus.get('examples', []))} corpus exemplars"
                + (f" (via inferred genre: {inferred_genre})" if inferred_genre else "")
                + (
                    f"; song evidence: {song_evidence.get('song')} "
                    f"({len(song_evidence.get('claims', []))} claims)"
                    if song_evidence else ""
                )
            ),
        }
    ]
    return {
        "research": research,
        "excerpts": excerpts,
        "song_evidence": song_evidence,
        "corpus": corpus,
        "inferred_genre": inferred_genre or "",
        "events": events,
    }


def _skeleton_node(state: _AgentState) -> _AgentState:
    llm = make_llm(role="director").with_structured_output(BandSkeleton)
    messages = [
        SystemMessage(content=SKELETON_SYSTEM_PROMPT),
        HumanMessage(
            content=skeleton_user_prompt(
                state.get("style", ""),
                {"results": state.get("research", [])},
                state.get("corpus", {}),
                excerpts=state.get("excerpts") or None,
                song_evidence=state.get("song_evidence") or None,
                genre=state.get("inferred_genre") or state.get("style", ""),
            )
        ),
    ]
    # One-shot retry: langchain_openai's streaming JSON parser occasionally
    # dies mid-response with `Error in input stream` on openrouter.ai, or
    # returns None silently when the parse fails. Either aborts the compose
    # (SSE emits `compose_crashed`, UI shows "Chat failed"). Retrying once
    # almost always succeeds since the failure is a transient parse race.
    import time as _time
    skeleton: BandSkeleton | None = None
    last_exc: Exception | None = None
    # Three attempts: the parse-None flake has been observed to strike twice
    # in a row on m3; the third try costs nothing when the first succeeds.
    for attempt in (1, 2, 3):
        _t0 = _time.monotonic()
        try:
            skeleton = llm.invoke(messages)
            _log.info("skeleton TIMING attempt %d ok: %.1fs", attempt, _time.monotonic() - _t0)
        except Exception as exc:
            _log.warning("skeleton TIMING attempt %d FAIL: %.1fs", attempt, _time.monotonic() - _t0)
            _log.warning(
                "skeleton (attempt %d) raised: %s: %s", attempt, type(exc).__name__, exc,
            )
            last_exc = exc
            skeleton = None
        if skeleton is not None:
            break
        _log.warning("skeleton (attempt %d) returned None — retrying", attempt)
    if skeleton is None:
        # Re-raise the ORIGINAL exception so typed errors (LLMError et al.)
        # keep their meaning for the API layer, which maps them to proper
        # SSE error events instead of a generic compose_crashed.
        if last_exc is not None:
            raise last_exc
        raise RuntimeError(
            "skeleton LLM call returned no parsed output after 2 attempts — "
            "likely a provider streaming/parse flake. Try again."
        )
    # Audit trail: what did the director actually commit? Empty feel/plan or
    # missing grids are the leading indicator of a bland, colliding mix.
    _log.info(
        "skeleton commitments: feel=%dch plan=%dch grids={%s}",
        len(skeleton.rhythmic_feel or ""),
        len(skeleton.arrangement_plan or ""),
        ", ".join(
            f"{i.id}:{i.onset_grid or '-'}/{i.max_notes_per_bar or '∞'}"
            for i in skeleton.instruments
        ),
    )
    events = state.get("events", []) + [
        {
            "type": "progress",
            "stage": "skeleton",
            "message": (
                f"{skeleton.genre} @ {skeleton.tempo_bpm:.0f} BPM in {skeleton.key}, "
                f"{len(skeleton.instruments)} instruments, {skeleton.num_bars} bars"
            ),
        }
    ]
    return {"skeleton": skeleton, "events": events}


# How many fill LLM calls to run concurrently. Each fill unit is one
# (instrument, section-slice) pair — with 5-7 instruments × 2-3 slices that's
# 10-21 units. 16 puts essentially ALL units in flight at once, so the fills
# stage costs one slice-latency (~60-90s) instead of 3 sequential waves.
# Fine on flat-fee gateways (opencode.ai) and on llama-server (requests just
# queue at the server); drop to 3-4 on metered OpenRouter accounts where each
# in-flight call reserves max_tokens against the credit budget.
_FILL_MAX_WORKERS = 16


def _fills_node(state: _AgentState) -> _AgentState:
    skeleton = state["skeleton"]
    skeleton_ctx = skeleton.model_dump(mode="json", exclude={"instruments"})
    # Every fill sees the WHOLE band (roles + committed playing styles), not
    # just its own declaration — parallel-composed parts used to collide in
    # register and rhythm because each agent wrote blind. Compact projection
    # keeps the token cost small.
    skeleton_ctx["ensemble"] = [
        {
            "id": i.id,
            "instrument": i.instrument,
            "role": i.role,
            "playing_style": i.playing_style,
            "is_drum": i.is_drum,
        }
        for i in skeleton.instruments
    ]
    # Include drums now: the LLM writes GM percussion pitches from the
    # director's committed rhythmic_feel. If the drum fill fails at every
    # tier, `compose_band` still falls back to the corpus groove (or the
    # deterministic four-on-the-floor default) — so drums always play,
    # but the LLM gets to shape the groove first when it can.
    targets: list[InstrumentDecl] = list(skeleton.instruments)

    fills: dict[str, list[NotePlan]] = {}
    fallback_ids: list[str] = []
    targets_by_id = {inst.id: inst for inst in targets}
    if not targets:
        events = state.get("events", []) + [
            {"type": "progress", "stage": "fills", "message": "no instruments in skeleton"}
        ]
        return {"fills": fills, "events": events}

    # Flatten to (instrument, section-slice) work units so slices for the same
    # instrument run in parallel (not sequentially inside `_fill_one`). With
    # 5 instruments × 2-3 slices this is 10-15 tasks in the pool. The pool
    # cap bounds provider RPM; per-instrument aggregation happens after.
    sections = _sections_for_fill(skeleton_ctx)
    work: list[tuple[InstrumentDecl, dict[str, Any]]] = [
        (inst, sec) for inst in targets for sec in sections
    ]
    section_notes_by_inst: dict[str, list[NotePlan]] = {inst.id: [] for inst in targets}

    pool_size = min(_FILL_MAX_WORKERS, max(1, len(work)))
    with ThreadPoolExecutor(max_workers=pool_size) as pool:
        # Phase A: rich→minimal fill per (instrument, slice).
        section_futures = {
            pool.submit(_fill_section, skeleton_ctx, inst, sec): inst.id
            for inst, sec in work
        }
        for fut in as_completed(section_futures):
            inst_id = section_futures[fut]
            try:
                notes = fut.result()
                if notes:
                    section_notes_by_inst[inst_id].extend(notes)
            except Exception as exc:
                _log.info("fill section for %s: %s: %s", inst_id, type(exc).__name__, exc)

        # Phase B: for melodic instruments still empty, run seeded fallback
        # in parallel on the same pool.
        empty_melodic = [
            inst for inst in targets
            if not section_notes_by_inst[inst.id] and not inst.is_drum
        ]
        if empty_melodic:
            seeded_futures = {
                pool.submit(llm_seeded_fill, skeleton, inst, make_llm(role="instrument")): inst.id
                for inst in empty_melodic
            }
            for fut in as_completed(seeded_futures):
                inst_id = seeded_futures[fut]
                try:
                    seeded = fut.result()
                    if seeded:
                        section_notes_by_inst[inst_id].extend(seeded)
                except Exception as exc:
                    _log.info("seeded fill for %s: %s: %s", inst_id, type(exc).__name__, exc)

    # Phase C: aggregate + deterministic fallback for anyone still empty.
    for inst in targets:
        notes = section_notes_by_inst[inst.id]
        if notes:
            fills[inst.id] = notes
        else:
            _log.warning(
                "band_agent: all LLM tiers empty for %s — deterministic fallback", inst.id
            )
            fills[inst.id] = deterministic_fill(skeleton, targets_by_id[inst.id])
            fallback_ids.append(inst.id)

    llm_ok = sum(1 for iid, v in fills.items() if v and iid not in fallback_ids)
    events = state.get("events", []) + [
        {
            "type": "progress",
            "stage": "fills",
            "message": (
                f"filled {sum(1 for v in fills.values() if v)} / {len(targets)} instruments"
                + (
                    f" ({llm_ok} by LLM, {len(fallback_ids)} deterministic fallback: "
                    f"{', '.join(fallback_ids)})"
                    if fallback_ids else ""
                )
            ),
        }
    ]
    return {"fills": fills, "events": events}


from pydantic import BaseModel, Field as _Field

from .band_spec import NotePlan as _NotePlan


class _MinimalFill(BaseModel):
    """Stripped-down fill schema used as a retry when `InstrumentFill` can't
    be parsed — providers sometimes truncate JSON on the richer wrapper but
    complete a bare notes list. Retried automatically per section slice."""

    notes: list[_NotePlan] = _Field(default_factory=list)


_MAX_BARS_PER_SLICE = 12


def _slice_cap(num_bars: int) -> int:
    """Adaptive slice count. Short songs (≤23 bars) fit reliably in 2 slices —
    3 was overkill and added a whole extra LLM round-trip per instrument for
    no output-budget benefit. Long songs (≥24 bars) still get 3 to stay under
    per-call token limits."""
    if num_bars < 24:
        return 2
    return 3


def _sections_for_fill(skeleton_ctx: dict[str, Any]) -> list[dict[str, Any]]:
    """Return the bar-range slices to iterate over. Skeletons with many
    small sections (Intro/Verse/PreChorus/Chorus/Bridge/Outro = 6) would
    otherwise multiply LLM calls 6× per instrument. We cap to `_slice_cap`
    by merging adjacent sections into balanced chunks; a single-section
    skeleton still works through the same code path."""
    sections = skeleton_ctx.get("sections") or []
    num_bars = int(skeleton_ctx.get("num_bars") or 16)
    cap = _slice_cap(num_bars)
    if not sections:
        return _split_range(0, num_bars, name_prefix="all", cap=cap)
    slices = [
        {
            "name": s.get("name") or "section",
            "start_bar": int(s.get("start_bar", 0)),
            "end_bar": int(s.get("end_bar", 0)),
            "energy": s.get("energy") or "medium",
        }
        for s in sections
    ]
    if len(slices) <= cap:
        return slices
    total = sum(s["end_bar"] - s["start_bar"] for s in slices)
    target = max(1, total // cap)
    merged: list[dict[str, Any]] = []
    cur_name: list[str] = []
    cur_start = slices[0]["start_bar"]
    cur_end = cur_start
    for s in slices:
        cur_name.append(s["name"])
        cur_end = s["end_bar"]
        if cur_end - cur_start >= target and len(merged) < cap - 1:
            merged.append({
                "name": "+".join(cur_name),
                "start_bar": cur_start,
                "end_bar": cur_end,
                "energy": s.get("energy") or "medium",
            })
            cur_name = []
            cur_start = cur_end
    if cur_start < cur_end or not merged:
        merged.append({
            "name": "+".join(cur_name) if cur_name else "outro",
            "start_bar": cur_start,
            "end_bar": max(cur_end, cur_start + 1),
            "energy": "medium",
        })
    return merged


def _split_range(start: int, end: int, *, name_prefix: str, cap: int) -> list[dict[str, Any]]:
    """Break bar-range [start,end) into equal chunks capped at
    `_MAX_BARS_PER_SLICE` bars each, up to `cap` chunks."""
    length = end - start
    if length <= 0:
        return [{"name": name_prefix, "start_bar": start, "end_bar": max(end, start + 1), "energy": "medium"}]
    n = max(1, min(cap, (length + _MAX_BARS_PER_SLICE - 1) // _MAX_BARS_PER_SLICE))
    chunk = (length + n - 1) // n
    out: list[dict[str, Any]] = []
    for i in range(n):
        s = start + i * chunk
        e = min(end, s + chunk)
        if s >= e:
            break
        out.append({
            "name": f"{name_prefix}_{i + 1}",
            "start_bar": s,
            "end_bar": e,
            "energy": "medium",
        })
    return out


def _fill_section(
    skeleton_ctx: dict[str, Any],
    instrument: InstrumentDecl,
    section: dict[str, Any],
) -> list[NotePlan]:
    """Compose one (instrument, section) unit. Returns notes clipped to the
    slice bar-range, or an empty list if both rich and minimal schemas failed.
    Per-unit granularity is what lets `_fills_node` run slices for the same
    instrument in parallel — the previous `_fill_one` iterated slices in a
    for-loop, which is what dominated the 800s walltime."""
    start = int(section.get("start_bar", 0))
    end = int(section.get("end_bar", start))
    if end <= start:
        return []
    llm = make_llm(role="instrument")
    rich = llm.with_structured_output(InstrumentFill)
    minimal = llm.with_structured_output(_MinimalFill)
    inst_json = instrument.model_dump(mode="json")
    prompt_kwargs = dict(
        bar_start=start,
        bar_end=end,
        section_name=section.get("name") or "",
        section_energy=section.get("energy") or "",
    )
    msgs = [
        SystemMessage(content=FILL_SYSTEM_PROMPT),
        HumanMessage(content=fill_user_prompt(skeleton_ctx, inst_json, **prompt_kwargs)),
    ]

    import time as _time

    # Rich schema first; empty is legitimate (a lead can rest through an
    # intro), so we only retry with the lean schema when rich actually THREW.
    t0 = _time.monotonic()
    try:
        fill_rich: InstrumentFill = rich.invoke(msgs)
        notes = _clip_notes(fill_rich.notes, start, end)
        _log.info(
            "fill TIMING rich ok %s bars %d-%d: %.1fs, %d notes",
            instrument.id, start, end - 1, _time.monotonic() - t0, len(notes),
        )
        return notes
    except Exception as exc:
        _log.warning(
            "fill TIMING rich FAIL %s bars %d-%d: %.1fs, %s: %s",
            instrument.id, start, end - 1, _time.monotonic() - t0,
            type(exc).__name__, str(exc)[:300],
        )

    t0 = _time.monotonic()
    try:
        fill_min: _MinimalFill = minimal.invoke(msgs)
        notes = _clip_notes(fill_min.notes, start, end)
        _log.info(
            "fill TIMING minimal ok %s bars %d-%d: %.1fs, %d notes",
            instrument.id, start, end - 1, _time.monotonic() - t0, len(notes),
        )
        return notes
    except Exception as exc:
        _log.warning(
            "fill TIMING minimal FAIL %s bars %d-%d: %.1fs, %s: %s",
            instrument.id, start, end - 1, _time.monotonic() - t0,
            type(exc).__name__, str(exc)[:300],
        )
        return []


def _clip_notes(notes: list[NotePlan], start_bar: int, end_bar: int) -> list[NotePlan]:
    """Drop any notes the model emitted outside the requested section range —
    models occasionally leak notes for other bars into a section slice; we
    prune them so concatenation doesn't double-emit bars."""
    return [n for n in notes if start_bar <= n.bar < end_bar]


def _compose_node(state: _AgentState) -> _AgentState:
    skeleton = state["skeleton"]
    fills = state.get("fills", {})
    spec = spec_from_skeleton(skeleton, fills)
    groove = (state.get("corpus") or {}).get("groove")
    song = compose_band(spec, request=state.get("style", ""), groove=groove)
    return {"spec": spec, "song": song}


# --------------------------------------------------------------------------
# Intent classification: one small LLM call decides whether the user is
# asking to reproduce a specific song ("replicate") or to compose in a style
# ("compose"). This replaces a brittle regex router: users write prompts in
# Spanish/English/mixed, with typos, quoted titles, weird verb choices, and
# implicit references ("hazme viva la vida" is replicate; "hazme algo como
# viva la vida" is compose). A tiny LLM handles that space; a regex can't.
# --------------------------------------------------------------------------


def _intent_node(state: _AgentState) -> _AgentState:
    import time as _time
    prompt = state.get("style", "")
    llm = make_llm(role="director").with_structured_output(IntentDecision)
    messages = [
        SystemMessage(content=INTENT_SYSTEM_PROMPT),
        HumanMessage(content=intent_user_prompt(prompt)),
    ]
    _t0 = _time.monotonic()
    try:
        decision: IntentDecision = llm.invoke(messages)
        _log.info("intent TIMING: %.1fs", _time.monotonic() - _t0)
    except Exception:
        # If the classifier hiccups, fall through to compose — replicate is
        # the more expensive path (external HTTP + no re-generation), so
        # failing safe means we still produce a song.
        decision = IntentDecision(intent="compose", target=None)
    events = state.get("events", []) + [
        {
            "type": "progress",
            "stage": "intent",
            "message": (
                f"intent={decision.intent}"
                + (f" target='{decision.target}'" if decision.target else "")
            ),
        }
    ]
    return {"intent": decision, "events": events}


# --------------------------------------------------------------------------
# Replicate path: agent decided this is a "reproduce specific song" ask →
# search Bitmidi, download, import verbatim. Skips skeleton + fills — the
# LLM has nothing to add on top of a real transcription.
# --------------------------------------------------------------------------


def _replicate_node(state: _AgentState) -> _AgentState:
    from music_assistant.infrastructure.web_research.entity_resolution import (
        token_similarity,
    )

    prompt = state.get("style", "")
    decision = state.get("intent")
    query = (decision.target if decision else "") or prompt
    events = list(state.get("events", []))
    hits = search_midi_online(query, limit=3)
    # Bitmidi's search is fuzzy and its catalog is thin outside anglo
    # repertoire — a Cerati request once matched a Star Wars MIDI because
    # we took hits[0] blindly. Require real title overlap with the target;
    # a mismatch is a MISS (compose fallback), not a shrug.
    candidates = []
    if hits:
        scored = sorted(
            ((token_similarity(query, h.title), h) for h in hits),
            key=lambda t: -t[0],
        )
        _log.warning(
            "replicate: query %r → candidates %s",
            query,
            [(round(s, 2), h.title) for s, h in scored],
        )
        candidates = [h for s, h in scored if s >= 0.45]
    if not candidates:
        events.append({
            "type": "progress",
            "stage": "replicate_miss",
            "message": (
                f"no MIDI matching '{query}' on Bitmidi"
                + (f" (best candidate was '{hits[0].title}' — rejected)" if hits else "")
                + " — falling back to compose"
            ),
        })
        # Signal to the router: no song yet, and skeleton/fills should run.
        return {"events": events, "replicate_failed": True}

    # Try candidates in score order: wild MIDI files are frequently corrupt
    # (truncated tracks, bytes >127 — "Smells Like Teen Spirit" hit both),
    # so a failed download OR a failed import moves on to the next match
    # instead of crashing the whole request.
    for chosen in candidates:
        events.append({
            "type": "progress",
            "stage": "replicate_hit",
            "message": f"downloading '{chosen.title}' from Bitmidi",
        })
        try:
            path = download_midi(chosen)
            if path is None:
                raise RuntimeError("download failed")
            song = import_midi(path, request=prompt)
        except Exception as exc:
            _log.warning(
                "replicate: %r unusable (%s: %s) — trying next candidate",
                chosen.title, type(exc).__name__, exc,
            )
            events.append({
                "type": "progress",
                "stage": "replicate_retry",
                "message": f"'{chosen.title}' is corrupt — trying the next match",
            })
            continue
        events.append({
            "type": "progress",
            "stage": "replicate_done",
            "message": (
                f"imported {len(song.roster)} tracks, "
                f"{sum(len(p.notes) for p in song.parts.values())} notes"
            ),
        })
        return {"song": song, "events": events}

    events.append({
        "type": "progress",
        "stage": "replicate_miss",
        "message": "every matching MIDI was corrupt — falling back to compose",
    })
    return {"events": events, "replicate_failed": True}


def _route_after_intent(state: _AgentState) -> str:
    """LangGraph conditional edge: use the classifier's decision to pick
    between the replicate flow and the from-scratch compose flow."""
    decision = state.get("intent")
    if decision and decision.intent == "replicate" and decision.target:
        return "do_replicate"
    return "do_research"


def _route_after_replicate(state: _AgentState) -> str:
    """If Bitmidi missed, fall through to compose (research → skeleton → …)
    so the user still gets a song. Otherwise we're done."""
    if state.get("replicate_failed"):
        return "do_research"
    return END


def _build_graph():
    g = StateGraph(_AgentState)
    g.add_node("do_intent", _intent_node)
    g.add_node("do_replicate", _replicate_node)
    g.add_node("do_research", _research_node)
    g.add_node("do_skeleton", _skeleton_node)
    g.add_node("do_fills", _fills_node)
    g.add_node("do_compose", _compose_node)
    g.set_entry_point("do_intent")
    g.add_conditional_edges("do_intent", _route_after_intent, {
        "do_replicate": "do_replicate",
        "do_research": "do_research",
    })
    g.add_conditional_edges("do_replicate", _route_after_replicate, {
        "do_research": "do_research",
        END: END,
    })
    g.add_edge("do_research", "do_skeleton")
    g.add_edge("do_skeleton", "do_fills")
    g.add_edge("do_fills", "do_compose")
    g.add_edge("do_compose", END)
    return g.compile()


_GRAPH = None


def _graph():
    global _GRAPH
    if _GRAPH is None:
        _GRAPH = _build_graph()
    return _GRAPH


def _director_event(song: SongState) -> dict[str, Any]:
    return {
        "type": "director",
        "source": "director",
        "header": song.header.model_dump(mode="json"),
        "roster": [item.model_dump(mode="json") for item in song.roster],
    }


def stream_compose(style: str) -> Iterator[tuple[dict[str, Any], Optional[SongState]]]:
    """Yield `(event, song_snapshot)` pairs matching the `ComposeSong.event_streamer`
    contract, so the FastAPI stream handler stays unchanged.

    Uses langgraph's `stream(mode="updates")` so progress events reach the SSE
    client AS EACH NODE FINISHES rather than piled up at the end. Without this,
    the browser (and Vercel's 300 s route maxDuration) would time out waiting
    for the first byte of progress even though the pipeline is running fine.

    Order (typical compose path):
      1. `progress[research]` — after `_research_node`.
      2. `progress[skeleton]` — after `_skeleton_node`.
      3. `progress[fills]`    — after `_fills_node`.
      4. `director`           — header + roster; carries the final song snapshot.
      5. sentinel `({}, song)` so the caller renders artifacts + emits `done`.
    """
    initial: _AgentState = {"style": style, "events": []}
    emitted: set[int] = set()
    final_state: _AgentState = {}
    for update in _graph().stream(initial, stream_mode="values"):
        # `stream_mode="values"` yields the accumulated state after each node.
        # We diff against events already sent so the same progress line isn't
        # emitted twice as later nodes echo the earlier `events` list.
        final_state = update  # type: ignore[assignment]
        for ev in update.get("events", []):
            key = id(ev)
            if key in emitted:
                continue
            emitted.add(key)
            yield ev, None

    song = final_state.get("song")
    if song is not None:
        yield _director_event(song), song
        yield {}, song
