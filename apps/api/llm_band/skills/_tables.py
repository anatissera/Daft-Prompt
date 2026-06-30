"""Hand-curated tables backing the skill layer.

Kept out of the public skill modules so the LLM-facing surface stays narrow and
table edits don't churn the skill APIs. All progressions are written in Roman
numerals so they transpose cleanly into any key via `music21.roman`.
"""

from __future__ import annotations

PROGRESSIONS_MAJOR: dict[str, list[list[str]]] = {
    "happy":      [["I", "V", "vi", "IV"], ["I", "vi", "IV", "V"]],
    "energetic":  [["I", "V", "vi", "IV"], ["I", "bVII", "IV", "I"]],
    "mellow":     [["I", "iii", "IV", "V"], ["vi", "IV", "I", "V"]],
    "dramatic":   [["I", "V", "vi", "iii", "IV", "I", "IV", "V"]],
    "default":    [["I", "V", "vi", "IV"]],
}

PROGRESSIONS_MINOR: dict[str, list[list[str]]] = {
    "melancholic": [["i", "VI", "III", "VII"], ["i", "iv", "VII", "VI"]],
    "dark":        [["i", "VII", "VI", "VII"], ["i", "iv", "v", "i"]],
    "energetic":   [["i", "VII", "VI", "V"], ["i", "VI", "VII", "i"]],
    "mellow":      [["i", "iv", "VI", "VII"]],
    "default":     [["i", "VI", "III", "VII"]],
}

# General MIDI percussion keys we actually use.
DRUM_KICK = 36
DRUM_SNARE = 38
DRUM_HAT_CLOSED = 42
DRUM_HAT_OPEN = 46
DRUM_CRASH = 49
DRUM_RIDE = 51

# Drum patterns are expressed as (drum_key, start_beat_in_bar, duration_beats).
# Listed once per bar; `drum_pattern` repeats them across `num_bars`.
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
}

DRUM_PATTERN_ALIASES: dict[str, str] = {
    "house": "four_on_floor",
    "disco": "four_on_floor",
    "rock": "rock_basic",
    "pop": "rock_basic",
    "hiphop": "boom_bap",
    "hip_hop": "boom_bap",
    "ballad": "half_time",
}

# Section templates per broad genre family. Each entry is a sequence of section
# names; `suggest_form` distributes them evenly across `num_bars`.
FORM_TEMPLATES: dict[str, list[str]] = {
    "pop":      ["intro", "verse", "chorus", "verse", "chorus", "bridge", "chorus", "outro"],
    "rock":     ["intro", "verse", "chorus", "verse", "chorus", "solo", "chorus", "outro"],
    "electronic": ["intro", "build", "drop", "break", "build", "drop", "outro"],
    "ballad":   ["intro", "verse", "chorus", "verse", "chorus", "outro"],
    "default":  ["intro", "verse", "chorus", "verse", "chorus", "outro"],
}
