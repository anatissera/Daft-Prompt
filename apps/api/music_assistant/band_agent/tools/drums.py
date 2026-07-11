"""Deterministic drum-track synthesis from a Groove-corpus channel grid.

The planner does not emit drum notes (they are the biggest token cost in a
song and the LLM offers no musical value over a real DAW pattern). Instead
we pull a `GroovePattern` from the corpus, map its channel-string grid onto
GM percussion pitches, and repeat it across the song's `num_bars`.

Grid format: `pattern_by_channel[<channel>]` is a string where each char is
one subdivision (16th notes at 4/4 in the Groove index). Any non-`.` /
non-` ` / non-`0` char counts as a hit ('x' in practice).
"""

from __future__ import annotations

from typing import Optional

from music_assistant.domain.song_state import Note


# Channel name (as in the Groove index) → GM percussion pitch (channel 10).
# https://en.wikipedia.org/wiki/General_MIDI#Percussion
_CHANNEL_TO_GM: dict[str, int] = {
    "kick": 36,
    "snare": 38,
    "side_stick": 37,
    "clap": 39,
    "closed_hihat": 42,
    "pedal_hihat": 44,
    "open_hihat": 46,
    "low_tom": 41,
    "mid_tom": 47,
    "high_tom": 50,
    "tom_low": 41,
    "tom_mid": 47,
    "tom_high": 50,
    "crash": 49,
    "ride": 51,
    "ride_bell": 53,
    "china": 52,
    "tambourine": 54,
    "cowbell": 56,
    "shaker": 82,
}


# Fallback pattern used when the corpus returns no groove — a simple
# four-on-the-floor with backbeat snare and a driving eighth-note hat.
# 16 subdivisions per bar.
_DEFAULT_PATTERN: dict[str, str] = {
    "kick":         "x...x...x...x...",
    "snare":        "....x.......x...",
    "closed_hihat": "x.x.x.x.x.x.x.x.",
}


def synthesize_drum_notes(
    pattern_by_channel: Optional[dict[str, str]],
    *,
    num_bars: int,
    beats_per_bar: float = 4.0,
    default_velocity: int = 96,
) -> list[Note]:
    """Expand a Groove-style channel grid to `Note`s across `num_bars`.

    Ignores channels not in `_CHANNEL_TO_GM`. Uses `_DEFAULT_PATTERN` when
    `pattern_by_channel` is None or empty.
    """
    grid = pattern_by_channel or _DEFAULT_PATTERN
    # Derive subdivisions-per-bar from the longest channel string. All
    # channels in a real Groove entry share the same length, but empty rows
    # can be shorter, so `max` is robust.
    subs_per_bar = max((_subs_of_bar(s) for s in grid.values()), default=16)
    if subs_per_bar <= 0:
        return []
    beat_per_sub = beats_per_bar / subs_per_bar
    dur = beat_per_sub  # each hit occupies its own subdivision

    notes: list[Note] = []
    for channel, row in grid.items():
        pitch = _CHANNEL_TO_GM.get(channel.lower())
        if pitch is None or not row:
            continue
        row_bar_len = _subs_of_bar(row) or subs_per_bar
        # Iterate one bar at a time and repeat the underlying pattern by
        # tiling it if the source is shorter than num_bars.
        for bar in range(num_bars):
            source_bar = bar % max(1, len(row) // row_bar_len or 1)
            offset = source_bar * row_bar_len
            slice_ = row[offset:offset + row_bar_len]
            for i, ch in enumerate(slice_):
                if _is_hit(ch):
                    notes.append(Note(
                        bar=bar,
                        start_beat=i * beat_per_sub,
                        pitch=pitch,
                        dur=dur,
                        velocity=default_velocity,
                    ))
    return notes


def _subs_of_bar(row: str) -> int:
    """Best guess at subdivisions-per-bar. The Groove index uses 16 for 4/4;
    fall back to the string length when it's short."""
    if not row:
        return 0
    if len(row) % 16 == 0:
        return 16
    if len(row) % 8 == 0:
        return 8
    return len(row)


def _is_hit(char: str) -> bool:
    return char not in (".", " ", "0", "")
