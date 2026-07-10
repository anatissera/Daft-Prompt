"""Fetch + digest real page content for style grounding.

`search_web` alone hands the planner nothing but result TITLES, so
"instrument research" was decorative: the roster came entirely from the
LLM's prior. This tool fetches the top few result pages in parallel,
strips them to plain text, and keeps a compact excerpt biased toward
production vocabulary (instruments, tempo, synths). The excerpts ride
along in the skeleton prompt so the instrument choice is grounded in
prose actually written about the artist/style.
"""

from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from music_assistant.infrastructure.web_research.fetch import UrlLibPageFetcher

_MAX_PAGES = 3
_EXCERPT_CHARS = 1500
_FETCH_TIMEOUT_S = 5.0

_SCRIPT_STYLE = re.compile(r"<(script|style|noscript)[^>]*>.*?</\1>", re.IGNORECASE | re.DOTALL)
_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"\s+")

# Sentences mentioning production vocabulary are the ones that ground the
# roster; a page's nav/boilerplate rarely contains these words.
_PRODUCTION_HINT = re.compile(
    r"\b(instrument|synth|bass|drum|guitar|piano|vocal|tempo|bpm|beat|"
    r"kick|snare|pad|lead|sample|wobble|sub|arpegg|chord|key of|"
    r"production|sound design|genre)\b",
    re.IGNORECASE,
)


def _to_text(html: str) -> str:
    text = _SCRIPT_STYLE.sub(" ", html)
    text = _TAG.sub(" ", text)
    return _WS.sub(" ", text).strip()


def _excerpt(text: str, *, limit: int = _EXCERPT_CHARS) -> str:
    """Prefer sentences that talk about production/instrumentation; pad with
    the page opening if that alone doesn't fill the budget."""
    sentences = re.split(r"(?<=[.!?])\s+", text)
    scored = [s for s in sentences if _PRODUCTION_HINT.search(s) and 30 < len(s) < 400]
    picked: list[str] = []
    used = 0
    for s in scored:
        if used + len(s) > limit:
            break
        picked.append(s)
        used += len(s)
    if used < limit // 2:
        head = text[: limit - used]
        picked.append(head)
    return " ".join(picked)[:limit]


def fetch_style_excerpts(hits: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Fetch up to `_MAX_PAGES` of `hits` in parallel and return
    `{title, site, excerpt}` digests. Failures are dropped silently — an
    empty list simply means the planner works from titles + corpus alone,
    which is the previous behaviour."""
    targets = hits[:_MAX_PAGES]
    if not targets:
        return []
    fetcher = UrlLibPageFetcher(timeout_seconds=_FETCH_TIMEOUT_S)
    out: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=len(targets)) as pool:
        futures = {
            pool.submit(fetcher.fetch, h.get("url", "")): h for h in targets if h.get("url")
        }
        for fut in as_completed(futures):
            hit = futures[fut]
            try:
                text = _to_text(fut.result())
            except Exception:
                continue
            if len(text) < 200:
                continue
            out.append({
                "title": hit.get("title", ""),
                "site": hit.get("site", ""),
                "excerpt": _excerpt(text),
            })
    return out
