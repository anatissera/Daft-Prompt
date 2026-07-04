from __future__ import annotations

from music_assistant.application.answer_music_question import AnswerMusicQuestion
from music_assistant.application.composition_brief import BuildCompositionBrief
from music_assistant.canned import canned_song
from music_assistant.domain.audio_profile import (
    EvidenceClaim,
    ReferenceProfile,
    ReferenceSource,
    SongIdentity,
    SongKnowledgeProfile,
    SongSectionProfile,
)
from music_assistant.music.validators import errors_only, harmonic_fit, validate_song


def claim(claim_id: str, claim_type: str, value: str, *, section: str | None = None, confidence: float = 0.72):
    return EvidenceClaim(
        claim_id=claim_id,
        claim_type=claim_type,  # type: ignore[arg-type]
        value=value,
        normalized_value=value,
        section_name=section,
        source_name="EvaluationFixture",
        source_url="file://evaluation",
        extraction_method="manual_fixture",
        confidence=confidence,
        snippet=value,
    )


def evaluation_profile() -> SongKnowledgeProfile:
    chorus_chords = claim("chorus_chords", "chord_progression", "Am - F - C - G", section="chorus", confidence=0.76)
    chorus_lyrics = claim("chorus_lyrics", "lyrics", "section lyric locator", section="chorus")
    return SongKnowledgeProfile(
        profile_id="song_eval",
        identity=SongIdentity(title="Evaluation Song", artist="Fixture Artist"),
        evidence_claims=[
            claim("tempo", "tempo", "118 BPM", confidence=0.82),
            claim("key", "key", "A minor", confidence=0.74),
            chorus_chords,
            chorus_lyrics,
            claim("drums", "groove", "four-on-the-floor drum groove", confidence=0.7),
        ],
        sections=[SongSectionProfile(name="chorus", order=1, chord_claims=[chorus_chords], lyric_claims=[chorus_lyrics])],
    )


def test_evaluation_profile_qa_answers_common_questions_without_network_or_llm():
    profile = ReferenceProfile(
        reference_id="ref_eval",
        source=ReferenceSource(reference_id="ref_eval", kind="metadata", label="Evaluation Song", uri="research://eval", authorized=True),
        knowledge=evaluation_profile(),
    )

    tempo = AnswerMusicQuestion().execute("what is the tempo?", profile)
    chords = AnswerMusicQuestion().execute("what chords are in the chorus?", profile)
    lyrics = AnswerMusicQuestion().execute("do you know chorus lyrics?", profile)

    assert "118 BPM" in tempo.answer
    assert "probably Am - F - C - G" in chords.answer
    assert "section-scoped lyric evidence" in lyrics.answer


def test_evaluation_briefs_cover_scratch_single_and_multi_reference():
    base = evaluation_profile()
    harmony = evaluation_profile().model_copy(update={"profile_id": "song_harmony", "identity": SongIdentity(title="Harmony Reference")})

    scratch = BuildCompositionBrief().execute("compose a dark cumbia loop", [])
    single = BuildCompositionBrief().execute("use this song's drums", [base])
    multi = BuildCompositionBrief().execute("use drums from Evaluation Song and harmony from Harmony Reference", [base, harmony])

    assert scratch.brief is not None and scratch.brief.references_used == []
    assert single.brief is not None and single.brief.transfer_policy["song_eval"] == ["rhythmic_guidance"]
    assert multi.brief is not None
    assert multi.brief.transfer_policy["song_eval"] == ["rhythmic_guidance"]
    assert multi.brief.transfer_policy["song_harmony"] == ["harmonic_guidance"]


def test_evaluation_symbolic_composition_remains_valid_and_playable():
    song = canned_song("evaluation sketch")

    assert errors_only(validate_song(song)) == []
    assert song.parts
    assert harmonic_fit(song)["_overall"] >= 0.5
