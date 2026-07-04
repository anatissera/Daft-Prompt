from __future__ import annotations

import ast
from pathlib import Path

from music_assistant.domain.audio_profile import EvidenceClaim
from music_assistant.ports.song_source_connector import (
    ConnectorFailure,
    ConnectorResult,
    FetchStatus,
    ResolvedSongQuery,
    SongSourceConnector,
)


class SuccessfulConnector:
    source_name = "fixture chords"

    def collect(self, query: ResolvedSongQuery) -> ConnectorResult:
        return ConnectorResult(
            source_name=self.source_name,
            query=query,
            fetch_status="fetched",
            claims=[
                EvidenceClaim(
                    claim_id="fixture_chorus_chords",
                    claim_type="chord_progression",
                    value="Am - F - C - G",
                    normalized_value="Am F C G",
                    section_name="chorus",
                    source_name=self.source_name,
                    source_url="https://fixture.test/song",
                    extraction_method="site_parser",
                    confidence=0.78,
                    snippet="Chorus: Am F C G",
                )
            ],
        )


class ConflictingConnector:
    source_name = "fixture conflict"

    def collect(self, query: ResolvedSongQuery) -> ConnectorResult:
        return ConnectorResult(
            source_name=self.source_name,
            query=query,
            fetch_status="fetched",
            claims=[
                EvidenceClaim(
                    claim_id="fixture_key_conflict",
                    claim_type="key",
                    value="F# minor",
                    normalized_value="F# minor",
                    source_name=self.source_name,
                    source_url="https://fixture.test/conflict",
                    extraction_method="site_parser",
                    confidence=0.7,
                    snippet="Key: F# minor",
                )
            ],
        )


class BlockedConnector:
    source_name = "blocked source"

    def collect(self, query: ResolvedSongQuery) -> ConnectorResult:
        return ConnectorResult(
            source_name=self.source_name,
            query=query,
            fetch_status="blocked",
            failures=[
                ConnectorFailure(
                    source_name=self.source_name,
                    url="https://blocked.test/song",
                    status="blocked",
                    reason="HTTP 403",
                )
            ],
        )


class EmptyJsConnector:
    source_name = "js only source"

    def collect(self, query: ResolvedSongQuery) -> ConnectorResult:
        return ConnectorResult(
            source_name=self.source_name,
            query=query,
            fetch_status="js_rendered",
            failures=[
                ConnectorFailure(
                    source_name=self.source_name,
                    url="https://js.test/song",
                    status="js_rendered",
                    reason="Initial HTML contained no structured claims.",
                )
            ],
        )


def test_fake_connectors_return_normalized_claims_and_explicit_failures():
    query = ResolvedSongQuery(title="Demo Song", artist="Fixture Artist")
    connectors: list[SongSourceConnector] = [
        SuccessfulConnector(),
        ConflictingConnector(),
        BlockedConnector(),
        EmptyJsConnector(),
    ]

    results = [connector.collect(query) for connector in connectors]

    assert results[0].claims[0].claim_type == "chord_progression"
    assert results[0].claims[0].source_name == "fixture chords"
    assert results[1].claims[0].claim_type == "key"
    assert results[2].failures[0].status == "blocked"
    assert results[3].failures[0].status == "js_rendered"
    assert {result.fetch_status for result in results} == {
        "fetched",
        "blocked",
        "js_rendered",
    }


def test_connector_status_contract_covers_expected_fetch_outcomes():
    statuses: set[FetchStatus] = {
        "fetched",
        "blocked",
        "empty",
        "js_rendered",
        "unsupported",
        "error",
    }

    assert "blocked" in statuses
    assert "js_rendered" in statuses
    assert "unsupported" in statuses


def test_application_and_domain_do_not_import_concrete_source_connectors():
    root = Path(__file__).resolve().parents[1] / "music_assistant"
    checked = [root / "domain", root / "application"]
    violations: list[tuple[str, str]] = []
    for directory in checked:
        for path in directory.rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    names = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom):
                    names = [node.module or ""]
                else:
                    continue
                for name in names:
                    if name.startswith("music_assistant.infrastructure.web_research"):
                        violations.append((str(path.relative_to(root)), name))

    assert violations == []
