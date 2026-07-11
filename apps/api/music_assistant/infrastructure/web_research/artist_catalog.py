"""Small provider-free artist catalog used as a first style-profile seed."""

from __future__ import annotations

from music_assistant.ports.artist_catalog import ArtistCatalog, ArtistSongCandidate


_SEEDED_ARTISTS: dict[str, list[str]] = {
    "daft punk": [
        "One More Time",
        "Around the World",
        "Digital Love",
        "Harder Better Faster Stronger",
    ],
    "twenty one pilots": [
        "Stressed Out",
        "Ride",
        "Heathens",
        "Chlorine",
    ],
    "jamiroquai": [
        "Virtual Insanity",
        "Space Cowboy",
        "Cosmic Girl",
        "Canned Heat",
    ],
    "queen": [
        "Another One Bites the Dust",
        "Bohemian Rhapsody",
        "Don't Stop Me Now",
        "Under Pressure",
    ],
    "nirvana": [
        "Smells Like Teen Spirit",
        "Come As You Are",
        "Lithium",
        "In Bloom",
    ],
}


class SeededArtistCatalog(ArtistCatalog):
    def representative_songs(self, artist_name: str, *, limit: int = 6) -> list[ArtistSongCandidate]:
        songs = _SEEDED_ARTISTS.get(artist_name.strip().casefold(), [])
        return [
            ArtistSongCandidate(
                title=title,
                artist=artist_name,
                reason="seeded popular/tab-available representative",
                popularity_rank=index + 1,
                tab_likely=True,
                source_name="seeded artist catalog",
                confidence=0.58,
            )
            for index, title in enumerate(songs[:limit])
        ]
