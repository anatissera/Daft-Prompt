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

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Iterator, Optional, TypedDict

from langgraph.graph import END, StateGraph
from langchain_core.messages import HumanMessage, SystemMessage

from music_assistant.domain.song_state import SongState
from music_assistant.infrastructure.llm import make_llm

from .band_spec import (
    BandSkeleton,
    BandSpec,
    InstrumentDecl,
    InstrumentFill,
    NotePlan,
    spec_from_skeleton,
)
from .prompts import (
    FILL_SYSTEM_PROMPT,
    SKELETON_SYSTEM_PROMPT,
    fill_user_prompt,
    skeleton_user_prompt,
)
from .tools import (
    compose_band,
    infer_genre_from_titles,
    retrieve_corpus,
    search_web,
)


class _AgentState(TypedDict, total=False):
    style: str
    research: list[dict[str, Any]]
    corpus: dict[str, Any]
    skeleton: BandSkeleton
    fills: dict[str, list[NotePlan]]
    spec: BandSpec
    song: SongState
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


# How many per-instrument fill calls to run concurrently. Local llama-server
# usually has 1-2 slots (`-np 1|2`); above that it serialises internally.
# Kept small so we don't oversubscribe the model.
_FILL_MAX_WORKERS = 4


def _fills_node(state: _AgentState) -> _AgentState:
    skeleton = state["skeleton"]
    skeleton_ctx = skeleton.model_dump(mode="json", exclude={"instruments"})
    targets: list[InstrumentDecl] = [
        i for i in skeleton.instruments if not i.is_drum
    ]

    fills: dict[str, list[NotePlan]] = {}
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
                    fills[inst_id] = fill.notes
                except Exception:
                    # A single failed fill leaves that instrument silent
                    # instead of crashing the whole song. The rest of the
                    # arrangement is still musically coherent.
                    fills[inst_id] = []

    events = state.get("events", []) + [
        {
            "type": "progress",
            "stage": "fills",
            "message": (
                f"filled {sum(1 for v in fills.values() if v)} / {len(targets)} instruments"
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


def _build_graph():
    g = StateGraph(_AgentState)
    g.add_node("do_research", _research_node)
    g.add_node("do_skeleton", _skeleton_node)
    g.add_node("do_fills", _fills_node)
    g.add_node("do_compose", _compose_node)
    g.set_entry_point("do_research")
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
