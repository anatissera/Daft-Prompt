"""DuckDuckGo-backed search adapter for the web-research feature."""

from __future__ import annotations

import html
import re
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, quote_plus, unquote, urlparse
from urllib.request import Request, urlopen

from music_assistant.ports.web_search import SearchResult, WebSearch


_ENDPOINT = "https://html.duckduckgo.com/html/"
_RESULT_ANCHOR = re.compile(
    r'<a[^>]+class="[^"]*result__a[^"]*"[^>]+href="([^"]+)"[^>]*>(.*?)</a>',
    re.IGNORECASE | re.DOTALL,
)
_TAG = re.compile(r"<[^>]+>")


class DuckDuckGoSearch(WebSearch):
    """Query DuckDuckGo's no-JS HTML endpoint and return real results.

    Uses only the standard library — no third-party search client, no API key.
    The endpoint occasionally rate-limits; callers should tolerate an empty list.
    """

    def __init__(self, *, timeout_seconds: float = 8.0) -> None:
        self.timeout_seconds = timeout_seconds

    def search(self, query: str, *, limit: int = 10) -> list[SearchResult]:
        body = f"q={quote_plus(query)}".encode()
        request = Request(
            _ENDPOINT,
            data=body,
            method="POST",
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (X11; Linux x86_64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0 Safari/537.36"
                ),
                "Content-Type": "application/x-www-form-urlencoded",
                "Accept": "text/html,application/xhtml+xml",
            },
        )
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                charset = response.headers.get_content_charset() or "utf-8"
                page = response.read(2_000_000).decode(charset, errors="replace")
        except (HTTPError, URLError, TimeoutError, ValueError):
            return []

        results: list[SearchResult] = []
        seen: set[str] = set()
        for href, inner in _RESULT_ANCHOR.findall(page):
            url = _resolve(href)
            if not url or url in seen:
                continue
            seen.add(url)
            title = html.unescape(_TAG.sub("", inner)).strip()
            results.append(SearchResult(url=url, title=title, site=_site(url)))
            if len(results) >= limit:
                break
        return results


def _resolve(href: str) -> str:
    """DDG wraps outbound links as //duckduckgo.com/l/?uddg=<encoded>."""
    if href.startswith("//"):
        href = "https:" + href
    parsed = urlparse(href)
    if parsed.netloc.endswith("duckduckgo.com") and parsed.path.startswith("/l/"):
        uddg = parse_qs(parsed.query).get("uddg")
        if uddg:
            return unquote(uddg[0])
        return ""
    if parsed.scheme in ("http", "https"):
        return href
    return ""


def _site(url: str) -> str:
    host = urlparse(url).netloc
    return host[4:] if host.startswith("www.") else host
