"""Rhythm skills: grid quantization and drum pattern generation.

`drum_pattern` returns ready-to-use `Note` objects on General MIDI drum keys, so
the drum agent can ship a known-good pattern verbatim instead of generating
percussion notes one by one. `quantize_rhythm` is a cleanup pass over agent-
generated rhythms that snaps onsets and durations to a beat grid.
"""

from __future__ import annotations

from ..domain.song_state import Note
from ..music.theory import beats_per_bar
from . import _tables


def quantize_rhythm(
    onsets: list[tuple[float, float]],
    grid: float,
    bar_beats: float,
) -> list[tuple[float, float]]:
    """Snap `(start_beat, duration)` pairs to multiples of `grid` beats.

    Onsets are clamped to `[0, bar_beats)`; durations are clamped to at least
    one grid step and at most the remaining bar so quantized notes never
    overflow. Invalid grid (`<= 0`) returns the input unchanged.
    """
    if grid <= 0:
        return list(onsets)
    out: list[tuple[float, float]] = []
    for start, dur in onsets:
        snapped_start = round(start / grid) * grid
        if snapped_start < 0:
            snapped_start = 0.0
        if snapped_start >= bar_beats:
            snapped_start = bar_beats - grid
        snapped_dur = max(grid, round(dur / grid) * grid)
        if snapped_start + snapped_dur > bar_beats:
            snapped_dur = bar_beats - snapped_start
        out.append((round(snapped_start, 6), round(snapped_dur, 6)))
    return out


def drum_pattern(
    style: str,
    time_signature: tuple[int, int],
    num_bars: int,
    velocity: int = 96,
) -> list[Note]:
    """Tile a hand-curated drum pattern across `num_bars`.

    Resolves `style` against the pattern table directly first, then against an
    alias map (so "house" → "four_on_floor"); falls back to "rock_basic" if
    nothing matches, since that pattern fits the widest set of contexts. Hits
    whose `start_beat` would land past the bar's beat count are dropped so the
    pattern degrades gracefully on odd meters rather than corrupting the bar.
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


def transition_fill_bars(num_bars: int, every: int = 4) -> list[int]:
    """Bars that should receive a deterministic fill before a phrase boundary."""
    if num_bars < every or every <= 0:
        return []
    return list(range(every - 1, num_bars, every))


def drum_transition_fill(
    time_signature: tuple[int, int],
    bar: int,
    velocity: int = 108,
) -> list[Note]:
    """A short tom/snare fill over the last quarter-note beat of `bar`."""
    bpb = beats_per_bar(time_signature)
    if bpb <= 0:
        return []
    fill_start = max(0.0, bpb - 1.0)
    step = max(0.0625, (bpb - fill_start) / 4)
    pitches = [
        _tables.DRUM_SNARE,
        _tables.DRUM_TOM_HIGH,
        _tables.DRUM_TOM_MID,
        _tables.DRUM_TOM_LOW,
    ]
    return [
        Note(
            bar=bar,
            start_beat=round(fill_start + index * step, 6),
            pitch=pitch,
            dur=round(step, 6),
            velocity=velocity,
        )
        for index, pitch in enumerate(pitches)
        if fill_start + index * step < bpb
    ]


def apply_transition_fills(
    notes: list[Note],
    time_signature: tuple[int, int],
    num_bars: int,
    every: int = 4,
) -> list[Note]:
    """Replace the last beat of each phrase-boundary bar with a fixed drum fill."""
    fill_bars = set(transition_fill_bars(num_bars, every=every))
    if not fill_bars:
        return list(notes)
    bpb = beats_per_bar(time_signature)
    fill_start = max(0.0, bpb - 1.0)
    kept = [
        note
        for note in notes
        if not (note.bar in fill_bars and note.start_beat >= fill_start)
    ]
    for bar in sorted(fill_bars):
        kept.extend(drum_transition_fill(time_signature, bar))
    return sorted(kept, key=lambda note: (note.bar, note.start_beat, note.pitch or 0))


__all__ = [
    "quantize_rhythm",
    "drum_pattern",
    "transition_fill_bars",
    "drum_transition_fill",
    "apply_transition_fills",
]
