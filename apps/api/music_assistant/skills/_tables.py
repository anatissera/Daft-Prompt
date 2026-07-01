"""Hand-curated drum-pattern tables used by `drum_pattern`."""

from __future__ import annotations

DRUM_KICK = 36
DRUM_SNARE = 38
DRUM_HAT_CLOSED = 42
DRUM_HAT_OPEN = 46
DRUM_CRASH = 49
DRUM_RIDE = 51

DRUM_PATTERNS: dict[str, list[tuple[int, float, float]]] = {
    "four_on_floor": [
        (DRUM_KICK, 0.0, 0.5), (DRUM_KICK, 1.0, 0.5),
        (DRUM_KICK, 2.0, 0.5), (DRUM_KICK, 3.0, 0.5),
        (DRUM_SNARE, 1.0, 0.5), (DRUM_SNARE, 3.0, 0.5),
        (DRUM_HAT_CLOSED, 0.0, 0.5), (DRUM_HAT_CLOSED, 0.5, 0.5),
        (DRUM_HAT_CLOSED, 1.0, 0.5), (DRUM_HAT_CLOSED, 1.5, 0.5),
        (DRUM_HAT_CLOSED, 2.0, 0.5), (DRUM_HAT_CLOSED, 2.5, 0.5),
        (DRUM_HAT_CLOSED, 3.0, 0.5), (DRUM_HAT_CLOSED, 3.5, 0.5),
    ],
    "rock_basic": [
        (DRUM_KICK, 0.0, 0.5), (DRUM_KICK, 2.0, 0.5),
        (DRUM_SNARE, 1.0, 0.5), (DRUM_SNARE, 3.0, 0.5),
        (DRUM_HAT_CLOSED, 0.0, 0.5), (DRUM_HAT_CLOSED, 0.5, 0.5),
        (DRUM_HAT_CLOSED, 1.0, 0.5), (DRUM_HAT_CLOSED, 1.5, 0.5),
        (DRUM_HAT_CLOSED, 2.0, 0.5), (DRUM_HAT_CLOSED, 2.5, 0.5),
        (DRUM_HAT_CLOSED, 3.0, 0.5), (DRUM_HAT_CLOSED, 3.5, 0.5),
    ],
    "boom_bap": [
        (DRUM_KICK, 0.0, 0.5), (DRUM_KICK, 2.5, 0.5),
        (DRUM_SNARE, 1.0, 0.5), (DRUM_SNARE, 3.0, 0.5),
        (DRUM_HAT_CLOSED, 0.0, 0.5), (DRUM_HAT_CLOSED, 0.5, 0.5),
        (DRUM_HAT_CLOSED, 1.0, 0.5), (DRUM_HAT_CLOSED, 1.5, 0.5),
        (DRUM_HAT_CLOSED, 2.0, 0.5), (DRUM_HAT_CLOSED, 2.5, 0.5),
        (DRUM_HAT_CLOSED, 3.0, 0.5), (DRUM_HAT_CLOSED, 3.5, 0.5),
    ],
    "half_time": [
        (DRUM_KICK, 0.0, 0.5),
        (DRUM_SNARE, 2.0, 0.5),
        (DRUM_HAT_CLOSED, 0.0, 0.5), (DRUM_HAT_CLOSED, 1.0, 0.5),
        (DRUM_HAT_CLOSED, 2.0, 0.5), (DRUM_HAT_CLOSED, 3.0, 0.5),
    ],
    "funk": [
        (DRUM_KICK, 0.0, 0.25), (DRUM_KICK, 0.75, 0.25),
        (DRUM_KICK, 2.5, 0.25),
        (DRUM_SNARE, 1.0, 0.25), (DRUM_SNARE, 3.0, 0.25),
        (DRUM_HAT_CLOSED, 0.0, 0.25), (DRUM_HAT_CLOSED, 0.5, 0.25),
        (DRUM_HAT_CLOSED, 1.0, 0.25), (DRUM_HAT_CLOSED, 1.5, 0.25),
        (DRUM_HAT_CLOSED, 2.0, 0.25), (DRUM_HAT_CLOSED, 2.5, 0.25),
        (DRUM_HAT_CLOSED, 3.0, 0.25), (DRUM_HAT_CLOSED, 3.5, 0.25),
    ],
}

DRUM_PATTERN_ALIASES: dict[str, str] = {
    "house": "four_on_floor",
    "disco": "four_on_floor",
    "edm": "four_on_floor",
    "techno": "four_on_floor",
    "rock": "rock_basic",
    "pop": "rock_basic",
    "hiphop": "boom_bap",
    "hip_hop": "boom_bap",
    "hip-hop": "boom_bap",
    "rap": "boom_bap",
    "trap": "boom_bap",
    "ballad": "half_time",
    "slow": "half_time",
}
