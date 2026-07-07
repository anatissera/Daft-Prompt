from __future__ import annotations

import json

from music_assistant.infrastructure.storage.in_memory_songsterr_tab_store import InMemorySongsterrTabStore
from music_assistant.infrastructure.web_research.fetch import CurlPageFetcher
from music_assistant.infrastructure.web_research.songsterr_tabs import SongsterrTabLoader
from music_assistant.ports.page_fetcher import PageFetcher
from music_assistant.ports.song_source_connector import ResolvedSongQuery


class FixtureFetcher(PageFetcher):
    def __init__(self, pages: dict[str, str], errors: dict[str, RuntimeError] | None = None) -> None:
        self.pages = pages
        self.errors = errors or {}
        self.urls: list[str] = []

    def fetch(self, url: str) -> str:
        self.urls.append(url)
        if url in self.errors:
            raise self.errors[url]
        return self.pages[url]


class AdvancingClock:
    def __init__(self, values: list[float]) -> None:
        self.values = values
        self.index = 0

    def __call__(self) -> float:
        value = self.values[min(self.index, len(self.values) - 1)]
        self.index += 1
        return value


def songsterr_state_html(*, tracks: list[dict] | None = None, song_id: int = 371, revision_id: int = 7564044, image: str = "v0-test-image") -> str:
    state = {
        "meta": {
            "current": {
                "songId": song_id,
                "revisionId": revision_id,
                "image": image,
                "title": "Another One Bites the Dust",
                "artist": "Queen",
                "tempo": {"bpm": 110, "type": 4},
                "tracks": tracks or [
                    {
                        "partId": 4,
                        "name": "John Deacon | Fender Precision Bass",
                        "instrument": "Electric Bass (finger)",
                        "isBassGuitar": True,
                        "isDrums": False,
                        "isGuitar": False,
                        "isPiano": False,
                        "tuning": ["E1", "A1", "D2", "G2"],
                        "difficulty": "beginner",
                    },
                    {
                        "partId": 6,
                        "name": "Roger Taylor | Drum Loops",
                        "instrument": "Drums",
                        "isBassGuitar": False,
                        "isDrums": True,
                        "isGuitar": False,
                        "isPiano": False,
                    },
                    {
                        "partId": 5,
                        "name": "John Deacon | Keyboards",
                        "instrument": "Pad 8 (sweep)",
                        "isBassGuitar": False,
                        "isDrums": False,
                        "isGuitar": False,
                        "isPiano": True,
                    },
                ],
            }
        }
    }
    return f'<html><body><script id="state" type="application/json">{json.dumps(state)}</script></body></html>'


def revision_payload(name: str, *, instrument_id: int = 33) -> str:
    return json.dumps(
        {
            "name": name,
            "instrumentId": instrument_id,
            "measures": [
                {
                    "signature": [4, 4],
                    "marker": {"text": "Intro"},
                    "voices": [
                        {
                            "beats": [
                                {"type": 4, "duration": [1, 4], "notes": [{"string": 3, "fret": 5}]},
                                {"type": 4, "duration": [1, 4], "notes": [{"rest": True}]},
                            ]
                        }
                    ],
                },
                {
                    "signature": [4, 4],
                    "marker": {"text": "Verse I"},
                    "voices": [
                        {
                            "beats": [
                                {"type": 8, "duration": [1, 8], "notes": [{"string": 3, "fret": 0}]},
                            ]
                        }
                    ],
                },
            ],
        }
    )


def test_songsterr_tab_loader_uses_curl_fetcher_by_default():
    loader = SongsterrTabLoader()

    assert isinstance(loader.fetcher, CurlPageFetcher)
    assert loader.fetcher.timeout_seconds == 12.0
    assert loader.total_budget_seconds == 45.0


