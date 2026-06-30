"""HTTP fetching for web research."""

from __future__ import annotations

from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from music_assistant.ports.page_fetcher import PageFetcher


class UrlLibPageFetcher(PageFetcher):
    def __init__(self, *, timeout_seconds: float = 8.0) -> None:
        self.timeout_seconds = timeout_seconds

    def fetch(self, url: str) -> str:
        request = Request(
            url,
            headers={
                "User-Agent": "MusicAssistantResearch/0.1 (+local educational prototype)",
                "Accept": "text/html,application/xhtml+xml",
            },
        )
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                content_type = response.headers.get_content_charset() or "utf-8"
                return response.read(1_000_000).decode(content_type, errors="replace")
        except (HTTPError, URLError, TimeoutError, ValueError) as exc:
            raise RuntimeError(f"could not fetch {url}: {exc}") from exc
