"""Small deterministic helpers that complement `theory.py` and `validators.py`.

Kept separate so `theory.py` stays a thin music21 wrapper and `validators.py`
stays focused on `SongState`-shaped checks. Everything here is pure and cheap;
no LLM, no external I/O.
"""

from __future__ import annotations

from typing import Iterable

from ..domain.song_state import Header, Note, Part
from .theory import beats_per_bar


def note_density(notes: Iterable[Note], header: Header) -> float:
    """Sounding notes per bar. Rests (pitch=None) do not count."""
    num_bars = max(1, header.num_bars)
    sounding = sum(1 for n in notes if n.pitch is not None)
    return sounding / num_bars


def part_density_by_id(parts: dict[str, Part], header: Header) -> dict[str, float]:
    """Convenience for eval: `part_id -> notes/bar` over the whole song."""
    return {pid: note_density(p.notes, header) for pid, p in parts.items()}


def detect_overlaps(part: Part, header: Header) -> list[tuple[int, str]]:
    """Same-instrument overlapping sounding notes. Assumes monophonic-by-convention
    (bass, lead, most winds). Returns `(bar, message)` per overlap so the caller
    can promote them to `ValidationIssue`s if the instrument is monophonic.

    An "overlap" means two sounding notes whose [start, start+dur) intervals
    intersect on the absolute beat axis. Rests are ignored. Zero-duration and
    negative-duration notes are ignored (validator flags those separately)."""
    bpb = beats_per_bar(header.time_signature)
    intervals: list[tuple[float, float, int]] = []  # (start, end, bar)
    for n in part.notes:
        if n.pitch is None or n.dur <= 0:
            continue
        start = n.bar * bpb + n.start_beat
        end = start + n.dur
        intervals.append((start, end, n.bar))
    intervals.sort()
    issues: list[tuple[int, str]] = []
    for i in range(1, len(intervals)):
        prev_start, prev_end, prev_bar = intervals[i - 1]
        cur_start, cur_end, cur_bar = intervals[i]
        if cur_start < prev_end - 1e-6:
            issues.append(
                (
                    cur_bar,
                    f"overlapping notes: prev ends at abs beat {prev_end:.3f}, "
                    f"next starts at {cur_start:.3f}",
                )
            )
    return issues