def test_songsterr_tab_loader_fetches_and_normalizes_all_available_tracks():
    fetcher = FixtureFetcher(
        {
            "https://www.songsterr.com/a/wsa/queen-another-one-bites-the-dust-tab-s371": songsterr_state_html(),
            "https://dqsljvtekg760.cloudfront.net/371/7564044/v0-test-image/4.json": revision_payload("Bass"),
            "https://dqsljvtekg760.cloudfront.net/371/7564044/v0-test-image/6.json": revision_payload("Drums", instrument_id=1024),
            "https://dqsljvtekg760.cloudfront.net/371/7564044/v0-test-image/5.json": revision_payload("Keys", instrument_id=95),
        }
    )
    loader = SongsterrTabLoader(fetcher=fetcher)

    bundle = loader.load_from_tab_url(
        "https://www.songsterr.com/a/wsa/queen-another-one-bites-the-dust-tab-s371",
        ResolvedSongQuery(title="Another One Bites the Dust", artist="Queen"),
    )

    assert bundle is not None
    assert bundle.song_id == 371
    assert bundle.revision_id == 7564044
    assert bundle.tempo_bpm == 110
    assert [track.part_id for track in bundle.tracks] == [4, 6, 5]
    assert bundle.instrument_names == ["bass", "drums", "piano"]
    assert bundle.tracks[0].measures[0].marker == "Intro"
    assert bundle.tracks[0].measures[0].events[0].fret == 5
    assert bundle.tracks[1].is_drums is True


def test_songsterr_tab_loader_uses_cumulative_beat_positions_for_subdivisions():
    payload = {
        "signature": [4, 4],
        "marker": {"text": "Intro"},
        "voices": [
            {
                "beats": [
                    {"type": 8, "duration": [1, 8], "notes": [{"rest": True}]},
                    {"type": 16, "duration": [1, 16], "notes": [{"string": "3", "fret": "5"}]},
                    {"type": 16, "duration": [1, 16], "notes": [{"string": "3", "fret": "3"}]},
                    {"type": 4, "duration": [1, 4], "notes": [{"string": "3", "fret": "0"}]},
                ]
            }
        ],
    }

    bundle = SongsterrTabLoader(
        fetcher=FixtureFetcher(
            {
                "https://www.songsterr.com/a/wsa/queen-another-one-bites-the-dust-bass-tab-s371": songsterr_state_html(
                    tracks=[
                        {
                            "partId": 4,
                            "name": "John Deacon | Fender Precision Bass",
                            "instrument": "Electric Bass (finger)",
                            "isBassGuitar": True,
                            "isDrums": False,
                            "isGuitar": False,
                            "isPiano": False,
                            "tuning": ["43", "38", "33", "28"],
                        }
                    ]
                ),
                "https://dqsljvtekg760.cloudfront.net/371/7564044/v0-test-image/4.json": json.dumps(
                    {"name": "Bass", "measures": [payload]}
                ),
            }
        )
    ).load_from_tab_url(
        "https://www.songsterr.com/a/wsa/queen-another-one-bites-the-dust-bass-tab-s371",
        ResolvedSongQuery(title="Another One Bites the Dust", artist="Queen"),
    )

    assert bundle is not None
    events = bundle.tracks[0].measures[0].events
    assert [event.beat_index for event in events] == [0.0, 0.5, 0.75, 1.0]
    assert events[1].string == 3
    assert events[1].fret == 5


def test_songsterr_tab_loader_exposes_drum_fret_as_gm_pitch_source():
    drum_payload = {
        "signature": [4, 4],
        "marker": {"text": "Intro"},
        "voices": [
            {
                "beats": [
                    {"type": 8, "duration": [1, 8], "notes": [{"string": "-0.5", "fret": "42"}]},
                    {"type": 8, "duration": [1, 8], "notes": [{"string": "1.5", "fret": "38"}]},
                    {"type": 8, "duration": [1, 8], "notes": [{"string": "3.5", "fret": "36"}]},
                ]
            }
        ],
    }

    bundle = SongsterrTabLoader(
        fetcher=FixtureFetcher(
            {
                "https://www.songsterr.com/a/wsa/queen-another-one-bites-the-dust-drum-tab-s371": songsterr_state_html(
                    tracks=[
                        {
                            "partId": 6,
                            "name": "Roger Taylor | Drum Loops",
                            "instrument": "Drums",
                            "isBassGuitar": False,
                            "isDrums": True,
                            "isGuitar": False,
                            "isPiano": False,
                        }
                    ]
                ),
                "https://dqsljvtekg760.cloudfront.net/371/7564044/v0-test-image/6.json": json.dumps(
                    {"name": "Drums", "instrumentId": 1024, "measures": [drum_payload]}
                ),
            }
        )
    ).load_from_tab_url(
        "https://www.songsterr.com/a/wsa/queen-another-one-bites-the-dust-drum-tab-s371",
        ResolvedSongQuery(title="Another One Bites the Dust", artist="Queen"),
    )

    assert bundle is not None
    events = bundle.tracks[0].measures[0].events
    assert [event.fret for event in events] == [42, 38, 36]


