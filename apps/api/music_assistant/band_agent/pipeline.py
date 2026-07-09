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


class _AgentState(TypedDict, total=False):
    style: str
    intent: IntentDecision
    research: list[dict[str, Any]]
    corpus: dict[str, Any]
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
    corpus = retrieve_corpus(style)
    inferred_genre: str | None = None
    # The Lakh index is genre-tagged, not artist-tagged, so a prompt like
    # "marshmello" scores 0 overlap. Scan the web-result titles for a known
    # genre keyword and re-query — this typically recovers a real groove and
    # tempo prior without adding an LLM call.
    if not corpus.get("examples"):
        # Try titles from the original search first; if that's silent, do a
        # cheap second query biased toward genre pages ("<query> genre").
        inferred_genre = infer_genre_from_titles(
            _text_signals(research + [{"title": style}])
        )
        if inferred_genre is None:
            extra = search_web(f"{style} genre", decorate=False)
            inferred_genre = infer_genre_from_titles(_text_signals(extra))
        if inferred_genre:
            corpus = retrieve_corpus(inferred_genre)
    events = state.get("events", []) + [
        {
            "type": "progress",
            "stage": "research",
            "message": (
                f"found {len(research)} web hits; "
                f"{len(corpus.get('examples', []))} corpus exemplars"
                + (f" (via inferred genre: {inferred_genre})" if inferred_genre else "")
            ),
        }
    ]
    return {"research": research, "corpus": corpus, "events": events}


def _skeleton_node(state: _AgentState) -> _AgentState:
    llm = make_llm(role="director").with_structured_output(BandSkeleton)
    messages = [
        SystemMessage(content=SKELETON_SYSTEM_PROMPT),
        HumanMessage(
            content=skeleton_user_prompt(
                state.get("style", ""),
                {"results": state.get("research", [])},
                state.get("corpus", {}),
            )
        ),
    ]
    skeleton: BandSkeleton = llm.invoke(messages)
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


# How many per-instrument fill calls to run concurrently. 4 works well on
# Gemini free-tier (15 RPM headroom) and llama-server (4 slots). Drop to
# 1-2 on tight OpenRouter accounts where each in-flight call reserves
# max_tokens against the credit budget.
_FILL_MAX_WORKERS = 4


def _fills_node(state: _AgentState) -> _AgentState:
    skeleton = state["skeleton"]
    skeleton_ctx = skeleton.model_dump(mode="json", exclude={"instruments"})
    targets: list[InstrumentDecl] = [
        i for i in skeleton.instruments if not i.is_drum
    ]

    fills: dict[str, list[NotePlan]] = {}
    fallback_ids: list[str] = []
    targets_by_id = {inst.id: inst for inst in targets}
    if targets:
        with ThreadPoolExecutor(max_workers=min(_FILL_MAX_WORKERS, len(targets))) as pool:
            futures = {
                pool.submit(_fill_one, skeleton_ctx, inst): inst.id
                for inst in targets
            }
            for fut in as_completed(futures):
                inst_id = futures[fut]
                try:
                    fill: InstrumentFill = fut.result()
                    if not fill.notes:
                        raise ValueError("empty note list")
                    fills[inst_id] = fill.notes
                except Exception as exc:
                    _log.warning(
                        "band_agent: fill for %s failed (%s: %s) — using deterministic fallback",
                        inst_id, type(exc).__name__, exc,
                    )
                    fills[inst_id] = deterministic_fill(skeleton, targets_by_id[inst_id])
                    fallback_ids.append(inst_id)

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


def _fill_one(skeleton_ctx: dict[str, Any], instrument: InstrumentDecl) -> InstrumentFill:
    llm = make_llm(role="instrument").with_structured_output(InstrumentFill)
    messages = [
        SystemMessage(content=FILL_SYSTEM_PROMPT),
        HumanMessage(
            content=fill_user_prompt(
                skeleton_ctx,
                instrument.model_dump(mode="json"),
            )
        ),
    ]
    return llm.invoke(messages)


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
    prompt = state.get("style", "")
    llm = make_llm(role="director").with_structured_output(IntentDecision)
    messages = [
        SystemMessage(content=INTENT_SYSTEM_PROMPT),
        HumanMessage(content=intent_user_prompt(prompt)),
    ]
    try:
        decision: IntentDecision = llm.invoke(messages)
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
    prompt = state.get("style", "")
    decision = state.get("intent")
    query = (decision.target if decision else "") or prompt
    events = list(state.get("events", []))
    hits = search_midi_online(query, limit=3)
    if not hits:
        events.append({
            "type": "progress",
            "stage": "replicate_miss",
            "message": f"no MIDI found on Bitmidi for '{query}' — falling back to compose",
        })
        # Signal to the router: no song yet, and skeleton/fills should run.
        return {"events": events, "replicate_failed": True}
    chosen = hits[0]
    events.append({
        "type": "progress",
        "stage": "replicate_hit",
        "message": f"downloading '{chosen.title}' from Bitmidi",
    })
    path = download_midi(chosen)
    if path is None:
        events.append({
            "type": "progress",
            "stage": "replicate_miss",
            "message": "download failed — falling back to compose",
        })
        return {"events": events, "replicate_failed": True}
    song = import_midi(path, request=prompt)
    events.append({
        "type": "progress",
        "stage": "replicate_done",
        "message": (
            f"imported {len(song.roster)} tracks, "
            f"{sum(len(p.notes) for p in song.parts.values())} notes"
        ),
    })
    return {"song": song, "events": events}


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

    Order:
      1. `progress[research]` — research is done, no song yet.
      2. `progress[skeleton]` — skeleton LLM call finished.
      3. `progress[fills]`    — per-instrument fills finished.
      4. `director`           — header + roster; carries the final song snapshot.
      5. sentinel `({}, song)` so the caller renders artifacts + emits `done`.
    """
    initial: _AgentState = {"style": style, "events": []}
    final: _AgentState = _graph().invoke(initial)  # type: ignore[assignment]

    for ev in final.get("events", []):
        yield ev, None

    song = final["song"]
    yield _director_event(song), song
    yield {}, song
