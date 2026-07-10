from __future__ import annotations

from music_assistant.application.answer_music_question import AnswerMusicQuestion
from music_assistant.application.profile_queries import ProfileQueryTools, answer_from_profile
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


def test_query_tools_prefer_songsterr_tab_markers_for_sections_when_available():
    profile = knowledge_profile()
    profile.metadata["songsterr_tab_index"] = {
        "loaded": True,
        "instruments": ["bass", "drums"],
        "tracks": [],
        "sections": ["Intro", "Verse I", "Chorus I", "Break", "Verse II", "Chorus II"],
        "source_urls": ["https://www.songsterr.com/a/wsa/fixture-tab-s1"],
        "warnings_count": 0,
    }
    profile.sections = [
        SongSectionProfile(name="unknown", order=0),
        SongSectionProfile(name="chorus", order=1),
        SongSectionProfile(name="verse 2", order=2),
    ]

    sections = ProfileQueryTools().sections(profile)

    assert sections.answer.startswith("Songsterr tab sections: Intro, Verse I, Chorus I")
    assert "CifraClub/LaCuerda-style section evidence is partial: unknown, chorus, verse 2" in sections.answer
    assert sections.evidence == [
        "songsterr:sections:6",
        "section:unknown:claims=0",
        "section:chorus:claims=0",
        "section:verse 2:claims=0",
    ]


def test_query_tools_answer_specific_instrument_evidence_and_missing_instrument_evidence():
    profile = knowledge_profile()
    profile.evidence_claims = [
        claim("songsterr_tracks", "instrumentation", "Available tab tracks: guitar, bass, drums", source="Songsterr"),
        claim("songsterr_bass", "tab", "Bass tab available from Songsterr", source="Songsterr"),
        claim("songsterr_piano", "instrumentation", "Available tab tracks: piano, vocal", source="Songsterr"),
    ]

    bass = ProfileQueryTools().instrumentation(profile, instrument="bass")
    piano = ProfileQueryTools().instrumentation(profile, instrument="piano")
    sax = ProfileQueryTools().instrumentation(profile, instrument="sax")

    assert "bass" in bass.answer.lower()
    assert "Songsterr" in " ".join(bass.evidence)
    assert "piano" in piano.answer.lower()
    assert "Songsterr" in " ".join(piano.evidence)
    assert "do not have sax-specific evidence" in sax.answer


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


def test_answer_music_question_combines_key_and_chords_from_knowledge():
    answer = AnswerMusicQuestion().execute(
        "What key is it in and what chords are in the chorus?",
        reference_with_knowledge(),
    )

    assert "key is likely A minor" in answer.answer
    assert "probably Bm7 - E9 - Amaj7" in answer.answer
    assert any("key:A minor" in item for item in answer.evidence)
    assert any("chord_progression:chorus" in item for item in answer.evidence)


def test_query_tools_map_chorus_to_refrain_section_aliases():
    profile = knowledge_profile()
    profile.evidence_claims = [claim for claim in profile.evidence_claims if claim.section_name != "chorus"]
    refrain = claim("refrain_chords", "chord_progression", "Ebm7 - Fm7 - Bbm7", section="refrão", confidence=0.7)
    profile.evidence_claims.append(refrain)

    chords = ProfileQueryTools().chords(profile, section_name="chorus")

    assert "Ebm7 - Fm7 - Bbm7" in chords.answer
    assert any("chord_progression:refrão" in item for item in chords.evidence)


def test_query_tools_summarize_repeated_two_bar_chorus_patterns():
    profile = knowledge_profile()
    profile.conflicts = []
    profile.evidence_claims = [
        claim("key", "key", "Db", confidence=0.62),
        claim(
            "chorus_chords",
            "chord_progression",
            "Ebm7(9) | Fm7(9) Bbm7(9) | Ebm7(9) | Fm7(9) Bbm7(9) | Ab7",
            section="chorus",
            confidence=0.64,
            source="CifraClub",
        ),
        claim(
            "chorus_extended",
            "chord_progression",
            (
                "Ebm7(9) | Fm7(9) Bbm7(9) | Ebm7(9) | Fm7(9) Bbm7(9) | "
                "Ebm7(9) | Fm7(9) Bbm7(9) | Ebm7(9) | Fm7(9) Bbm7(9)"
            ),
            section="chorus",
            confidence=0.64,
            source="CifraClub",
        ),
    ]

    answer = AnswerMusicQuestion().execute(
        "What key is it in and what chords are in the chorus?",
        reference_with_knowledge().model_copy(update={"knowledge": profile}),
    )

    assert "key is likely Db" in answer.answer
    assert "repeated 2-bar pattern" in answer.answer
    assert "Ebm7(9) | Fm7(9) Bbm7(9)" in answer.answer
    assert "repeated 2 times" in answer.answer
    assert "Ab7 turnaround" in answer.answer
    assert "extended chorus repeat" in answer.answer
    assert len(answer.answer) < 360
    assert all(len(item) <= 180 for item in answer.evidence)


