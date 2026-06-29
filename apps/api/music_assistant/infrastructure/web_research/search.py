"""Free, lightweight search adapter for the scraping-analysis branch."""

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
                site="Hooktheory",
            ),
            SearchResult(
                url=f"https://www.cifraclub.com.br/?q={encoded}",
                title=f"CifraClub search for {query}",
                site="CifraClub",
            ),
            SearchResult(
                url=f"https://www.lacuerda.net/busca.php?query={encoded}",
                title=f"La Cuerda search for {query}",
                site="La Cuerda",
            ),
            SearchResult(
                url=f"https://www.google.com/search?q={encoded}+chords+key+tempo",
                title=f"Generic music search for {query}",
                site="Search",
            ),
            SearchResult(
                url=f"https://tabs.ultimate-guitar.com/search.php?search_type=title&value={encoded}",
                title=f"Ultimate Guitar search for {query}",
                site="Ultimate Guitar",
            ),
            SearchResult(
                url=f"https://www.hooktheory.com/theorytab/view/{slug}",
                title=f"Hooktheory candidate for {query}",
                site="Hooktheory",
            ),
        ]
        return candidates[:limit]
