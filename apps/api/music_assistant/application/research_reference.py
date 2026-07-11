"""Research a song from public web evidence."""

from __future__ import annotations

from music_assistant.domain.audio_profile import ReferenceProfile
from music_assistant.ports.song_researcher import SongResearcher


class ResearchReference:
    def __init__(self, researcher: SongResearcher) -> None:
        self.researcher = researcher

    def execute(self, query: str) -> ReferenceProfile:
        cleaned = query.strip()
        if not cleaned:
            raise ValueError("research query cannot be empty")
        return self.researcher.research(cleaned)
