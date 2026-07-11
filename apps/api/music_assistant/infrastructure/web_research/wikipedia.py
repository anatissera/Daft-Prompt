"""Wikipedia lookup adapter.

Fallback grounding source for music Q&A when the scraping search engines
(DuckDuckGo HTML, etc.) rate-limit or captcha-block this host. Uses the
official MediaWiki APIs — keyless, JSON, and tolerant of typos ("freddy
mercury" still finds Freddie Mercury).
"""

from __future__ import annotations

import json
import logging
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

log = logging.getLogger(__name__)

_UA = "DaftPrompt/1.0 (music study project; contact via repo)"


def _get_json(url: str, timeout: float) -> dict | None:
    request = Request(url, headers={"User-Agent": _UA, "Accept": "application/json"})
    try:
        with urlopen(request, timeout=timeout) as response:
            return json.loads(response.read(2_000_000).decode("utf-8", errors="replace"))
    except (HTTPError, URLError, TimeoutError, ValueError, json.JSONDecodeError):
        return None


class WikipediaSearch:
    def __init__(self, *, timeout_seconds: float = 8.0) -> None:
        self.timeout_seconds = timeout_seconds

    def search(
        self, query: str, *, langs: tuple[str, ...] = ("es", "en"), limit: int = 3
    ) -> list[dict[str, str]]:
        """Return up to `limit` results: title, url, site and a summary
        extract. Tries each language until one yields hits. Never raises."""
        query = (query or "").strip()
        if not query:
            return []
        for lang in langs:
            params = urlencode(
                {"action": "query", "list": "search", "srsearch": query,
                 "format": "json", "srlimit": limit}
            )
            data = _get_json(f"https://{lang}.wikipedia.org/w/api.php?{params}", self.timeout_seconds)
            hits = (data or {}).get("query", {}).get("search", [])
            if not hits:
                continue
            results: list[dict[str, str]] = []
            for hit in hits[:limit]:
                title = hit.get("title") or ""
                if not title:
                    continue
                slug = quote(title.replace(" ", "_"))
                summary = _get_json(
                    f"https://{lang}.wikipedia.org/api/rest_v1/page/summary/{slug}",
                    self.timeout_seconds,
                )
                results.append({
                    "title": title,
                    "url": f"https://{lang}.wikipedia.org/wiki/{slug}",
                    "site": f"{lang}.wikipedia.org",
                    "extract": (summary or {}).get("extract", ""),
                })
            if results:
                return results
        return []
