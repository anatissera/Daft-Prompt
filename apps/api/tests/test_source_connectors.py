from __future__ import annotations

from pathlib import Path

import pytest

from music_assistant.infrastructure.web_research.connectors import (
    CifraClubConnector,
    HookTheoryConnector,
    LaCuerdaConnector,
    SongsterrConnector,
)
from music_assistant.ports.page_fetcher import PageFetcher
from music_assistant.ports.song_source_connector import ResolvedSongQuery


FIXTURE_DIR = Path(__file__).parent / "fixtures" / "web_sources"


class FixtureFetcher(PageFetcher):
    def __init__(self, pages: dict[str, str], errors: dict[str, RuntimeError] | None = None) -> None:
        self.pages = pages
        self.errors = errors or {}

    def fetch(self, url: str) -> str:
        if url in self.errors:
            raise self.errors[url]
        return self.pages[url]


def read_fixture(name: str) -> str:
    return (FIXTURE_DIR / name).read_text(encoding="utf-8")


def test_hooktheory_connector_extracts_metadata_sections_and_progressions():
    connector = HookTheoryConnector(
        fetcher=FixtureFetcher({"https://fixture.test/hook": read_fixture("hooktheory_space_cowboy.html")})
    )
    query = ResolvedSongQuery(title="Space Cowboy", artist="Jamiroquai", source_url="https://fixture.test/hook")

    result = connector.collect(query)

    assert result.fetch_status == "fetched"
    assert result.failures == []
    assert {claim.claim_type for claim in result.claims} >= {"key", "tempo", "meter", "chord_progression", "section"}
    assert any(claim.value == "111 BPM" for claim in result.claims)
    assert any(claim.section_name == "chorus" and "Bm7" in claim.value for claim in result.claims)
    assert all(claim.source_name == "HookTheory" for claim in result.claims)
    assert all(claim.extraction_method == "site_parser" for claim in result.claims)


def test_cifraclub_connector_extracts_key_and_section_chords():
    connector = CifraClubConnector(
        fetcher=FixtureFetcher({"https://fixture.test/cifra": read_fixture("cifraclub_space_cowboy.html")})
    )
    query = ResolvedSongQuery(title="Space Cowboy", artist="Jamiroquai", source_url="https://fixture.test/cifra")

    result = connector.collect(query)

    assert result.fetch_status == "fetched"
    assert any(claim.claim_type == "key" and claim.value == "Am" for claim in result.claims)
    assert any(claim.claim_type == "chord_progression" and claim.section_name == "chorus" for claim in result.claims)
    assert all(claim.source_name == "CifraClub" for claim in result.claims)


def test_cifraclub_connector_normalizes_portuguese_section_names_to_english():
    html = """
    <html><body>
      <div class="tom">Tom: Db</div>
      <pre>
[Refrão]
<b>Ebm7(9)</b> lyrics
<b>Fm7(9)</b> <b>Bbm7(9)</b>

[Segunda Parte]
<b>Db7M(9)</b> lyrics
      </pre>
    </body></html>
    """
    connector = CifraClubConnector(fetcher=FixtureFetcher({"https://fixture.test/cifra": html}))
    query = ResolvedSongQuery(title="Space Cowboy", artist="Jamiroquai", source_url="https://fixture.test/cifra")

    result = connector.collect(query)

    assert any(claim.claim_type == "section" and claim.value == "chorus" for claim in result.claims)
    assert any(claim.claim_type == "section" and claim.value == "verse 2" for claim in result.claims)
    assert any(claim.claim_type == "chord_progression" and claim.section_name == "chorus" for claim in result.claims)
    assert any(claim.claim_type == "chord_progression" and claim.section_name == "verse 2" for claim in result.claims)


def test_cifraclub_connector_preserves_numbered_section_instances():
    html = """
    <html><body>
      <div class="tom">Tom: Em</div>
      <pre>
[Dedilhado - Intro]
<b>Em</b> <b>A</b>

[Primeira Parte]
<b>Em</b> <b>A</b> <b>D</b>

[Refrão 1]
<b>Bm</b> <b>F#m7</b> <b>G</b> <b>D</b>

[Segunda Parte]
<b>Em</b> <b>A</b> <b>D</b>

[Refrão 2]
<b>Bm</b> <b>F#m7</b> <b>G</b> <b>D</b>

[Terceira Parte]
<b>G</b> <b>D/F#</b> <b>A</b>

[Dedilhado - Interlúdio]
<b>Em</b> <b>A</b>
      </pre>
    </body></html>
    """
    connector = CifraClubConnector(fetcher=FixtureFetcher({"https://fixture.test/cifra": html}))
    query = ResolvedSongQuery(title="Adios", artist="Gustavo Cerati", source_url="https://fixture.test/cifra")

    result = connector.collect(query)

    section_names = [claim.value for claim in result.claims if claim.claim_type == "section"]
    assert section_names == [
        "intro",
        "verse 1",
        "chorus 1",
        "verse 2",
        "chorus 2",
        "verse 3",
        "interlude",
    ]
    assert any(claim.claim_type == "chord_progression" and claim.section_name == "chorus 1" for claim in result.claims)
    assert any(claim.claim_type == "chord_progression" and claim.section_name == "chorus 2" for claim in result.claims)


