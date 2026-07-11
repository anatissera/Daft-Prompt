"""Curated demo cache: normalized prompt -> stored compose job.

Lets a rehearsed prompt ("una cancion de rock") replay a previously
composed song instantly instead of running the full pipeline. Only
exact (normalized) matches hit the cache, so every other prompt keeps
composing from scratch. Entries are pinned by hand with
`scripts/pin_demo_song.py`; the mapping lives next to the artifacts in
`<outputs>/demo_cache.json`.
"""

from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path

CACHE_FILENAME = "demo_cache.json"

_WS_RE = re.compile(r"\s+")
_PUNCT_RE = re.compile(r"[^\w\s]", re.UNICODE)


def normalize_prompt(text: str) -> str:
    """Accent-insensitive, punctuation-insensitive, case-insensitive key."""
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = _PUNCT_RE.sub(" ", text.lower())
    return _WS_RE.sub(" ", text).strip()


def _cache_path(outputs_root: Path) -> Path:
    return outputs_root / CACHE_FILENAME


def load(outputs_root: Path) -> dict[str, str]:
    path = _cache_path(outputs_root)
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return {}
    return {k: v for k, v in data.items() if isinstance(k, str) and isinstance(v, str)}


def lookup(outputs_root: Path, prompt: str) -> str | None:
    """Return the pinned job_id for this prompt, or None (cache miss)."""
    return load(outputs_root).get(normalize_prompt(prompt))


def pin(outputs_root: Path, job_id: str, prompts: list[str]) -> dict[str, str]:
    """Map every prompt phrasing to job_id and persist. Returns the mapping."""
    cache = load(outputs_root)
    for prompt in prompts:
        key = normalize_prompt(prompt)
        if key:
            cache[key] = job_id
    _cache_path(outputs_root).write_text(json.dumps(cache, ensure_ascii=False, indent=2))
    return cache
