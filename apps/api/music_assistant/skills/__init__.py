"""Deterministic composition skills used by the instrument agent for efficiency.

Only the primitives needed by the current efficiency work live here — `drum_pattern`
(so drum parts skip the LLM entirely) and `apply_edits` (so revision-round turns
ship a diff instead of a full note list). Pure functions, no LLM, no I/O.
"""

from .edits import EditFailure, NoteEdit, apply_edits
from .rhythm import drum_pattern

__all__ = ["EditFailure", "NoteEdit", "apply_edits", "drum_pattern"]