def test_lacuerda_connector_extracts_sections_and_chords():
    connector = LaCuerdaConnector(
        fetcher=FixtureFetcher({"https://fixture.test/lacuerda": read_fixture("lacuerda_adios.html")})
    )
    query = ResolvedSongQuery(title="Adios", artist="Gustavo Cerati", source_url="https://fixture.test/lacuerda")

    result = connector.collect(query)

    assert result.fetch_status == "fetched"
    assert any(claim.claim_type == "section" and claim.value == "intro" for claim in result.claims)
    assert any(claim.claim_type == "section" and claim.value == "chorus" for claim in result.claims)
    assert any(
        claim.claim_type == "chord_progression"
        and claim.section_name == "chorus"
        and "Bm" in claim.value
        for claim in result.claims
    )
    assert all(claim.source_name == "LaCuerda" for claim in result.claims)


def test_songsterr_connector_extracts_instrument_tracks_and_tab_availability():
    connector = SongsterrConnector(
        fetcher=FixtureFetcher({"https://fixture.test/songsterr": read_fixture("songsterr_adios.html")})
    )
    query = ResolvedSongQuery(title="Adios", artist="Gustavo Cerati", source_url="https://fixture.test/songsterr")

    result = connector.collect(query)

    assert result.fetch_status == "fetched"
    assert any(claim.claim_type == "tab" and "Guitar tab available" in claim.value for claim in result.claims)
    assert any(claim.claim_type == "instrumentation" and "bass" in claim.value.lower() for claim in result.claims)
    assert any(claim.claim_type == "instrumentation" and "drums" in claim.value.lower() for claim in result.claims)
    assert {"guitar_tab", "bass_tab", "drum_tab"} <= {part.kind for part in result.playable_parts}
    assert all(claim.source_name == "Songsterr" for claim in result.claims)


def test_songsterr_connector_extracts_search_result_tabs_without_global_filter_false_positives():
    connector = SongsterrConnector(
        fetcher=FixtureFetcher({"https://fixture.test/songsterr": read_fixture("songsterr_search_results.html")})
    )
    query = ResolvedSongQuery(
        title="Another One Bites the Dust",
        artist="Queen",
        source_url="https://fixture.test/songsterr",
    )

    result = connector.collect(query)

    assert result.fetch_status == "fetched"
    assert any(
        claim.claim_type == "metadata"
        and "Another One Bites the Dust" in claim.value
        and "Queen" in claim.value
        for claim in result.claims
    )
    assert any(claim.claim_type == "tab" and "Generic tab available" in claim.value for claim in result.claims)
    assert any(claim.claim_type == "tab" and "Bass tab available" in claim.value for claim in result.claims)
    assert any(claim.claim_type == "tab" and "Drum tab available" in claim.value for claim in result.claims)
    assert {"bass_tab", "drum_tab"} <= {part.kind for part in result.playable_parts}


def test_songsterr_connector_does_not_use_global_filters_as_instrument_evidence():
    connector = SongsterrConnector(
        fetcher=FixtureFetcher({"https://fixture.test/songsterr": read_fixture("songsterr_global_filters_only.html")})
    )
    query = ResolvedSongQuery(
        title="Another One Bites the Dust",
        artist="Queen",
        source_url="https://fixture.test/songsterr",
    )

    result = connector.collect(query)

    assert result.fetch_status == "fetched"
    assert any(claim.claim_type == "tab" and "Generic tab available" in claim.value for claim in result.claims)
    assert not any("Bass tab available" in claim.value for claim in result.claims)
    assert not any("Drum tab available" in claim.value for claim in result.claims)


@pytest.mark.parametrize(
    "connector_cls",
    [
        HookTheoryConnector,
        CifraClubConnector,
        LaCuerdaConnector,
        SongsterrConnector,
    ],
)
def test_connectors_report_blocked_fetches(connector_cls):
    connector = connector_cls(
        fetcher=FixtureFetcher(
            {},
            {"https://fixture.test/blocked": RuntimeError("HTTP 403")},
        )
    )
    query = ResolvedSongQuery(title="Blocked Song", source_url="https://fixture.test/blocked")

    result = connector.collect(query)

    assert result.fetch_status == "blocked"
    assert result.claims == []
    assert result.failures[0].status == "blocked"
    assert "HTTP 403" in result.failures[0].reason


@pytest.mark.parametrize(
    "connector_cls",
    [
        HookTheoryConnector,
        CifraClubConnector,
        LaCuerdaConnector,
        SongsterrConnector,
    ],
)
def test_connectors_report_js_only_or_empty_pages(connector_cls):
    connector = connector_cls(
        fetcher=FixtureFetcher({"https://fixture.test/js": read_fixture("js_only.html")})
    )
    query = ResolvedSongQuery(title="JS Song", source_url="https://fixture.test/js")

    result = connector.collect(query)

    assert result.fetch_status == "js_rendered"
    assert result.claims == []
    assert result.failures[0].status == "js_rendered"
