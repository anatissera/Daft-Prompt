"""Deterministic music-theory helpers shared by converters and validators."""

from __future__ import annotations

import re
from functools import lru_cache
from typing import Optional


def beats_per_bar(time_signature: tuple[int, int]) -> float:
    """Number of quarter-note beats per bar for a given time signature."""
    numerator, denominator = time_signature
    return numerator * (4.0 / denominator)


@lru_cache(maxsize=128)
def key_pitch_classes(key_str: str) -> frozenset[int]:
    """Pitch classes (0-11) belonging to `key_str` (e.g. "F# minor", "C major").

    Falls back to an empty set if music21 can't parse the key, so callers can
    treat "unknown key" as "don't flag out-of-key" rather than crash.
    """
    from music21 import key as m21key

    try:
        k = m21key.Key(*_split_key(key_str))
        return frozenset(p.pitchClass for p in k.pitches)
    except Exception:
        return frozenset()


def _split_key(key_str: str) -> tuple[str, str]:
    parts = key_str.strip().split()
    tonic = parts[0] if parts else "C"
    mode = parts[1].lower() if len(parts) > 1 else "major"
    return tonic, mode


def in_key(pitch: int, key_str: str) -> bool:
    """True if `pitch`'s pitch class is in the key (or the key is unknown)."""
    pcs = key_pitch_classes(key_str)
    if not pcs:
        return True
    return (pitch % 12) in pcs


def _normalize_chord_symbol(chord_str: str) -> str:
    """Map an LLM-emitted chord symbol to music21's notation. The main mismatch is
    flats: LLMs write 'Bb'/'Db', music21 wants 'B-'/'D-'. Only the flat applied to
    the leading root letter is converted (kinds like 'dim'/'sus' are left alone)."""
    return re.sub(r"^([A-Ga-g])b", r"\1-", chord_str.strip())


@lru_cache(maxsize=256)
def chord_pitch_classes(chord_str: str) -> frozenset[int]:
    """Pitch classes (0-11) of a chord symbol (e.g. "Em7", "Cmaj7", "Bb7", "A/C#").

    Falls back to an empty set when the symbol is empty, "N.C.", or unparseable, so
    callers treat "unknown chord" as "don't flag" rather than crash — mirroring
    `key_pitch_classes`.
    """
    if not chord_str or not chord_str.strip():
        return frozenset()
    from music21 import harmony

    try:
        cs = harmony.ChordSymbol(_normalize_chord_symbol(chord_str))
        return frozenset(p.pitchClass for p in cs.pitches)
    except Exception:
        return frozenset()


@lru_cache(maxsize=256)
def chord_tone_names(chord_str: str) -> tuple[str, ...]:
    """Human-readable note names of a chord symbol, in chord order (root first), e.g.
    "Em7" -> ("E", "G", "B", "D"). Empty tuple when unparseable. For prompt guidance."""
    if not chord_str or not chord_str.strip():
        return ()
    from music21 import harmony

    try:
        cs = harmony.ChordSymbol(_normalize_chord_symbol(chord_str))
        seen: list[str] = []
        for p in cs.pitches:
            name = p.name.replace("-", "b")  # music21 'E-' -> 'Eb'
            if name not in seen:
                seen.append(name)
        return tuple(seen)
    except Exception:
        return ()


def active_chord_at(bar: int, chord_progression) -> Optional[str]:
    """The chord symbol in effect at `bar` = the most recent span with span.bar <= bar.

    `chord_progression` is a list of objects with `.bar` and `.chord`. Returns None
    when no span covers the bar (e.g. the progression is empty or starts later).
    """
    covering = [cs for cs in chord_progression if cs.bar <= bar]
    if not covering:
        return None
    return max(covering, key=lambda cs: cs.bar).chord
