"""Runtime retrieval of style exemplars from the offline indices.

Two entry points feed the composition graph:
  - `retrieve_style_examples(genre, energy, key, n)`: returns roman/symbol
    progressions + typical instrumentation from same-genre Lakh segments.
  - `retrieve_groove(style, bpm, energy)`: returns a compact drum-pattern grid
    from the Groove index, matching style + bpm.

The LLM never sees raw MIDI or per-note dicts — only the compact objects here.

If the indices are absent (fresh clone, CI without corpus), each function
returns an empty result and the caller degrades to today's behaviour.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Iterable, Optional

APP_ROOT = Path(__file__).resolve().parents[2]
INDEX_ROOT = APP_ROOT / "data" / "index"


@dataclass
class LakhExample:
    track_id: str
    genre: str
    key: str
    tempo: float
    progression: list[str]
    density_by_role: dict[str, float]
    roles: list[str]


@dataclass
class GroovePattern:
    style: str
    bpm: float
    type: str
    num_bars: int
    pattern_by_channel: dict[str, str] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Loaders — cached; parquet if pyarrow is installed, else JSON-lines
# ---------------------------------------------------------------------------


def _find_index(basename: str) -> Optional[Path]:
    for ext in (".parquet", ".jsonl"):
        p = INDEX_ROOT / f"{basename}{ext}"
        if p.exists():
            return p
    return None


@lru_cache(maxsize=1)
def _load_lakh() -> list[dict]:
    path = _find_index("lakh_segments")
    if path is None:
        return []
    return _load_any(path)


@lru_cache(maxsize=1)
def _load_groove() -> list[dict]:
    path = _find_index("groove_patterns")
    if path is None:
        return []
    return _load_any(path)


def _load_any(path: Path) -> list[dict]:
    if path.suffix == ".parquet":
        try:
            import pyarrow.parquet as pq
            table = pq.read_table(path)
            rows = table.to_pylist()
            return [_decode_json_columns(r) for r in rows]
        except Exception:
            return []
    rows: list[dict] = []
    with path.open() as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def _decode_json_columns(row: dict) -> dict:
    for k, v in list(row.items()):
        if isinstance(v, str) and v and v[0] in "[{":
            try:
                row[k] = json.loads(v)
            except Exception:
                pass
    return row


# ---------------------------------------------------------------------------
# Genre normalisation — cheap fuzzy match, no LLM needed for coarse genres.
# ---------------------------------------------------------------------------


_GENRE_SYNONYMS = {
    "reggaeton": ("reggaeton", "latin urban", "latin"),
    "bossa": ("bossa", "brazilian", "latin", "jazz"),
    "bossa nova": ("bossa", "brazilian", "latin", "jazz"),
    "funk": ("funk", "soul"),
    "rock": ("rock", "hard rock", "alt rock"),
    "grunge": ("rock", "alt rock", "grunge"),
    "pop": ("pop", "dance"),
    "hip hop": ("hip hop", "rap"),
    "electronic": ("electronic", "electronica", "edm"),
    "house": ("house", "electronic", "dance"),
    "techno": ("techno", "electronic"),
    "jazz": ("jazz",),
    "blues": ("blues", "rhythm and blues"),
    "country": ("country",),
    "metal": ("metal", "heavy metal"),
    "soul": ("soul", "r&b", "rnb"),
    "afrobeat": ("afrobeat", "afro", "latin"),
    "salsa": ("salsa", "latin"),
    "cumbia": ("cumbia", "latin"),
    "classical": ("classical", "orchestral"),
    "ambient": ("ambient", "electronic"),
}


def normalize_genre(user_style: str) -> list[str]:
    """Map a free-form style string to a list of coarse tags used in the corpus
    indices. First hit wins; unknown → single-element list with the lowercased
    string so filters still work by substring."""
    s = (user_style or "").strip().lower()
    if not s:
        return []
    for keyword, tags in _GENRE_SYNONYMS.items():
        if keyword in s:
            return list(tags)
    # Fall back to substring of the raw string.
    return [s.split()[0]]


# ---------------------------------------------------------------------------
# Public retrieval API
# ---------------------------------------------------------------------------


def retrieve_style_examples(
    genre: str,
    energy: str = "medium",
    n: int = 3,
    _rows: Optional[list[dict]] = None,
) -> list[LakhExample]:
    """Return up to `n` Lakh segments matching `genre` and target `energy`
    (low/medium/high). Empty list when the index is absent."""
    rows = _rows if _rows is not None else _load_lakh()
    if not rows:
        return []
    tags = normalize_genre(genre) or [genre.lower()]
    matches = [
        r for r in rows if any(tag in (r.get("genre") or "").lower() for tag in tags)
    ]
    if not matches:
        return []

    ranked = sorted(matches, key=lambda r: _energy_distance(r, energy))
    picked = ranked[: max(1, n)]
    return [_row_to_lakh(r) for r in picked]


def retrieve_groove(
    style: str,
    bpm: float,
    energy: str = "medium",
    _rows: Optional[list[dict]] = None,
) -> Optional[GroovePattern]:
    """Return one groove pattern matching `style` closest by bpm. Prefer
    `type=fill` for high-energy hand-offs, `type=beat` otherwise. Returns None
    when nothing matches or the index is absent."""
    rows = _rows if _rows is not None else _load_groove()
    if not rows:
        return None
    tags = normalize_genre(style) or [style.lower()]
    prefer_type = "fill" if energy == "high" else "beat"
    matches = [
        r for r in rows if any(tag in (r.get("style") or "").lower() for tag in tags)
    ]
    if not matches:
        return None

    def rank(r: dict) -> tuple[int, float]:
        type_penalty = 0 if r.get("type") == prefer_type else 1
        bpm_penalty = abs(_safe_float(r.get("bpm"), 0.0) - bpm)
        return (type_penalty, bpm_penalty)

    best = min(matches, key=rank)
    return _row_to_groove(best)


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


_ENERGY_DENSITY = {"low": 3.0, "medium": 6.0, "high": 10.0}


def _energy_distance(row: dict, energy: str) -> float:
    target = _ENERGY_DENSITY.get(energy, 6.0)
    d = row.get("density_by_role") or {}
    if isinstance(d, str):
        try:
            d = json.loads(d)
        except Exception:
            d = {}
    if not d:
        return 999.0
    avg = sum(d.values()) / len(d)
    return abs(avg - target)


def _row_to_lakh(r: dict) -> LakhExample:
    return LakhExample(
        track_id=r.get("track_id", ""),
        genre=r.get("genre", ""),
        key=r.get("key", "C major"),
        tempo=_safe_float(r.get("tempo"), 120.0),
        progression=_ensure_list(r.get("progression")),
        density_by_role=_ensure_dict(r.get("density_by_role")),
        roles=_ensure_list(r.get("roles")),
    )


def _row_to_groove(r: dict) -> GroovePattern:
    return GroovePattern(
        style=r.get("style", ""),
        bpm=_safe_float(r.get("bpm"), 120.0),
        type=r.get("type", "beat"),
        num_bars=int(r.get("num_bars", 0)),
        pattern_by_channel=_ensure_dict(r.get("pattern_by_channel")),
    )


def _safe_float(v, default: float) -> float:
    try:
        return float(v)
    except Exception:
        return default


def _ensure_list(v) -> list:
    if isinstance(v, list):
        return v
    if isinstance(v, str) and v:
        try:
            got = json.loads(v)
            return got if isinstance(got, list) else []
        except Exception:
            return []
    return []


def _ensure_dict(v) -> dict:
    if isinstance(v, dict):
        return v
    if isinstance(v, str) and v:
        try:
            got = json.loads(v)
            return got if isinstance(got, dict) else {}
        except Exception:
            return {}
    return {}


def clear_caches() -> None:
    """Test helper — the parquet loader is cached across calls."""
    _load_lakh.cache_clear()
    _load_groove.cache_clear()
