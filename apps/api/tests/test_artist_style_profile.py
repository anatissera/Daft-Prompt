from __future__ import annotations

from music_assistant.application.artist_style_profile import (
    ArtistStyleProfileRequest,
    BuildArtistStyleProfile,
)
from music_assistant.application.composition_brief import BuildCompositionBrief
from music_assistant.domain.audio_profile import (
    EvidenceClaim,
    PlayablePart,
    ReferenceProfile,
    ReferenceSource,
    SongIdentity,
    SongKnowledgeProfile,
    ToneProfile,
)
from music_assistant.ports.artist_catalog import ArtistSongCandidate


class FakeCatalog:
    def representative_songs(self, artist_name: str, *, limit: int = 6) -> list[ArtistSongCandidate]:
        return [
            ArtistSongCandidate(
                title="Tabbed Hit",
                artist=artist_name,
                reason="popular and tab available",
                popularity_rank=1,
                tab_likely=True,
                source_name="fixture",
                confidence=0.82,
            ),
            ArtistSongCandidate(
                title="Deep Cut",
                artist=artist_name,
                reason="representative contrast",
                popularity_rank=4,
                tab_likely=False,
                source_name="fixture",
                confidence=0.62,
            ),
        ][:limit]


class FakeResearcher:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def research(self, query: str) -> ReferenceProfile:
        self.calls.append(query)
        if "Tabbed Hit" in query:
            knowledge = _knowledge(
                "Tabbed Hit",
                tempo="124 BPM",
                progression="Am - F - C - G",
                tab=True,
                traits=["punchy chorus drums", "melodic bass"],
                genre="alt pop",
            )
        else:
            knowledge = _knowledge(
                "Deep Cut",
                tempo="96 BPM",
                progression="Dm - Bb - F - C",
                tab=False,
                traits=["sparse piano verse", "wide synth chorus"],
                genre="rap rock",
            )
        return ReferenceProfile(
            reference_id=knowledge.profile_id.replace("song_", "ref_", 1),
            source=ReferenceSource(
                reference_id=knowledge.profile_id.replace("song_", "ref_", 1),
                kind="metadata",
                label=query,
                uri=f"research://{query}",
                authorized=True,
            ),
            summary="fixture",
            knowledge=knowledge,
        )


def _claim(claim_id: str, claim_type: str, value: str, *, confidence: float = 0.7) -> EvidenceClaim:
    return EvidenceClaim(
        claim_id=claim_id,
        claim_type=claim_type,  # type: ignore[arg-type]
        value=value,
        normalized_value=value,
        source_name="fixture",
        source_url="https://fixture.test/song",
        extraction_method="manual_fixture",
        confidence=confidence,
        snippet=value,
    )


def _knowledge(
    title: str,
    *,
    tempo: str,
    progression: str,
    tab: bool,
    traits: list[str],
    genre: str,
) -> SongKnowledgeProfile:
    slug = title.lower().replace(" ", "_")
    claims = [
        _claim(f"{slug}_tempo", "tempo", tempo, confidence=0.78),
        _claim(f"{slug}_progression", "chord_progression", progression, confidence=0.71),
        _claim(f"{slug}_instrumentation", "instrumentation", ", ".join(traits), confidence=0.69),
        _claim(f"{slug}_genre", "metadata", f"genre: {genre}", confidence=0.64),
    ]
    playable_parts = [
        PlayablePart(
            part_id=f"{slug}_drums",
            kind="drum_tab",
            instrument_family="drums",
            title="Main drum groove",
            source_name="Songsterr",
            source_url="https://songsterr.test/song",
            confidence=0.82,
        )
    ] if tab else []
    tone_profiles = [
        ToneProfile(
            tone_id=f"{slug}_tone",
            instrument="synth",
            description="Wide compressed synth chorus",
            patch_family="wide synth",
            confidence=0.61,
        )
    ]
    return SongKnowledgeProfile(
        profile_id=f"song_fixture_{slug}",
        identity=SongIdentity(title=title, artist="Fixture Band"),
        metadata={"genre": genre},
        evidence_claims=claims,
        playable_parts=playable_parts,
        tone_profiles=tone_profiles,
        source_names=["fixture"],
    )


def test_artist_style_profile_selects_representatives_and_aggregates_traits():
    researcher = FakeResearcher()
    result = BuildArtistStyleProfile(song_researcher=researcher, artist_catalog=FakeCatalog()).execute(
        ArtistStyleProfileRequest(artist_name="Fixture Band", max_songs=2)
    )

    profile = result.profile

    assert researcher.calls == ["Tabbed Hit by Fixture Band", "Deep Cut by Fixture Band"]
    assert profile.artist_name == "Fixture Band"
    assert [song.title for song in profile.representative_songs] == ["Tabbed Hit", "Deep Cut"]
    assert profile.representative_songs[0].tab_available is True
    assert profile.tempo_range_bpm == (96.0, 124.0)
    assert "Am - F - C - G" in profile.common_progressions
    assert "drums" in profile.typical_instruments
    assert any("punchy chorus drums" in trait for trait in profile.drum_traits)
    assert any("wide synth" in trait for trait in profile.production_tone_traits)
    assert profile.confidence_summary["tab_backed_songs"] == "1"


def test_artist_style_profile_feeds_composition_brief():
    style = BuildArtistStyleProfile(song_researcher=FakeResearcher(), artist_catalog=FakeCatalog()).execute(
        "Fixture Band"
    ).profile

    built = BuildCompositionBrief().execute(
        "Compose something similar to Fixture Band with a funk bassline.",
        [],
        artist_style_profiles=[style],
    )

    assert built.brief is not None
    assert built.brief.artist_style_profile_ids == ["artist_fixture_band"]
    assert built.brief.artist_style_profiles[0].artist_name == "Fixture Band"
    assert built.brief.style_guidance["artist_fixture_band"]["progressions"]
