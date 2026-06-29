from __future__ import annotations

from music_assistant.application.research_reference import ResearchReference
from music_assistant.domain.reference_profile import (
    MusicProfile,
    ReferenceProfile,
    ReferenceSource,
    ResearchEvidence,
)


class FakeSongResearcher:
    def research(self, query: str) -> ReferenceProfile:
        return ReferenceProfile(
            reference_id="ref_every_breath_you_take",
            source=ReferenceSource(
                reference_id="ref_every_breath_you_take",
                kind="metadata",
                label=query,
                uri=f"research://{query}",
                authorized=True,
            ),
            music=MusicProfile(
                duration_seconds=0.0,
                tempo_bpm=117.0,
                tempo_confidence=0.74,
                key="A major",
                key_confidence=0.68,
                confidence=0.7,
                overall_confidence=0.7,
            ),
            summary="Research found a likely A major song around 117 BPM.",
            research_evidence=[
                ResearchEvidence(
                    url="https://example.test/every-breath-you-take",
                    site="Example",
                    claim_type="tempo",
                    value="117 BPM",
                    confidence=0.74,
                    snippet="Tempo: 117 BPM",
                )
            ],
        )


def test_research_reference_builds_profile_from_song_researcher():
    profile = ResearchReference(FakeSongResearcher()).execute("Every Breath You Take")

    assert profile.reference_id == "ref_every_breath_you_take"
    assert profile.source.kind == "metadata"
    assert profile.music is not None
    assert profile.music.tempo_bpm == 117.0
    assert profile.music.key == "A major"
    assert profile.research_evidence[0].claim_type == "tempo"
