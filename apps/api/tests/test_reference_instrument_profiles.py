from __future__ import annotations

from music_assistant.application.reference_instruments import ReferenceInstrumentProfileBuilder
from music_assistant.domain.audio_profile import (
    EvidenceClaim,
    ReferenceProfile,
    ReferenceSource,
    SongIdentity,
    SongKnowledgeProfile,
)
from music_assistant.infrastructure.storage.in_memory_songsterr_tab_store import InMemorySongsterrTabStore
from music_assistant.infrastructure.web_research.songsterr_tabs import (
    InstrumentTabTrack,
    SongsterrTabBundle,
    TabEvent,
    TabMeasure,
)


def _reference() -> ReferenceProfile:
    return ReferenceProfile(
        reference_id="ref_song",
        source=ReferenceSource(
            reference_id="ref_song",
            kind="metadata",
            label="Fixture Song",
            uri="research://fixture",
            authorized=True,
        ),
        knowledge=SongKnowledgeProfile(
            profile_id="song_fixture",
            identity=SongIdentity(title="Fixture Song", artist="Fixture Artist"),
        ),
    )


def _claim(claim_type: str, value: str) -> EvidenceClaim:
    return EvidenceClaim(
        claim_id=f"claim_{claim_type}",
        claim_type=claim_type,  # type: ignore[arg-type]
        value=value,
        normalized_value=value,
        source_name="fixture",
        source_url="https://fixture.test",
        extraction_method="manual_fixture",
        confidence=0.8,
    )


def test_bass_profile_uses_songsterr_tuning_for_symbolic_seed_and_timbre():
    store = InMemorySongsterrTabStore()
    store.save(
        "ref_song",
        SongsterrTabBundle(
            source_url="https://songsterr.test/bass",
            song_id=1,
            revision_id=2,
            image="img",
            title="Fixture Song",
            tempo_bpm=110,
            tracks=[
                InstrumentTabTrack(
                    part_id=4,
                    name="Fender Precision Bass",
                    instrument="Electric Bass (finger)",
                    instrument_family="bass",
                    tuning=["E1", "A1", "D2", "G2"],
                    is_bass=True,
                    measures=[
                        TabMeasure(
                            index=0,
                            marker="Verse",
                            signature=(4, 4),
                            events=[
                                TabEvent(measure_index=0, beat_index=0, duration="1/4", string=3, fret=5),
                                TabEvent(measure_index=0, beat_index=1, duration="1/8", string=2, fret=3),
                            ],
                        )
                    ],
                    note_count=2,
                    beat_count=2,
                )
            ],
        ),
    )

    profiles = ReferenceInstrumentProfileBuilder(songsterr_tab_store=store).build(_reference())

    bass = profiles["bass"]
    assert bass.instrument_family == "bass"
    assert bass.timbre.midi_program == 33
    assert bass.timbre.midi_range == (28, 55)
    assert bass.pattern.subdivision == "mixed"
    assert bass.symbolic_seed[0].pitch == 43
    assert bass.symbolic_seed[0].duration_beats == 1.0
    assert bass.evidence == ["songsterr:part:4:instrument=bass"]
    assert bass.musical_memory.note_packs[0].pack_id == "bass_verse_0_0"
    assert bass.musical_memory.note_packs[0].section_name == "Verse"
    assert bass.musical_memory.rhythm_patterns[0].accent_beats == [0.0, 1.0]
    assert "Fender Precision Bass" in bass.musical_memory.summary


def test_bass_profile_uses_numeric_songsterr_tuning_for_literal_note_packs():
    store = InMemorySongsterrTabStore()
    store.save(
        "ref_song",
        SongsterrTabBundle(
            source_url="https://songsterr.test/bass",
            song_id=1,
            revision_id=2,
            image="img",
            title="Fixture Song",
            tempo_bpm=110,
            tracks=[
                InstrumentTabTrack(
                    part_id=4,
                    name="John Deacon | Fender Precision Bass",
                    instrument="Electric Bass (finger)",
                    instrument_family="bass",
                    tuning=["43", "38", "33", "28"],
                    is_bass=True,
                    measures=[
                        TabMeasure(
                            index=0,
                            marker="Intro",
                            signature=(4, 4),
                            events=[
                                TabEvent(measure_index=0, beat_index=0.5, duration="1/16", string=3, fret=5),
                                TabEvent(measure_index=0, beat_index=0.75, duration="1/16", string=3, fret=3),
                                TabEvent(measure_index=0, beat_index=1.0, duration="1/4", string=3, fret=0),
                            ],
                        )
                    ],
                    note_count=3,
                    beat_count=3,
                )
            ],
        ),
    )

    bass = ReferenceInstrumentProfileBuilder(songsterr_tab_store=store).build(_reference())["bass"]

    assert [note.pitch for note in bass.symbolic_seed[:3]] == [38, 36, 33]
    assert [note.start_beat for note in bass.symbolic_seed[:3]] == [0.5, 0.75, 1.0]
    assert bass.musical_memory.note_packs[0].pack_id == "bass_intro_0_0"
    assert len(bass.musical_memory.note_packs[0].notes) == 3


