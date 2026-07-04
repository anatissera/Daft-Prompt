from __future__ import annotations

from music_assistant.domain.audio_profile import EvidenceClaim
from music_assistant.infrastructure.web_research.fusion import EvidenceFuser
from music_assistant.ports.song_source_connector import ConnectorResult, ResolvedSongQuery


def claim(
    claim_id: str,
    claim_type: str,
    value: str,
    *,
    source: str,
    section: str | None = None,
    confidence: float = 0.7,
    notes: list[str] | None = None,
) -> EvidenceClaim:
    return EvidenceClaim(
        claim_id=claim_id,
        claim_type=claim_type,  # type: ignore[arg-type]
        value=value,
        normalized_value=value,
        section_name=section,
        source_name=source,
        source_url=f"https://{source.lower().replace(' ', '-')}.test/song",
        extraction_method="site_parser",
        confidence=confidence,
        snippet=f"{claim_type}: {value}",
        notes=notes or [],
    )


def result(source: str, query: ResolvedSongQuery, claims: list[EvidenceClaim]) -> ConnectorResult:
    return ConnectorResult(source_name=source, query=query, fetch_status="fetched", claims=claims)


def test_fuse_connector_claims_builds_traceable_song_knowledge_profile():
    query = ResolvedSongQuery(title="Space Cowboy", artist="Jamiroquai")
    results = [
        result(
            "HookTheory",
            query,
            [
                claim("tempo_ht", "tempo", "111 BPM", source="HookTheory", confidence=0.8),
                claim("key_ht", "key", "A minor", source="HookTheory", confidence=0.75),
                claim("chorus_ht", "chord_progression", "Bm7 - E9 - Amaj7", source="HookTheory", section="chorus"),
                claim("section_ht", "section", "chorus", source="HookTheory", section="chorus"),
            ],
        ),
        result(
            "CifraClub",
            query,
            [
                claim("tempo_cc", "tempo", "111 bpm", source="CifraClub", confidence=0.65),
                claim("key_cc", "key", "Am", source="CifraClub", confidence=0.62),
                claim("chorus_cc", "chord_progression", "Bm7 E9 Amaj7", source="CifraClub", section="chorus"),
            ],
        ),
    ]

    profile = EvidenceFuser().fuse_connector_results(query, results)

    assert profile.identity.title == "Space Cowboy"
    assert profile.identity.artist == "Jamiroquai"
    assert profile.confidence_summary["tempo"] == "high"
    assert profile.confidence_summary["key"] == "medium"
    assert profile.conflicts == []
    assert len(profile.sections) == 1
    assert profile.sections[0].name == "chorus"
    assert profile.sections[0].start_seconds is None
    assert profile.sections[0].timestamp_confidence is None
    assert len(profile.sections[0].chord_claims) == 2


def test_fusion_preserves_key_and_chord_conflicts():
    query = ResolvedSongQuery(title="Conflict Demo")
    results = [
        result(
            "One",
            query,
            [
                claim("key_one", "key", "A major", source="One", confidence=0.8),
                claim("chorus_one", "chord_progression", "A - E - F#m - D", source="One", section="chorus"),
            ],
        ),
        result(
            "Two",
            query,
            [
                claim("key_two", "key", "C major", source="Two", confidence=0.78),
                claim("chorus_two", "chord_progression", "C - G - Am - F", source="Two", section="chorus"),
            ],
        ),
    ]

    profile = EvidenceFuser().fuse_connector_results(query, results)

    assert {conflict.claim_type for conflict in profile.conflicts} == {"key", "chord_progression"}
    assert profile.confidence_summary["key"] == "conflicting"
    assert profile.confidence_summary["harmony"] == "conflicting"


def test_fusion_detects_likely_capo_or_transposition_without_flattening_conflict():
    query = ResolvedSongQuery(title="Capo Demo")
    results = [
        result(
            "Tabs",
            query,
            [
                claim(
                    "tabs_chords",
                    "chord_progression",
                    "G - D - Em - C",
                    source="Tabs",
                    section="verse",
                    notes=["capo 2"],
                )
            ],
        ),
        result(
            "Theory",
            query,
            [
                claim(
                    "theory_chords",
                    "chord_progression",
                    "A - E - F#m - D",
                    source="Theory",
                    section="verse",
                )
            ],
        ),
    ]

    profile = EvidenceFuser().fuse_connector_results(query, results)

    assert profile.conflicts
    assert "capo" in profile.conflicts[0].description.lower()
    assert "capo_or_transposition" in profile.conflicts[0].resolution


def test_fusion_records_missing_data_and_section_lyrics_without_fake_timestamps():
    query = ResolvedSongQuery(title="Sparse Demo", artist="Fixture Artist")
    results = [
        result(
            "LyricsSource",
            query,
            [
                claim("verse_section", "section", "verse", source="LyricsSource", section="verse"),
                claim("verse_lyrics", "lyrics", "section lyric locator", source="LyricsSource", section="verse"),
            ],
        )
    ]

    profile = EvidenceFuser().fuse_connector_results(query, results)

    assert profile.sections[0].lyric_claims[0].claim_type == "lyrics"
    assert profile.sections[0].start_seconds is None
    assert any(item.field == "tempo" for item in profile.missing_data)
    assert any(item.field == "section_timestamps" for item in profile.missing_data)
