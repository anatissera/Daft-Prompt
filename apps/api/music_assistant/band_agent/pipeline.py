"""Research → Plan → Compose pipeline, implemented as a LangGraph state graph.

Emits SSE-compatible dict events that the FastAPI layer wraps with `sse_data`.
The event shapes are identical to those the frontend already consumes from
the legacy negotiation stream:

  - `{"type": "director", "source": "director", "header": ..., "roster": ...}`
  - `{"type": "progress", "stage": ..., "message": ...}`   (new, optional UI)
  - final: caller yields a `DoneEvent` after `render_artifacts`.

The graph nodes are:

  1. `research` — deterministic: DDG search + corpus retrieval. No LLM.
  2. `plan`     — LLM structured-output call producing a `BandSpec`.
  3. `compose`  — deterministic: `BandSpec` → `SongState`.
"""

from __future__ import annotations

from typing import Any, Iterator, Optional, TypedDict

from langgraph.graph import END, StateGraph
from langchain_core.messages import HumanMessage, SystemMessage

from music_assistant.domain.song_state import SongState
from music_assistant.infrastructure.llm import make_llm

from .band_spec import BandSpec
from .prompts import SYSTEM_PROMPT, user_prompt
from .tools import compose_band, retrieve_corpus, search_web


class _AgentState(TypedDict, total=False):
    style: str
    research: list[dict[str, Any]]
    corpus: dict[str, Any]
    spec: BandSpec
    song: SongState
    events: list[dict[str, Any]]


def _research_node(state: _AgentState) -> _AgentState:
    style = state.get("style", "")
    research = search_web(style)
    corpus = retrieve_corpus(style)
    events = state.get("events", []) + [
        {
            "type": "progress",
            "stage": "research",
            "message": (
                f"found {len(research)} web hits; "
                f"{len(corpus.get('examples', []))} corpus exemplars"
            ),
        }
    ]
    return {"research": research, "corpus": corpus, "events": events}


def _plan_node(state: _AgentState) -> _AgentState:
    llm = make_llm(role="director").with_structured_output(BandSpec)
    messages = [
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(
            content=user_prompt(
                state.get("style", ""),
                {"results": state.get("research", [])},
                state.get("corpus", {}),
            )
        ),
    ]
    spec: BandSpec = llm.invoke(messages)
    events = state.get("events", []) + [
        {
            "type": "progress",
            "stage": "planned",
            "message": (
                f"{spec.genre} @ {spec.tempo_bpm:.0f} BPM in {spec.key}, "
                f"{len(spec.instruments)} instruments, {spec.num_bars} bars"
            ),
        }
    ]
    return {"spec": spec, "events": events}


def _compose_node(state: _AgentState) -> _AgentState:
    spec = state["spec"]
    song = compose_band(spec, request=state.get("style", ""))
    return {"song": song}


def _build_graph():
    g = StateGraph(_AgentState)
    g.add_node("do_research", _research_node)
    g.add_node("do_plan", _plan_node)
    g.add_node("do_compose", _compose_node)
    g.set_entry_point("do_research")
    g.add_edge("do_research", "do_plan")
    g.add_edge("do_plan", "do_compose")
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
      2. `progress[planned]`  — LLM has returned a BandSpec.
      3. `director`           — header + roster; carries the final song snapshot.
      4. sentinel `({}, song)` so the caller renders artifacts + emits `done`.
    """
    initial: _AgentState = {"style": style, "events": []}
    final: _AgentState = _graph().invoke(initial)  # type: ignore[assignment]

    for ev in final.get("events", []):
        yield ev, None

    song = final["song"]
    yield _director_event(song), song
    yield {}, song
