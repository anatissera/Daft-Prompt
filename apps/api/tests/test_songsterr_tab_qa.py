from __future__ import annotations

from music_assistant.application.answer_music_question import AnswerMusicQuestion
from music_assistant.domain.audio_profile import ReferenceProfile, ReferenceSource, SongIdentity, SongKnowledgeProfile
from music_assistant.infrastructure.web_research.songsterr_tabs import (
    InMemorySongsterrTabStore,
    InstrumentTabTrack,
    SongsterrTabBundle,
    TabEvent,
    TabMeasure,
)


def _profile() -> ReferenceProfile:
    return ReferenceProfile(
        reference_id="ref_queen_another_one_bites_the_dust",
        source=ReferenceSource(
            reference_id="ref_queen_another_one_bites_the_dust",
            kind="metadata",
            label="Another One Bites the Dust by Queen",
            uri="research://queen",
            authorized=True,
        ),
        knowledge=SongKnowledgeProfile(
            profile_id="song_queen_another_one_bites_the_dust",
            identity=SongIdentity(title="Another One Bites the Dust", artist="Queen"),
        ),
    )


def _bundle() -> SongsterrTabBundle:
    return SongsterrTabBundle(
        source_url="https://www.songsterr.com/a/wsa/queen-another-one-bites-the-dust-tab-s371",
        song_id=371,
        revision_id=7564044,
        image="v0-test-image",
        title="Another One Bites the Dust",
        artist="Queen",
        tempo_bpm=110,
        tracks=[
            InstrumentTabTrack(
                part_id=4,
                name="John Deacon | Fender Precision Bass",
                instrument="Electric Bass",
                instrument_family="bass",
                is_bass=True,
                measures=[
                    TabMeasure(
                        index=0,
                        marker="Intro",
                        events=[
                            TabEvent(measure_index=0, beat_index=0, duration="1/4", string=3, fret=5),
                            TabEvent(measure_index=0, beat_index=1, duration="1/4", string=3, fret=3),
                        ],
                    ),
                    TabMeasure(
                        index=1,
                        marker="Verse I",
                        events=[TabEvent(measure_index=1, beat_index=0, duration="1/8", string=3, fret=0)],
                    ),
                ],
                note_count=3,
                beat_count=3,
            ),
            InstrumentTabTrack(
                part_id=6,
                name="Roger Taylor | Drum Loops",
                instrument="Drums",
                instrument_family="drums",
                is_drums=True,
                measures=[
                    TabMeasure(index=0, marker="Intro", events=[]),
                    TabMeasure(index=1, marker="Verse I", events=[]),
                ],
                note_count=8,
                beat_count=4,
            ),
        ],
    )


def _answerer() -> AnswerMusicQuestion:
    store = InMemorySongsterrTabStore()
    store.save("ref_queen_another_one_bites_the_dust", _bundle())
    return AnswerMusicQuestion(songsterr_tab_store=store)


def test_answer_music_question_summarizes_bass_from_songsterr_bundle_without_dumping_tab():
    answer = _answerer().execute("What does the bass do?", _profile())

    assert "Bass tab loaded from Songsterr" in answer.answer
    assert "2 measures" in answer.answer
    assert "3 note events" in answer.answer
    assert "Intro, Verse I" in answer.answer
    assert "string=3" not in answer.answer
    assert answer.evidence == ["songsterr:part:4:measures=2:notes=3"]


def test_answer_music_question_reports_songsterr_tab_sections():
    answer = _answerer().execute("What sections are in the tab?", _profile())

    assert answer.answer == "Songsterr tab sections: Intro, Verse I."
    assert answer.evidence == ["songsterr:sections:2"]


def test_answer_music_question_uses_uncertainty_for_missing_tab_instrument():
    answer = _answerer().execute("What does the sax do?", _profile())

    assert answer.answer == "I do not have sax-specific Songsterr tab data for this song yet."
    assert answer.evidence == []
