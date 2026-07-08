"""Corpus retrieval: Lakh-derived style exemplars + Groove drum patterns.

Returns a single compact digest (JSON-safe) that the planner sees in-prompt:
  - `examples`: up to `k` Lakh segments matching the style (tempo, key,
    chord progression, typical roles).
  - `median_tempo`, `common_keys`, `common_roles`: aggregates across matches,
    used as prior beliefs when the planner falls back to defaults.
  - `groove`: a single drum pattern (channel-string grid) whose bpm is
    closest to the style median.

If the offline indices are missing (fresh clone, CI), everything degrades to
empty / None and the planner works from the prompt + web results alone.
"""

from __future__ import annotations

import re
from collections import Counter
from typing import Any, Iterable, Optional

from music_assistant.corpus.retrieve import (
    retrieve_groove,
    retrieve_style_examples,
)


# Closed vocabulary the fallback recognises inside web-search titles. Order
# is descending specificity: match a two-word genre before its head word so
# "hip hop" wins over "pop", "drum and bass" wins over "bass", etc.
_KNOWN_GENRES: tuple[str, ...] = (
    "drum and bass",
    "hip hop",
    "hip-hop",
    "future bass",
    "trap",
    "dubstep",
    "house",
    "techno",
    "electro",
    "electronic",
    "edm",
    "dance",
    "pop",
    "rock",
    "metal",
    "punk",
    "indie",
    "jazz",
    "blues",
    "funk",
    "soul",
    "rnb",
    "r&b",
    "reggae",
    "latin",
    "country",
    "classical",
    "folk",
    "ambient",
    "lofi",
    "disco",
)


def infer_genre_from_titles(titles: Iterable[str]) -> Optional[str]:
    """Return the most frequent known-genre keyword mentioned in `titles`,
    or None if nothing matches. Uses whole-word regex so "pop" doesn't
    match "population"."""
    hits: Counter[str] = Counter()
    for t in titles:
        low = (t or "").lower()
        for genre in _KNOWN_GENRES:
            pattern = r"\b" + re.escape(genre) + r"\b"
            if re.search(pattern, low):
                hits[genre] += 1
    if not hits:
        return None
    # Prefer more specific (longer) genres on ties.
    return max(hits.items(), key=lambda kv: (kv[1], len(kv[0])))[0]


def retrieve_corpus(query: str, *, k: int = 6, energy: str = "medium") -> dict[str, Any]:
    """Return a compact digest of style exemplars + a matching groove.

    `query` is the raw style prompt (e.g. "marshmello", "metal", "80s pop").
    """
    q = (query or "").strip()
    if not q:
        return _empty_digest()

    examples = retrieve_style_examples(q, energy=energy, n=k)
    if not examples:
        return _empty_digest()

    tempos = sorted(float(e.tempo) for e in examples if e.tempo)
    median_tempo = tempos[len(tempos) // 2] if tempos else 120.0

    key_counter: Counter[str] = Counter(e.key for e in examples if e.key)
    role_counter: Counter[str] = Counter(r for e in examples for r in e.roles)

    # Groove index styles are coarser than Lakh genres (rock/funk/jazz/hiphop/
    # latin/pop/dance/...); when the raw query doesn't hit a groove style, fall
    # back to the closest coarse category. Keeps EDM prompts from silently
    # dropping to the hard-coded four-on-the-floor when a `dance` groove exists.
    groove = retrieve_groove(q, bpm=median_tempo, energy=energy)
    if groove is None:
        mapped = _GROOVE_STYLE_FALLBACKS.get(q.lower())
        if mapped:
            groove = retrieve_groove(mapped, bpm=median_tempo, energy=energy)

    return {
        "examples": [
            {
                "track_id": e.track_id,
                "genre": e.genre,
                "key": e.key,
                "tempo": round(float(e.tempo), 1),
                "progression": e.progression,
                "roles": e.roles,
            }
            for e in examples
        ],
        "median_tempo": round(median_tempo, 1),
        "common_keys": [k for k, _ in key_counter.most_common(3)],
        "common_roles": [r for r, _ in role_counter.most_common(6)],
        "groove": None if groove is None else {
            "style": groove.style,
            "bpm": round(float(groove.bpm), 1),
            "type": groove.type,
            "num_bars": groove.num_bars,
            "pattern_by_channel": groove.pattern_by_channel,
        },
    }


_GROOVE_STYLE_FALLBACKS: dict[str, str] = {
    "electronic": "dance",
    "edm": "dance",
    "house": "dance",
    "techno": "dance",
    "trance": "dance",
    "dubstep": "dance",
    "future bass": "dance",
    "electro": "dance",
    "trap": "hiphop",
    "hip hop": "hiphop",
    "hip-hop": "hiphop",
    "lofi": "hiphop",
    "metal": "rock",
    "indie": "rock",
    "rnb": "soul",
    "r&b": "soul",
}


def _empty_digest() -> dict[str, Any]:
    return {
        "examples": [],
        "median_tempo": None,
        "common_keys": [],
        "common_roles": [],
        "groove": None,
    }
