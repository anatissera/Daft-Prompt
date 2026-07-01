"""Deterministic drum-pattern generator used by the drum shortcut in the
instrument agent — bypasses the LLM entirely for percussion parts.
"""

from __future__ import annotations

from ..domain.song_state import Note
from ..music.theory import beats_per_bar
from . import _tables


def drum_pattern(
    style: str,
    time_signature: tuple[int, int],
    num_bars: int,
    velocity: int = 96,
) -> list[Note]:
    """Tile a hand-curated drum pattern across `num_bars`.

    Style resolution: direct table match → alias map → fallback to `rock_basic`.
    Hits that would fall past the bar's beat count on an odd meter are dropped
    so the pattern degrades gracefully instead of corrupting the bar.
    """
    if num_bars <= 0:
        return []
    key = style.lower().strip()
    pattern = _tables.DRUM_PATTERNS.get(key)
    if pattern is None:
        alias = _tables.DRUM_PATTERN_ALIASES.get(key)
        if alias is not None:
            pattern = _tables.DRUM_PATTERNS[alias]
    if pattern is None:
        pattern = _tables.DRUM_PATTERNS["rock_basic"]

    bpb = beats_per_bar(time_signature)
    notes: list[Note] = []
    for bar in range(num_bars):
        for drum_key, start, dur in pattern:
            if start >= bpb:
                continue
            clipped_dur = min(dur, bpb - start)
            notes.append(Note(
                bar=bar, start_beat=start, pitch=drum_key,
                dur=clipped_dur, velocity=velocity,
            ))
    return notes