def test_bass_note_pack_keeps_compact_sixty_four_note_literal_window():
    store = InMemorySongsterrTabStore()
    measures = []
    for index in range(40):
        measures.append(
            TabMeasure(
                index=index,
                marker="Verse" if index == 0 else None,
                signature=(4, 4),
                events=[
                    TabEvent(measure_index=index, beat_index=0, duration="1/8", string=3, fret=0),
                    TabEvent(measure_index=index, beat_index=0.5, duration="1/8", string=3, fret=2),
                ],
            )
        )
    store.save(
        "ref_song",
        SongsterrTabBundle(
            source_url="https://songsterr.test/bass",
            song_id=1,
            revision_id=2,
            image="img",
            title="Fixture Song",
            tempo_bpm=110,
            tracks=[
                InstrumentTabTrack(
                    part_id=4,
                    name="Long Finger Bass",
                    instrument="Electric Bass (finger)",
                    instrument_family="bass",
                    tuning=["43", "38", "33", "28"],
                    is_bass=True,
                    measures=measures,
                    note_count=80,
                    beat_count=80,
                )
            ],
        ),
    )

    bass = ReferenceInstrumentProfileBuilder(songsterr_tab_store=store).build(_reference())["bass"]

    assert len(bass.symbolic_seed) == 64
    assert len(bass.musical_memory.note_packs[0].notes) == 64


def test_drum_profile_degrades_to_pattern_when_no_drum_pitch_is_available():
    store = InMemorySongsterrTabStore()
    store.save(
        "ref_song",
        SongsterrTabBundle(
            source_url="https://songsterr.test/drums",
            song_id=1,
            revision_id=2,
            image="img",
            title="Fixture Song",
            tracks=[
                InstrumentTabTrack(
                    part_id=6,
                    name="Drum Loops",
                    instrument="Drums",
                    instrument_family="drums",
                    is_drums=True,
                    measures=[
                        TabMeasure(
                            index=0,
                            marker="Intro",
                            signature=(4, 4),
                            events=[
                                TabEvent(measure_index=0, beat_index=0, duration="1/8"),
                                TabEvent(measure_index=0, beat_index=2, duration="1/8"),
                            ],
                        )
                    ],
                    note_count=2,
                    beat_count=2,
                )
            ],
        ),
    )

    drums = ReferenceInstrumentProfileBuilder(songsterr_tab_store=store).build(_reference())["drums"]

    assert drums.timbre.is_drum is True
    assert drums.pattern.density == "medium"
    assert drums.pattern.accent_beats == [0.0, 2.0]
    assert drums.symbolic_seed == []
    assert drums.musical_memory.rhythm_patterns[0].accent_beats == [0.0, 2.0]


def test_drum_profile_uses_songsterr_fret_as_gm_percussion_pitch():
    store = InMemorySongsterrTabStore()
    store.save(
        "ref_song",
        SongsterrTabBundle(
            source_url="https://songsterr.test/drums",
            song_id=1,
            revision_id=2,
            image="img",
            title="Fixture Song",
            tracks=[
                InstrumentTabTrack(
                    part_id=6,
                    name="Roger Taylor | Drum Loops",
                    instrument="Drums",
                    instrument_family="drums",
                    is_drums=True,
                    measures=[
                        TabMeasure(
                            index=1,
                            marker="Intro",
                            signature=(4, 4),
                            events=[
                                TabEvent(
                                    measure_index=1,
                                    beat_index=0,
                                    duration="1/8",
                                    string=-0.5,
                                    fret=42,
                                    raw={"string": -0.5, "fret": 42},
                                ),
                                TabEvent(
                                    measure_index=1,
                                    beat_index=1,
                                    duration="1/8",
                                    string=1.5,
                                    fret=38,
                                    raw={"string": 1.5, "fret": 38},
                                ),
                                TabEvent(
                                    measure_index=1,
                                    beat_index=2,
                                    duration="1/8",
                                    string=3.5,
                                    fret=36,
                                    raw={"string": 3.5, "fret": 36},
                                ),
                            ],
                        )
                    ],
                    note_count=3,
                    beat_count=3,
                )
            ],
        ),
    )

    drums = ReferenceInstrumentProfileBuilder(songsterr_tab_store=store).build(_reference())["drums"]

    assert [note.pitch for note in drums.symbolic_seed] == [42, 38, 36]
    assert [note.pitch for note in drums.musical_memory.note_packs[0].notes] == [42, 38, 36]
    assert "pitch data unavailable" not in " ".join(drums.uncertainty_notes).lower()


