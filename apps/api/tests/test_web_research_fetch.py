from __future__ import annotations

import subprocess

import pytest

from music_assistant.infrastructure.web_research.fetch import FallbackPageFetcher


class FailingFetcher:
    def __init__(self, message: str) -> None:
        self.message = message

    def fetch(self, url: str) -> str:
        raise RuntimeError(self.message)


class RecordingFetcher:
    def __init__(self, html: str) -> None:
        self.html = html
        self.urls: list[str] = []

    def fetch(self, url: str) -> str:
        self.urls.append(url)
        return self.html


def test_fallback_page_fetcher_uses_fallback_for_http_103_errors():
    fallback = RecordingFetcher("<html>Songsterr</html>")
    fetcher = FallbackPageFetcher(
        primary=FailingFetcher("could not fetch https://song.test: HTTP Error 103: Early Hints"),
        fallback=fallback,
        retry_when="HTTP Error 103",
    )

    html = fetcher.fetch("https://song.test")

    assert html == "<html>Songsterr</html>"
    assert fallback.urls == ["https://song.test"]


def test_fallback_page_fetcher_keeps_primary_error_when_fallback_fails():
    fetcher = FallbackPageFetcher(
        primary=FailingFetcher("could not fetch https://song.test: HTTP Error 103: Early Hints"),
        fallback=FailingFetcher("curl exited 28"),
        retry_when="HTTP Error 103",
    )

    with pytest.raises(RuntimeError, match="HTTP Error 103"):
        fetcher.fetch("https://song.test")


def test_fallback_page_fetcher_does_not_retry_unrelated_errors():
    fallback = RecordingFetcher("<html>unused</html>")
    fetcher = FallbackPageFetcher(
        primary=FailingFetcher("could not fetch https://song.test: HTTP Error 404: Not Found"),
        fallback=fallback,
        retry_when="HTTP Error 103",
    )

    with pytest.raises(RuntimeError, match="HTTP Error 404"):
        fetcher.fetch("https://song.test")
    assert fallback.urls == []


def test_curl_page_fetcher_reports_missing_curl(monkeypatch):
    from music_assistant.infrastructure.web_research.fetch import CurlPageFetcher

    def raise_missing(*args, **kwargs):
        raise FileNotFoundError("curl")

    monkeypatch.setattr(subprocess, "run", raise_missing)
    fetcher = CurlPageFetcher(timeout_seconds=1)

    with pytest.raises(RuntimeError, match="curl is not available"):
        fetcher.fetch("https://song.test")
