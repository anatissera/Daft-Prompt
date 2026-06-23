"""Deterministic music-theory helpers shared by converters and validators."""

from __future__ import annotations

from functools import lru_cache


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
