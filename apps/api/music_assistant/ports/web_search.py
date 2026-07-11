"""Search provider port for web research."""

from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel


class SearchResult(BaseModel):
    url: str
    title: str = ""
    site: str = ""


class WebSearch(Protocol):
    def search(self, query: str, *, limit: int = 10) -> list[SearchResult]:
        ...
