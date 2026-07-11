"""Default orchestration for research-only song analysis."""

from __future__ import annotations

from music_assistant.domain.audio_profile import ReferenceProfile
from music_assistant.infrastructure.web_research.fetch import UrlLibPageFetcher
from music_assistant.infrastructure.web_research.fusion import EvidenceFuser
from music_assistant.infrastructure.web_research.parsers import GenericSongPageParser
from music_assistant.infrastructure.web_research.search import DuckDuckGoSearch
from music_assistant.ports.page_fetcher import PageFetcher
from music_assistant.ports.song_researcher import SongResearcher
from music_assistant.ports.web_search import WebSearch


class DefaultSongResearcher(SongResearcher):
    def __init__(
        self,
        *,
        search: WebSearch | None = None,
        fetcher: PageFetcher | None = None,
        parser: GenericSongPageParser | None = None,
        fuser: EvidenceFuser | None = None,
    ) -> None:
        self.search = search or DuckDuckGoSearch()
        self.fetcher = fetcher or UrlLibPageFetcher()
        self.parser = parser or GenericSongPageParser()
        self.fuser = fuser or EvidenceFuser()

    def research(self, query: str) -> ReferenceProfile:
        pages = []
        for result in self.search.search(query, limit=12):
            try:
                html_text = self.fetcher.fetch(result.url)
            except RuntimeError:
                continue
            page = self.parser.parse(result, html_text)
            if page.claims:
                pages.append(page)
        return self.fuser.fuse(query, pages)
