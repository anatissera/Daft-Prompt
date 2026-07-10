"""Deterministic enforcement of the skeleton's rhythmic commitments.

The director commits, per instrument, an `onset_grid` (one-bar 16th-note
cell — genre rhythms like dembow or tango habanera ARE exact onset grids)
and a `max_notes_per_bar` density budget. Fill models — smaller and faster
than the director — often drift off those commitments when they only exist
as prose. These two passes make the commitments binding:

  - `enforce_grid`: snap near-grid notes onto their slot; drop notes whose
    onset lands on a rest slot. Empty/invalid grids mean free phrasing.
  - `enforce_density`: keep at most N notes per bar, preferring the loudest
    (velocity) and earliest — "sparse" as arithmetic instead of adjective.

Both are genre-agnostic: all musical knowledge lives in the committed data.
"""

from __future__ import annotations

import logging
import re
from typing import Any

log = logging.getLogger(__name__)

_GRID_RE = re.compile(r"^[xX.\-_ ]+$")

# How far (in beats) an onset may sit from an allowed slot and still be
# snapped onto it. A 16th is 0.25 beats; half of that keeps honest swing
# placement while catching float sloppiness.
_SNAP_TOLERANCE = 0.126


def _parse_grid(grid: str, beats_per_bar: float) -> list[float] | None:
    """Return the allowed onset beats for one bar, or None when the grid is
    absent/garbage (→ free phrasing). Accepts x/X as onsets and ./-/_/space
    as rests; any length is interpreted as an even division of the bar."""
    g = (grid or "").strip()
    if not g or not _GRID_RE.match(g) or "x" not in g.lower():
        return None
    slots = len(g)
    step = beats_per_bar / slots
    return [i * step for i, ch in enumerate(g) if ch in ("x", "X")]


def enforce_grid(
    notes: list[Any],
    grid: str,
    *,
    beats_per_bar: float,
    instrument_id: str = "?",
) -> list[Any]:
    """Snap each note's start_beat to its nearest allowed grid slot; drop
    notes that aren't near any allowed slot. `notes` are NotePlan-like
    objects (bar / start_beat / pitch / dur / velocity)."""
    allowed = _parse_grid(grid, beats_per_bar)
    if allowed is None or not notes:
        return notes
    kept: list[Any] = []
    dropped = 0
    for n in notes:
        beat = float(n.start_beat)
        nearest = min(allowed, key=lambda s: abs(s - beat))
        if abs(nearest - beat) <= _SNAP_TOLERANCE:
            if nearest != beat:
                n = n.model_copy(update={"start_beat": nearest})
            kept.append(n)
        else:
            dropped += 1
    if dropped:
        log.info(
            "groove_enforce: %s — dropped %d/%d off-grid notes (grid %r)",
            instrument_id, dropped, len(notes), grid,
        )
    return kept


def enforce_density(
    notes: list[Any],
    max_per_bar: int,
    *,
    instrument_id: str = "?",
) -> list[Any]:
    """Keep at most `max_per_bar` notes in each bar. Notes that start at the
    same beat count as ONE event (a chord is one gesture, not three notes of
    density). Within a bar, prefer louder events, then earlier ones."""
    if max_per_bar <= 0 or not notes:
        return notes
    by_bar: dict[int, dict[float, list[Any]]] = {}
    for n in notes:
        by_bar.setdefault(int(n.bar), {}).setdefault(float(n.start_beat), []).append(n)
    kept: list[Any] = []
    dropped = 0
    for bar, events in by_bar.items():
        if len(events) <= max_per_bar:
            for grp in events.values():
                kept.extend(grp)
            continue
        scored = sorted(
            events.items(),
            key=lambda kv: (-max(float(x.velocity) for x in kv[1]), kv[0]),
        )
        for beat, grp in scored[:max_per_bar]:
            kept.extend(grp)
        dropped += sum(len(g) for _, g in scored[max_per_bar:])
    if dropped:
        log.info(
            "groove_enforce: %s — pruned %d notes over density budget %d/bar",
            instrument_id, dropped, max_per_bar,
        )
    kept.sort(key=lambda n: (int(n.bar), float(n.start_beat)))
    return kept