def test_piano_profile_keeps_timbre_when_pitch_data_is_missing():
    store = InMemorySongsterrTabStore()
    store.save(
        "ref_song",
        SongsterrTabBundle(
            source_url="https://songsterr.test/keys",
            song_id=1,
            revision_id=2,
            image="img",
            title="Fixture Song",
            tracks=[
                InstrumentTabTrack(
                    part_id=5,
                    name="Rhodes",
                    instrument="Electric Piano",
                    instrument_family="piano",
                    is_piano=True,
                    measures=[
                        TabMeasure(
                            index=0,
                            marker="Chorus",
                            signature=(4, 4),
                            events=[TabEvent(measure_index=0, beat_index=0, duration="1/2")],
                        )
                    ],
                    note_count=1,
                    beat_count=1,
                )
            ],
        ),
    )

    piano = ReferenceInstrumentProfileBuilder(songsterr_tab_store=store).build(_reference())["piano"]

    assert piano.timbre.midi_program == 4
    assert piano.timbre.instrument_name == "Rhodes"
    assert piano.symbolic_seed == []
    assert "pitch data unavailable" in piano.uncertainty_notes[0].lower()
    assert piano.musical_memory.note_packs == []


def test_bass_profile_detects_repeated_two_bar_motif_and_compact_pitch_pattern():
    store = InMemorySongsterrTabStore()
    measures = []
    for index in range(4):
        measures.append(
            TabMeasure(
                index=index,
                marker="Verse" if index == 0 else None,
                signature=(4, 4),
                events=[
                    TabEvent(measure_index=index, beat_index=0, duration="1/4", string=3, fret=2),
                    TabEvent(measure_index=index, beat_index=2, duration="1/4", string=3, fret=4),
                ],
            )
        )
    store.save(
        "ref_song",
        SongsterrTabBundle(
            source_url="https://songsterr.test/bass",
            song_id=1,
            revision_id=2,
            image="img",
            title="Fixture Song",
            tracks=[
                InstrumentTabTrack(
                    part_id=4,
                    name="Finger Bass",
                    instrument="Electric Bass (finger)",
                    instrument_family="bass",
                    tuning=["E1", "A1", "D2", "G2"],
                    is_bass=True,
                    measures=measures,
                    note_count=8,
                    beat_count=8,
                )
            ],
        ),
    )

    bass = ReferenceInstrumentProfileBuilder(songsterr_tab_store=store).build(_reference())["bass"]

    assert bass.musical_memory.motifs[0].bar_count == 1
    assert bass.musical_memory.motifs[0].repetitions == 4
    assert bass.musical_memory.pitch_patterns[0].register == [40, 42]
    assert bass.musical_memory.pitch_patterns[0].intervals == [2]


def test_profile_derives_compact_harmonic_context_from_scraped_evidence():
    store = InMemorySongsterrTabStore()
    store.save(
        "ref_song",
        SongsterrTabBundle(
            source_url="https://songsterr.test/bass",
            song_id=1,
            revision_id=2,
            image="img",
            title="Fixture Song",
            tracks=[
                InstrumentTabTrack(
                    part_id=4,
                    name="Finger Bass",
                    instrument="Electric Bass (finger)",
                    instrument_family="bass",
                    tuning=["E1", "A1", "D2", "G2"],
                    is_bass=True,
                    measures=[
                        TabMeasure(
                            index=0,
                            marker="Verse",
                            signature=(4, 4),
                            events=[TabEvent(measure_index=0, beat_index=0, duration="1/4", string=3, fret=2)],
                        )
                    ],
                    note_count=1,
                    beat_count=1,
                )
            ],
        ),
    )
    reference = _reference().model_copy(
        update={
            "knowledge": SongKnowledgeProfile(
                profile_id="song_fixture",
                identity=SongIdentity(title="Fixture Song", artist="Fixture Artist"),
                evidence_claims=[
                    _claim("key", "E minor"),
                    _claim("chord_progression", "Em | C | D | Am"),
                ],
            )
        }
    )

    bass = ReferenceInstrumentProfileBuilder(songsterr_tab_store=store).build(reference)["bass"]

    assert bass.musical_memory.harmonic_context.key == "E minor"
    assert bass.musical_memory.harmonic_context.chord_progression == ["Em", "C", "D", "Am"]
    assert bass.musical_memory.harmonic_context.roman_progression[:4] == ["i", "VI", "VII", "iv"]
    assert "i-VI-VII-iv" in bass.musical_memory.summary
