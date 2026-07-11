"""From-scratch band-composition agent.

A single-LLM-call planner: it receives the user prompt, deterministic web
research + corpus digest, and returns a fully-specified `BandSpec` that a
deterministic `compose_band` step materialises into a `SongState`.

This replaces the multi-agent negotiation graph (`music_assistant.agents` +
`music_assistant.graph`). The rest of the pipeline (frontend SSE contract,
render_midi, finalize, validators, patch vocabulary) is unchanged.
"""

from .pipeline import stream_compose

__all__ = ["stream_compose"]
