from __future__ import annotations

from music_assistant.application.answer_music_question import AnswerMusicQuestion
from music_assistant.application.profile_queries import ProfileQueryTools
from music_assistant.domain.audio_profile import (
    EvidenceClaim,
    EvidenceConflict,
    MissingData,
    ReferenceProfile,
    ReferenceSource,
    SongIdentity,
    SongKnowledgeProfile,
    SongSectionProfile,
)


def claim(
    claim_id: str,
    claim_type: str,
    value: str,
    *,
    section: str | None = None,
    confidence: float = 0.7,
    source: str = "Fixture",
) -> EvidenceClaim:
    return EvidenceClaim(
        claim_id=claim_id,
        claim_type=claim_type,  # type: ignore[arg-type]
        value=value,
        normalized_value=value,
        section_name=section,
        source_name=source,
        source_url=f"https://{source.lower()}.test/song",
        extraction_method="site_parser",
        confidence=confidence,
        snippet=f"{claim_type}: {value}",
    )


def knowledge_profile() -> SongKnowledgeProfile:
    tempo = claim("tempo", "tempo", "111 BPM", confidence=0.82)
    key = claim("key", "key", "A minor", confidence=0.68)
    chorus_chords = claim("chorus_chords", "chord_progression", "Bm7 - E9 - Amaj7", section="chorus", confidence=0.73)
    chorus_lyrics = claim("chorus_lyrics", "lyrics", "section lyric locator", section="chorus", confidence=0.7)
    credit = claim("writer", "credit", "Jay Kay", confidence=0.74)
    instrument = claim("drums", "instrumentation", "four-on-the-floor funk groove", section="chorus", confidence=0.66)
    conflict_key = claim("key_conflict", "key", "C major", confidence=0.62, source="Other")
    return SongKnowledgeProfile(
        profile_id="song_space_cowboy",
        identity=SongIdentity(title="Space Cowboy", artist="Jamiroquai", album="Fixture Album", year=1994),
        evidence_claims=[tempo, key, chorus_chords, chorus_lyrics, credit, instrument, conflict_key],
        sections=[
            SongSectionProfile(
                name="chorus",
                order=1,
                chord_claims=[chorus_chords],
                lyric_claims=[chorus_lyrics],
                instrument_claims=[instrument],
            )
        ],
        conflicts=[
            EvidenceConflict(
                conflict_id="key_conflict",
                claim_type="key",
                description="Sources disagree on key.",
                claims=[key, conflict_key],
            )
        ],
        missing_data=[
            MissingData(
                field="section_timestamps",
                reason="No timestamped source.",
                needed_evidence="audio analysis",
            )
        ],
    )


def reference_with_knowledge() -> ReferenceProfile:
    return ReferenceProfile(
        reference_id="ref_space",
        source=ReferenceSource(
            reference_id="ref_space",
            kind="metadata",
            label="Space Cowboy",
            uri="research://Space Cowboy",
            authorized=True,
        ),
        knowledge=knowledge_profile(),
    )


def test_query_tools_answer_key_bpm_metadata_and_credits_from_evidence():
    tools = ProfileQueryTools()
    profile = knowledge_profile()

    tempo_key = tools.key_bpm(profile)
    metadata = tools.metadata_credits(profile)

    assert "111 BPM" in tempo_key.answer
    assert "A minor" in tempo_key.answer
    assert "web evidence" in tempo_key.answer
    assert any("Fixture" in item for item in tempo_key.evidence)
    assert "Space Cowboy" in metadata.answer
    assert "Jay Kay" in metadata.answer


def test_query_tools_answer_section_chords_lyrics_instruments_conflicts_and_missing_data():
    tools = ProfileQueryTools()
    profile = knowledge_profile()

    chords = tools.chords(profile, section_name="chorus")
    lyrics = tools.lyrics_by_section(profile, "chorus")
    instruments = tools.instrumentation(profile)
    conflicts = tools.conflicts(profile)
    missing = tools.missing_data(profile)

    assert "probably Bm7 - E9 - Amaj7" in chords.answer
    assert "section-scoped lyric evidence" in lyrics.answer
    assert "four-on-the-floor" in instruments.answer
    assert "Sources disagree on key" in conflicts.answer
    assert "section_timestamps" in missing.answer


def test_query_tools_do_not_invent_unavailable_solo_notes_or_timestamps():
    tools = ProfileQueryTools()
    profile = knowledge_profile()

    unsupported = tools.unsupported(profile, "What notes are in the solo?")

    assert "not enough evidence" in unsupported.answer.lower()
    assert "solo" in unsupported.answer.lower()
    assert unsupported.evidence == []


def test_answer_music_question_uses_knowledge_tools_before_audio_fallback():
    answer = AnswerMusicQuestion().execute("What chords are in the chorus?", reference_with_knowledge())

    assert answer.reference_id == "ref_space"
    assert "probably Bm7 - E9 - Amaj7" in answer.answer
    assert any("chord_progression" in item for item in answer.evidence)
