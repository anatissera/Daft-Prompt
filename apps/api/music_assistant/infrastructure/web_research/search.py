"""Free, lightweight search adapter for the web-research feature."""

from __future__ import annotations

from urllib.parse import quote_plus

from music_assistant.ports.web_search import SearchResult, WebSearch


class SeededWebSearch(WebSearch):
    """Build candidate URLs without requiring a paid search API."""

    def search(self, query: str, *, limit: int = 10) -> list[SearchResult]:
        encoded = quote_plus(query)
        slug = quote_plus(query.lower().replace(" ", "-"))
        candidates = [
            SearchResult(
                url=f"https://www.hooktheory.com/theorytab/search?q={encoded}",
                title=f"Hooktheory search for {query}",
                site="HookTheory",
            ),
            SearchResult(
                url=f"https://www.cifraclub.com.br/?q={encoded}",
                title=f"CifraClub search for {query}",
                site="CifraClub",
            ),
            SearchResult(
                url=f"https://www.lacuerda.net/busca.php?query={encoded}",
                title=f"La Cuerda search for {query}",
                site="LaCuerda",
            ),
            SearchResult(
                url=f"https://www.google.com/search?q={encoded}+chords+key+tempo",
                title=f"Generic music search for {query}",
                site="Search",
            ),
            SearchResult(
                url=f"https://www.songsterr.com/a/wa/search?pattern={encoded}",
                title=f"Songsterr search for {query}",
                site="Songsterr",
            ),
            SearchResult(
                url=f"https://www.songsterr.com/?pattern={encoded}&inst=guitar",
                title=f"Songsterr guitar search for {query}",
                site="Songsterr",
            ),
            SearchResult(
                url=f"https://www.songsterr.com/?pattern={encoded}&inst=bass",
                title=f"Songsterr bass search for {query}",
                site="Songsterr",
            ),
            SearchResult(
                url=f"https://www.songsterr.com/?pattern={encoded}&inst=drum",
                title=f"Songsterr drum search for {query}",
                site="Songsterr",
            ),
            SearchResult(
                url=f"https://www.songsterr.com/?pattern={encoded}&inst=piano",
                title=f"Songsterr piano search for {query}",
                site="Songsterr",
            ),
            SearchResult(
                url=f"https://www.hooktheory.com/theorytab/view/{slug}",
                title=f"Hooktheory candidate for {query}",
                site="HookTheory",
            ),
        ]
        return candidates[:limit]


class BroadMusicWebSearch(WebSearch):
    """Small, provider-free candidate set for artist/album/style research."""

    def search(self, query: str, *, limit: int = 10) -> list[SearchResult]:
        grounded = quote_plus(f"{query} instrumentation production sound tempo genre")
        wiki = quote_plus(query)
        candidates = [
            SearchResult(
                url=f"https://html.duckduckgo.com/html/?q={grounded}",
                title=f"Music production research for {query}",
                site="DuckDuckGo",
            ),
            SearchResult(
                url=f"https://en.wikipedia.org/w/index.php?search={wiki}",
                title=f"Background research for {query}",
                site="Wikipedia",
            ),
        ]
        return candidates[:limit]