def test_query_tools_summarize_one_bar_vamps_and_literal_fallbacks():
    profile = knowledge_profile()
    profile.evidence_claims = [
        claim("vamp", "chord_progression", "Am7 | Am7 | Am7 | Am7", section="verse", confidence=0.7),
    ]

    vamp = ProfileQueryTools().chords(profile, section_name="verse")

    assert "1-bar vamp" in vamp.answer
    assert "repeated 4 times" in vamp.answer

    profile.evidence_claims = [
        claim(
            "through_composed",
            "chord_progression",
            "Am7 | D9 | Gmaj7 | Cmaj7 | F#m7b5 | B7 | Em7 | A7 | Dm7 | G7",
            section="verse",
            confidence=0.7,
        ),
    ]

    literal = ProfileQueryTools().chords(profile, section_name="verse")

    assert "starts Am7 | D9 | Gmaj7 | Cmaj7 | F#m7b5 | B7 | Em7 | A7" in literal.answer
    assert "continues beyond that" in literal.answer


def test_query_tools_group_equal_numbered_chorus_instances():
    profile = knowledge_profile()
    profile.evidence_claims = [
        claim("chorus_1", "chord_progression", "Bm | F#m7 | G | D", section="chorus 1", confidence=0.64),
        claim("chorus_2", "chord_progression", "Bm | F#m7 | G | D", section="chorus 2", confidence=0.64),
    ]

    answer = ProfileQueryTools().chords(profile, section_name="chorus")

    assert "chorus 1 and chorus 2 use the same main progression" in answer.answer
    assert "Bm | F#m7 | G | D" in answer.answer
    assert any("chord_progression:chorus 1" in item for item in answer.evidence)
    assert any("chord_progression:chorus 2" in item for item in answer.evidence)


def test_query_tools_describe_extended_numbered_chorus_instances():
    profile = knowledge_profile()
    profile.evidence_claims = [
        claim("chorus_1", "chord_progression", "Bm F#m7 G D | A Bm G | Gm Em | A D G A G", section="chorus 1", confidence=0.64),
        claim(
            "chorus_2",
            "chord_progression",
            "Bm F#m7 G D | A Bm G | Gm Em | A D G A G | Em A D G A G | Em A D G A G",
            section="chorus 2",
            confidence=0.64,
        ),
    ]

    answer = ProfileQueryTools().chords(profile, section_name="chorus")

    assert "chorus 2 starts like chorus 1, then extends" in answer.answer
    assert "Em A D G A G" in answer.answer


def test_query_tools_list_different_numbered_chorus_instances_and_support_exact_instance():
    profile = knowledge_profile()
    profile.evidence_claims = [
        claim("chorus_1", "chord_progression", "Bm | F#m7 | G | D", section="chorus 1", confidence=0.64),
        claim("chorus_2", "chord_progression", "Em | A | D | G", section="chorus 2", confidence=0.64),
    ]

    grouped = ProfileQueryTools().chords(profile, section_name="chorus")
    exact = AnswerMusicQuestion().execute(
        "What chords are in chorus 2?",
        reference_with_knowledge().model_copy(update={"knowledge": profile}),
    )

    assert "Chorus 1:" in grouped.answer
    assert "Chorus 2:" in grouped.answer
    assert "Bm | F#m7 | G | D" in grouped.answer
    assert "Em | A | D | G" in grouped.answer
    assert "chorus 2" in exact.answer.lower()
    assert "Em | A | D | G" in exact.answer
    assert "Bm | F#m7 | G | D" not in exact.answer


# ---- Deep-listening queries (timbre / groove / dynamics claims) ----------------


