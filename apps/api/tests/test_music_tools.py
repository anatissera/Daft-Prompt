from __future__ import annotations

from music_assistant.application.answer_music_question import AnswerMusicQuestion
from music_assistant.application.music_tool_models import (
    ChordsToolInput,
    InstrumentSummaryToolInput,
    InstrumentsToolInput,
    ResearchSongToolInput,
    TabExcerptToolInput,
)
from music_assistant.application.music_tools import MusicTools
from music_assistant.domain.audio_profile import (
    EvidenceClaim,
    ReferenceProfile,
    ReferenceSource,
    SongIdentity,
    SongKnowledgeProfile,
)
from music_assistant.infrastructure.storage.in_memory_reference_store import InMemoryReferenceStore
from music_assistant.infrastructure.storage.in_memory_songsterr_tab_store import InMemorySongsterrTabStore
from music_assistant.infrastructure.web_research.songsterr_tabs import (
    InstrumentTabTrack,
    SongsterrTabBundle,
    TabEvent,
    TabMeasure,
)


class FakeResearcher:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def research(self, query: str) -> ReferenceProfile:
        self.calls.append(query)
        return ReferenceProfile(
            reference_id="ref_space_cowboy",
            source=ReferenceSource(
                reference_id="ref_space_cowboy",
                kind="metadata",
                label=query,
                uri=f"research://{query}",
                authorized=True,
            ),
            summary="Research found source-backed claims.",
            knowledge=SongKnowledgeProfile(
                profile_id="song_space_cowboy",
                identity=SongIdentity(title="Space Cowboy", artist="Jamiroquai"),
                evidence_claims=[
                    EvidenceClaim(
                        claim_id="chorus",
                        claim_type="chord_progression",
                        value="Ebm7 | Fm7 Bbm7 | Ebm7 | Fm7 Bbm7",
                        normalized_value="Ebm7 | Fm7 Bbm7 | Ebm7 | Fm7 Bbm7",
                        section_name="chorus",
                        source_name="Fixture",
                        source_url="https://fixture.test",
                        extraction_method="manual_fixture",
                        confidence=0.8,
                        snippet="chorus chords",
                    )
                ],
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
                tuning=["E1", "A1", "D2", "G2"],
                source_url="https://www.songsterr.com/a/wsa/queen-another-one-bites-the-dust-bass-tab-s371",
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
                measures=[TabMeasure(index=0, marker="Intro", events=[])],
                note_count=8,
                beat_count=4,
            ),
            InstrumentTabTrack(
                part_id=5,
                name="Electric Piano",
                instrument="Electric Piano",
                instrument_family="piano",
                is_piano=True,
                measures=[
                    TabMeasure(
                        index=0,
                        marker="Intro",
                        events=[TabEvent(measure_index=0, beat_index=0, duration="1/4", pitch=60)],
                    )
                ],
                note_count=1,
                beat_count=1,
            ),
        ],
    )


def _tools() -> MusicTools:
    references = InMemoryReferenceStore()
    tab_store = InMemorySongsterrTabStore()
    tab_store.save("ref_queen", _bundle())
    profile = ReferenceProfile(
        reference_id="ref_queen",
        source=ReferenceSource(
            reference_id="ref_queen",
            kind="metadata",
            label="Another One Bites the Dust by Queen",
            uri="research://queen",
            authorized=True,
        ),
        knowledge=SongKnowledgeProfile(
            profile_id="song_queen",
            identity=SongIdentity(title="Another One Bites the Dust", artist="Queen"),
            metadata={
                "songsterr_tab_index": {
                    "loaded": True,
                    "instruments": ["bass", "drums"],
                    "tracks": [
                        {"instrument": "bass", "name": "John Deacon | Fender Precision Bass", "part_id": 4},
                        {"instrument": "drums", "name": "Roger Taylor | Drum Loops", "part_id": 6},
                    ],
                    "sections": ["Intro", "Verse I"],
                    "source_urls": ["https://www.songsterr.com/a/wsa/queen-another-one-bites-the-dust-tab-s371"],
                    "warnings_count": 0,
                }
            },
        ),
    )
    references.save(profile)
    return MusicTools(
        reference_store=references,
        answer_music_question=AnswerMusicQuestion(songsterr_tab_store=tab_store),
        song_researcher=FakeResearcher(),
        songsterr_tab_store=tab_store,
        enable_web_research=True,
    )


def test_research_song_tool_persists_profile_and_returns_compact_output():
    output = _tools().research_song(ResearchSongToolInput(query="Space Cowboy by Jamiroquai"))

    assert output.reference_id == "ref_space_cowboy"
    assert "Research found" in output.summary
    assert output.error is None
    assert output.evidence_count == 1


def test_research_song_explains_how_to_leave_offline_mode_without_calling_provider():
    researcher = FakeResearcher()
    tools = MusicTools(
        reference_store=InMemoryReferenceStore(),
        answer_music_question=AnswerMusicQuestion(),
        song_researcher=researcher,
        enable_web_research=False,
    )

    output = tools.research_song(ResearchSongToolInput(query="Get Lucky by Daft Punk"))

    assert output.error == "web_research_disabled"
    assert "ENABLE_WEB_RESEARCH=true" in output.answer
    assert researcher.calls == []


def test_get_chords_tool_uses_profile_query_and_returns_evidence():
    tools = _tools()
    researched = tools.research_song(ResearchSongToolInput(query="Space Cowboy by Jamiroquai"))

    output = tools.get_chords(ChordsToolInput(reference_id=researched.reference_id, section_name="chorus"))

    assert "chorus" in output.answer.lower()
    assert "Ebm7" in output.answer
    assert output.evidence
    assert output.error is None


def test_get_instruments_tool_reads_lightweight_songsterr_index():
    output = _tools().get_instruments(InstrumentsToolInput(reference_id="ref_queen"))

    assert output.loaded is True
    assert output.instruments == ["bass", "drums"]
    assert output.tracks[0].instrument == "bass"
    assert output.error is None


def test_get_tab_excerpt_returns_small_extract_not_full_track_json():
    output = _tools().get_tab_excerpt(
        TabExcerptToolInput(reference_id="ref_queen", instrument="bass", start_measure=0, measure_count=1)
    )

    assert output.instrument == "bass"
    assert len(output.measures) == 1
    assert output.measures[0].marker == "Intro"
    assert output.measures[0].events[0].beat_index == 0.0
    assert output.measures[0].events[0].string == 3
    assert output.measures[0].events[0].fret == 5
    assert output.track_name
    assert output.tuning
    assert "string=3" not in output.summary
    assert "raw" not in output.model_dump_json()
    assert output.error is None


def test_get_piano_excerpt_includes_source_provided_midi_pitch():
    output = _tools().get_tab_excerpt(
        TabExcerptToolInput(reference_id="ref_queen", instrument="piano", start_measure=0, measure_count=1)
    )

    assert output.instrument == "piano"
    assert output.measures[0].events[0].pitch == 60
    assert output.measures[0].events[0].string is None
    assert output.measures[0].events[0].fret is None


def test_get_instrument_summary_uses_loaded_songsterr_bundle():
    output = _tools().get_instrument_summary(
        InstrumentSummaryToolInput(reference_id="ref_queen", instrument="bass")
    )

    assert "Bass tab loaded from Songsterr" in output.answer
    assert output.evidence == ["songsterr:part:4:measures=2:notes=3"]
    assert output.error is None
