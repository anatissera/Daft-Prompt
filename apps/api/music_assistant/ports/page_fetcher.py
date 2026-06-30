"""HTML fetcher port for web research."""

from __future__ import annotations

from typing import Protocol


class PageFetcher(Protocol):
    def fetch(self, url: str) -> str:
        ...
