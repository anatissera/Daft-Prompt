"""Deterministic composition skills the LLM agents can call.

Pure functions over music21 + `llm_band.music` helpers. No SongState reads, no
LLM calls, no I/O — every skill maps explicit inputs to explicit musical output
(MIDI pitches, ChordSpans, Notes), which keeps them trivially testable and lets
the same primitive serve director, instrument, and arbiter agents.

Agent wiring (`@tool` decoration, `bind_tools`) lives at the agent layer; this
package stays free of LangChain imports.
"""

from .edits import EditFailure, NoteEdit, apply_edits
from .harmony import fit_to_range, scale_degrees, transpose, voice_lead
from .melody import melodic_contour
from .progression import suggest_chord_progression, suggest_form
from .rhythm import drum_pattern, quantize_rhythm

__all__ = [
    "EditFailure",
    "NoteEdit",
    "apply_edits",
    "fit_to_range",
    "scale_degrees",
    "transpose",
    "voice_lead",
    "melodic_contour",
    "suggest_chord_progression",
    "suggest_form",
    "drum_pattern",
    "quantize_rhythm",
]