def _listening_profile() -> SongKnowledgeProfile:
    return SongKnowledgeProfile(
        profile_id="song_listening",
        identity=SongIdentity(title="Listening Test", artist="Fixture"),
        evidence_claims=[
            claim("mix_timbre", "timbre", "mix: warm, mixed, mid-heavy", confidence=0.6, source="LocalAudio"),
            claim("drum_timbre", "timbre", "drums: bright, noisy, high-heavy", confidence=0.6, source="LocalAudio"),
            claim("drum_groove", "groove", "drums: swung, busy, syncopated", confidence=0.7, source="LocalAudio"),
            claim("bass_groove", "groove", "bass: straight, moderate", confidence=0.5, source="LocalAudio"),
            claim("build", "audio_estimate", "drums builds through bars 8-15", confidence=0.5, source="LocalAudio"),
            claim("drop", "audio_estimate", "drums drops at bar 16", confidence=0.5, source="LocalAudio"),
            claim("vox_enter", "instrumentation", "vocals enters in B (bar 5)", confidence=0.5, source="LocalAudio"),
        ],
    )


def test_groove_tool_leads_with_the_strongest_groove_claim():
    from music_assistant.application.profile_queries import answer_from_profile

    answer = answer_from_profile("Does this song swing?", _listening_profile())
    assert answer.answer.startswith("The groove is likely drums: swung, busy, syncopated")
    assert "bass: straight, moderate" in answer.answer
    assert answer.evidence


def test_groove_tool_falls_back_to_instrumentation_descriptions():
    tools = ProfileQueryTools()
    profile = SongKnowledgeProfile(
        profile_id="song_fallback",
        identity=SongIdentity(title="Fallback"),
        evidence_claims=[claim("drums", "instrumentation", "four-on-the-floor funk groove", confidence=0.66)],
    )
    answer = tools.groove(profile)
    assert "four-on-the-floor funk groove" in answer.answer


def test_timbre_tool_prefers_the_mix_claim():
    from music_assistant.application.profile_queries import answer_from_profile

    answer = answer_from_profile("How does it sound?", _listening_profile())
    assert answer.answer.startswith("It likely sounds like this: mix: warm, mixed, mid-heavy")
    assert "not ground truth" in answer.answer


def test_timbre_tool_filters_by_stem():
    from music_assistant.application.profile_queries import answer_from_profile

    answer = answer_from_profile("What is the timbre of the drums?", _listening_profile())
    assert "drums: bright, noisy, high-heavy" in answer.answer
    assert "mix:" not in answer.answer


def test_dynamics_tool_cites_builds_drops_and_arrangement_changes():
    from music_assistant.application.profile_queries import answer_from_profile

    answer = answer_from_profile("Where does it build or drop?", _listening_profile())
    assert "vocals enters in B (bar 5)" in answer.answer
    assert "drums builds through bars 8-15" in answer.answer
    assert "drums drops at bar 16" in answer.answer
    assert len(answer.evidence) == 3


def test_listening_questions_without_evidence_stay_honest():
    from music_assistant.application.profile_queries import answer_from_profile

    empty = SongKnowledgeProfile(profile_id="song_empty", identity=SongIdentity(title="Empty"))
    assert "do not have timbre evidence" in answer_from_profile("How does it sound?", empty).answer
    assert "do not have groove evidence" in answer_from_profile("Does it swing?", empty).answer
    assert "do not have dynamics or arrangement evidence" in answer_from_profile("Where is the drop?", empty).answer


def test_evidence_followup_summarizes_strongest_research_claims():
    profile = knowledge_profile()

    answer = answer_from_profile("What evidence did you find?", profile)

    assert "strongest findings" in answer.answer
    assert answer.evidence
    assert len(answer.evidence) <= 5


def test_answer_music_question_routes_listening_questions_end_to_end():
    """Chat path: AnswerMusicQuestion -> answer_from_profile -> listening tools."""
    reference = ReferenceProfile(
        reference_id="ref_listen",
        source=ReferenceSource(
            reference_id="ref_listen",
            kind="upload",
            label="listen.wav",
            uri="local://listen.wav",
            authorized=True,
        ),
        knowledge=_listening_profile(),
    )
    swing = AnswerMusicQuestion().execute("Does this song swing?", reference)
    assert "swung" in swing.answer
    sound = AnswerMusicQuestion().execute("How does it sound?", reference)
    assert "mix: warm, mixed, mid-heavy" in sound.answer
    drop = AnswerMusicQuestion().execute("Where is the drop?", reference)
    assert "drops at bar 16" in drop.answer
