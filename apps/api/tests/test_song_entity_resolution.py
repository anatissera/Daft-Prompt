import json

from music_assistant.infrastructure.web_research.entity_resolution import (
    normalize_match_text,
    query_variants,
    resolve_song_entity,
)
from music_assistant.infrastructure.web_research.musicbrainz import MusicBrainzConnector


class _JsonFetcher:
    def __init__(self, payload):
        self.payload = payload
        self.urls = []

    def fetch(self, url: str) -> str:
        self.urls.append(url)
        return json.dumps(self.payload)


class _TransientJsonFetcher(_JsonFetcher):
    def fetch(self, url: str) -> str:
        self.urls.append(url)
        if len(self.urls) == 1:
            raise RuntimeError("temporary provider failure")
        return json.dumps(self.payload)


def test_entity_resolution_handles_accents_features_collaborations_and_versions():
    accented = resolve_song_entity("Adiós by Gustavo Cerati")
    featured = resolve_song_entity("Uptown Funk (feat. Bruno Mars) by Mark Ronson")
    collaboration = resolve_song_entity("Empire State of Mind by Jay-Z & Alicia Keys")
    remix = resolve_song_entity("Summertime Sadness (Cedric Gervais Remix) by Lana Del Rey")
    produced = resolve_song_entity("Track Name (prod. Metro Boomin) by Future")

    assert accented.alternate_titles == ["Adios"]
    assert featured.title == "Uptown Funk"
    assert featured.primary_artists == ["Mark Ronson"]
    assert featured.featured_artists == ["Bruno Mars"]
    assert collaboration.primary_artists == ["Jay-Z", "Alicia Keys"]
    assert remix.version == "Cedric Gervais Remix"
    assert remix.remix_artist == "Cedric Gervais"
    assert produced.producers == ["Metro Boomin"]
    assert any(variant.title == "Adios" for variant in query_variants(accented))
    assert normalize_match_text("SICKO MODE") == "sicko mode"


def test_musicbrainz_accepts_correct_identity_and_preserves_featured_credit():
    fetcher = _JsonFetcher({
        "recordings": [{
            "id": "recording-1",
            "score": 100,
            "title": "Uptown Funk",
            "first-release-date": "2014-11-10",
            "artist-credit": [
                {"name": "Mark Ronson", "joinphrase": " feat. "},
                {"name": "Bruno Mars", "joinphrase": ""},
            ],
            "releases": [{"title": "Uptown Special"}],
        }],
    })
    connector = MusicBrainzConnector(fetcher=fetcher)

    result = connector.collect(resolve_song_entity("Uptown Funk by Mark Ronson featuring Bruno Mars"))

    assert result.fetch_status == "fetched"
    assert result.query.title == "Uptown Funk"
    assert result.query.primary_artists == ["Mark Ronson"]
    assert result.query.featured_artists == ["Bruno Mars"]
    assert result.query.album == "Uptown Special"
    assert result.query.year == 2014
    assert {claim.claim_type for claim in result.claims} == {"metadata", "credit"}


def test_musicbrainz_rejects_high_provider_score_when_artist_is_wrong():
    connector = MusicBrainzConnector(fetcher=_JsonFetcher({
        "recordings": [{
            "id": "wrong",
            "score": 100,
            "title": "Hello",
            "artist-credit": [{"name": "Lionel Richie", "joinphrase": ""}],
        }],
    }))

    result = connector.collect(resolve_song_entity("Hello by Adele"))

    assert result.claims == []
    assert result.fetch_status == "empty"
    assert result.query.candidate_matches == ["Hello — Lionel Richie"]


def test_musicbrainz_retries_one_transient_provider_failure():
    fetcher = _TransientJsonFetcher({
        "recordings": [{
            "id": "get-lucky",
            "score": 100,
            "title": "Get Lucky",
            "artist-credit": [{"name": "Daft Punk", "joinphrase": ""}],
        }],
    })

    result = MusicBrainzConnector(fetcher=fetcher).collect(resolve_song_entity("Get Lucky by Daft Punk"))

    assert result.fetch_status == "fetched"
    assert len(fetcher.urls) == 2
