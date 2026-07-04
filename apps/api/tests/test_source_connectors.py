from __future__ import annotations

from pathlib import Path

import pytest

from music_assistant.infrastructure.web_research.connectors import (
    CifraClubConnector,
    HookTheoryConnector,
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


@pytest.mark.parametrize("connector_cls", [HookTheoryConnector, CifraClubConnector])
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


@pytest.mark.parametrize("connector_cls", [HookTheoryConnector, CifraClubConnector])
def test_connectors_report_js_only_or_empty_pages(connector_cls):
    connector = connector_cls(
        fetcher=FixtureFetcher({"https://fixture.test/js": read_fixture("js_only.html")})
    )
    query = ResolvedSongQuery(title="JS Song", source_url="https://fixture.test/js")

    result = connector.collect(query)

    assert result.fetch_status == "js_rendered"
    assert result.claims == []
    assert result.failures[0].status == "js_rendered"
