"""DuckDuckGo-backed style research.

The planner uses this to ground its picks (tempo/key/typical roster) in real
prose about the artist/style. It returns a compact, deterministic digest
(title/url/site + snippet-less) — the planner does not read pages, so we
avoid a page fetcher on this fast path. If DDG rate-limits, we return an
empty list and the planner falls back on the corpus + prompt text alone.
"""

from __future__ import annotations

from typing import Any

from music_assistant.infrastructure.web_research.search import DuckDuckGoSearch


_DEFAULT_LIMIT = 6
_SUFFIX = " music production style tempo key instruments"


def search_web(
    query: str, *, limit: int = _DEFAULT_LIMIT, decorate: bool = True
) -> list[dict[str, Any]]:
    """Return up to `limit` DDG results for a style/artist query.

    `decorate=True` (default) appends a production-focused suffix that biases
    DDG toward tempo/key/instrument pages. Pass `decorate=False` when you
    want the raw query — useful for a follow-up genre lookup where the plain
    "<artist> genre" phrasing has to reach Wikipedia intros untouched.
    """
    q = (query or "").strip()
    if not q:
        return []
    q_full = q + _SUFFIX if decorate else q
    results = DuckDuckGoSearch().search(q_full, limit=limit)
    return [{"title": r.title, "url": r.url, "site": r.site} for r in results]
