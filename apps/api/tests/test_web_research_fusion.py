from __future__ import annotations

from music_assistant.infrastructure.web_research.fusion import EvidenceFuser
from music_assistant.ports.song_researcher import ResearchClaim, ResearchPage


def test_evidence_fuser_groups_consistent_tempo_and_key_claims():
    pages = [
        ResearchPage(
            url="https://hooktheory.example/song",
            site="Hooktheory",
            title="Every Breath You Take",
            claims=[
                ResearchClaim(type="tempo", value="117 BPM", confidence=0.8, snippet="Tempo 117 BPM"),
                ResearchClaim(type="key", value="A major", confidence=0.75, snippet="Key A major"),
            ],
        ),
        ResearchPage(
            url="https://tabs.example/song",
            site="Tabs",
            title="Every Breath You Take chords",
            claims=[
                ResearchClaim(type="tempo", value="118 bpm", confidence=0.65, snippet="118 bpm"),
                ResearchClaim(type="key", value="A", confidence=0.65, snippet="Key: A"),
            ],
        ),
    ]

    profile = EvidenceFuser().fuse("Every Breath You Take", pages)

    assert profile.source.kind == "metadata"
    assert profile.audio is not None
    assert profile.audio.tempo_bpm == 117.5
    assert profile.audio.tempo_confidence > 0.7
    assert profile.audio.key == "A major"
    assert profile.research_evidence
    assert "2 sources" in profile.summary


def test_evidence_fuser_lowers_confidence_for_conflicting_key_claims():
    pages = [
        ResearchPage(
            url="https://one.example/song",
            site="One",
            title="Song",
            claims=[ResearchClaim(type="key", value="A major", confidence=0.8, snippet="A major")],
        ),
        ResearchPage(
            url="https://two.example/song",
            site="Two",
            title="Song",
            claims=[ResearchClaim(type="key", value="F# minor", confidence=0.8, snippet="F#m")],
        ),
    ]

    profile = EvidenceFuser().fuse("Every Breath You Take", pages)

    assert profile.audio is not None
    assert profile.audio.key in {"A major", "F# minor"}
    assert profile.audio.key_confidence < 0.7
    assert any(note.code == "conflicting_key_claims" for note in profile.audio.analysis_notes)