def test_songsterr_tab_loader_does_not_expose_string_fret_for_piano_tracks():
    piano_tracks = [
        {
            "partId": 5,
            "name": "John Deacon | Keyboards",
            "instrument": "Pad 8 (sweep)",
            "isBassGuitar": False,
            "isDrums": False,
            "isGuitar": False,
            "isPiano": True,
        }
    ]
    fetcher = FixtureFetcher(
        {
            "https://www.songsterr.com/a/wsa/queen-another-one-bites-the-dust-keyboard-tab-s371": songsterr_state_html(
                tracks=piano_tracks
            ),
            "https://dqsljvtekg760.cloudfront.net/371/7564044/v0-test-image/5.json": revision_payload(
                "Keys",
                instrument_id=95,
            ),
        }
    )

    bundle = SongsterrTabLoader(fetcher=fetcher).load_from_tab_url(
        "https://www.songsterr.com/a/wsa/queen-another-one-bites-the-dust-keyboard-tab-s371",
        ResolvedSongQuery(title="Another One Bites the Dust", artist="Queen"),
    )

    assert bundle is not None
    event = bundle.tracks[0].measures[0].events[0]
    assert bundle.tracks[0].instrument_family == "piano"
    assert event.string is None
    assert event.fret is None
    assert event.raw["string"] == 3
    assert event.raw["fret"] == 5


def test_songsterr_tab_loader_searches_filtered_results_before_loading_tab():
    drum_search_html = """
    <html><body>
      <a href="/a/wsa/queen-another-one-bites-the-dust-drum-tab-s371">
        <div>Another One Bites the Dust</div><div>Queen</div>
      </a>
    </body></html>
    """
    bass_search_html = """
    <html><body>
      <a href="/a/wsa/queen-another-one-bites-the-dust-bass-tab-s371">
        <div>Another One Bites the Dust</div><div>Queen</div>
      </a>
    </body></html>
    """
    bass_tracks = [
        {
            "partId": 4,
            "name": "John Deacon | Fender Precision Bass",
            "instrument": "Electric Bass (finger)",
            "isBassGuitar": True,
            "isDrums": False,
            "isGuitar": False,
            "isPiano": False,
        }
    ]
    drum_tracks = [
        {
            "partId": 6,
            "name": "Roger Taylor | Drum Loops",
            "instrument": "Drums",
            "isBassGuitar": False,
            "isDrums": True,
            "isGuitar": False,
            "isPiano": False,
        }
    ]
    fetcher = FixtureFetcher(
        {
            "https://www.songsterr.com/?pattern=Another+One+Bites+the+Dust+Queen": "<html></html>",
            "https://www.songsterr.com/?pattern=Another+One+Bites+the+Dust+Queen&inst=guitar": "<html></html>",
            "https://www.songsterr.com/?pattern=Another+One+Bites+the+Dust+Queen&inst=bass": bass_search_html,
            "https://www.songsterr.com/?pattern=Another+One+Bites+the+Dust+Queen&inst=drum": drum_search_html,
            "https://www.songsterr.com/?pattern=Another+One+Bites+the+Dust+Queen&inst=piano": "<html></html>",
            "https://www.songsterr.com/a/wsa/queen-another-one-bites-the-dust-bass-tab-s371": songsterr_state_html(tracks=bass_tracks),
            "https://www.songsterr.com/a/wsa/queen-another-one-bites-the-dust-drum-tab-s371": songsterr_state_html(tracks=drum_tracks),
            "https://dqsljvtekg760.cloudfront.net/371/7564044/v0-test-image/4.json": revision_payload("Bass"),
            "https://dqsljvtekg760.cloudfront.net/371/7564044/v0-test-image/6.json": revision_payload("Drums", instrument_id=1024),
        }
    )
    loader = SongsterrTabLoader(fetcher=fetcher)

    bundle = loader.load(ResolvedSongQuery(title="Another One Bites the Dust", artist="Queen"))

    assert bundle is not None
    assert bundle.source_url == "https://www.songsterr.com/a/wsa/queen-another-one-bites-the-dust-bass-tab-s371"
    assert "https://www.songsterr.com/?pattern=Another+One+Bites+the+Dust+Queen&inst=bass" in fetcher.urls
    assert "https://www.songsterr.com/?pattern=Another+One+Bites+the+Dust+Queen&inst=drum" in fetcher.urls
    assert "https://www.songsterr.com/?pattern=Another+One+Bites+the+Dust+Queen&inst=piano" in fetcher.urls
    assert bundle.instrument_names == ["bass", "drums"]
    assert [track.source_url for track in bundle.tracks] == [
        "https://www.songsterr.com/a/wsa/queen-another-one-bites-the-dust-bass-tab-s371",
        "https://www.songsterr.com/a/wsa/queen-another-one-bites-the-dust-drum-tab-s371",
    ]


