"""HTTP fetching for web research."""

from __future__ import annotations

import subprocess
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


class CurlPageFetcher(PageFetcher):
    def __init__(self, *, timeout_seconds: float = 8.0) -> None:
        self.timeout_seconds = timeout_seconds

    def fetch(self, url: str) -> str:
        try:
            completed = subprocess.run(
                [
                    "curl",
                    "-L",
                    "--max-time",
                    str(int(self.timeout_seconds)),
                    "--silent",
                    "--show-error",
                    url,
                ],
                check=False,
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds + 2,
            )
        except FileNotFoundError as exc:
            raise RuntimeError("curl is not available for fallback fetch") from exc
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(f"curl timed out fetching {url}") from exc
        if completed.returncode != 0:
            message = completed.stderr.strip() or f"curl exited {completed.returncode}"
            raise RuntimeError(message)
        return completed.stdout


class FallbackPageFetcher(PageFetcher):
    def __init__(
        self,
        *,
        primary: PageFetcher,
        fallback: PageFetcher,
        retry_when: str,
    ) -> None:
        self.primary = primary
        self.fallback = fallback
        self.retry_when = retry_when

    def fetch(self, url: str) -> str:
        try:
            return self.primary.fetch(url)
        except RuntimeError as exc:
            primary_error = exc
        if self.retry_when not in str(primary_error):
            raise primary_error
        try:
            return self.fallback.fetch(url)
        except RuntimeError:
            raise primary_error