def test_songsterr_tab_loader_keeps_partial_bundle_when_one_track_fails():
    fetcher = FixtureFetcher(
        {
            "https://www.songsterr.com/a/wsa/queen-another-one-bites-the-dust-tab-s371": songsterr_state_html(),
            "https://dqsljvtekg760.cloudfront.net/371/7564044/v0-test-image/4.json": revision_payload("Bass"),
            "https://dqsljvtekg760.cloudfront.net/371/7564044/v0-test-image/5.json": revision_payload("Keys", instrument_id=95),
        },
        errors={
            "https://dqsljvtekg760.cloudfront.net/371/7564044/v0-test-image/6.json": RuntimeError("HTTP 404"),
        },
    )
    loader = SongsterrTabLoader(fetcher=fetcher)

    bundle = loader.load_from_tab_url(
        "https://www.songsterr.com/a/wsa/queen-another-one-bites-the-dust-tab-s371",
        ResolvedSongQuery(title="Another One Bites the Dust", artist="Queen"),
    )

    assert bundle is not None
    assert [track.part_id for track in bundle.tracks] == [4, 5]
    assert any("part 6" in warning for warning in bundle.warnings)


def test_songsterr_tab_loader_stops_before_new_track_when_total_budget_is_spent():
    fetcher = FixtureFetcher(
        {
            "https://www.songsterr.com/a/wsa/queen-another-one-bites-the-dust-tab-s371": songsterr_state_html(),
            "https://dqsljvtekg760.cloudfront.net/371/7564044/v0-test-image/4.json": revision_payload("Bass"),
            "https://dqsljvtekg760.cloudfront.net/371/7564044/v0-test-image/6.json": revision_payload("Drums", instrument_id=1024),
            "https://dqsljvtekg760.cloudfront.net/371/7564044/v0-test-image/5.json": revision_payload("Keys", instrument_id=95),
        }
    )
    loader = SongsterrTabLoader(fetcher=fetcher, total_budget_seconds=1.0, clock=AdvancingClock([0.0, 0.1, 0.2, 1.5]))

    bundle = loader.load_from_tab_url(
        "https://www.songsterr.com/a/wsa/queen-another-one-bites-the-dust-tab-s371",
        ResolvedSongQuery(title="Another One Bites the Dust", artist="Queen"),
    )

    assert bundle is not None
    assert [track.part_id for track in bundle.tracks] == [4]
    assert "https://dqsljvtekg760.cloudfront.net/371/7564044/v0-test-image/6.json" not in fetcher.urls
    assert any("Songsterr load budget exhausted" in warning for warning in bundle.warnings)


def test_in_memory_songsterr_tab_store_is_process_local():
    store = InMemorySongsterrTabStore()
    bundle = SongsterrTabLoader(
        fetcher=FixtureFetcher(
            {
                "https://www.songsterr.com/a/wsa/queen-another-one-bites-the-dust-tab-s371": songsterr_state_html(),
                "https://dqsljvtekg760.cloudfront.net/371/7564044/v0-test-image/4.json": revision_payload("Bass"),
                "https://dqsljvtekg760.cloudfront.net/371/7564044/v0-test-image/6.json": revision_payload("Drums", instrument_id=1024),
                "https://dqsljvtekg760.cloudfront.net/371/7564044/v0-test-image/5.json": revision_payload("Keys", instrument_id=95),
            }
        )
    ).load_from_tab_url(
        "https://www.songsterr.com/a/wsa/queen-another-one-bites-the-dust-tab-s371",
        ResolvedSongQuery(title="Another One Bites the Dust", artist="Queen"),
    )
    assert bundle is not None

    store.save("ref_queen_another_one_bites_the_dust", bundle)

    assert store.get("ref_queen_another_one_bites_the_dust") is bundle
    assert InMemorySongsterrTabStore().get("ref_queen_another_one_bites_the_dust") is None
