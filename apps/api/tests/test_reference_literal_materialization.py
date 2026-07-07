from __future__ import annotations

from music_assistant.application.compose_song import prompt_from_composition_brief
from music_assistant.domain.audio_profile import (
    CompositionBrief,
    InstrumentTimbreProfile,
    MusicalMemoryProfile,
    ReferenceInstrumentProfile,
    ReferenceNotePack,
    ReferenceNoteSeed,
    ReferenceTransferIntent,
    ReferenceTransferItem,
    SongIdentity,
    SongKnowledgeProfile,
)
from music_assistant.application.composition_brief import BuildCompositionBrief
from music_assistant.domain.song_state import Header, RosterItem, SongState
from music_assistant.graph import run_instruments
from music_assistant.music.reference_materialization import literal_parts_from_request


def _bass_profile() -> ReferenceInstrumentProfile:
    notes = [
        ReferenceNoteSeed(bar=0, start_beat=0.0, duration_beats=1.0, pitch=40),
        ReferenceNoteSeed(bar=0, start_beat=2.0, duration_beats=1.0, pitch=43),
    ]
    return ReferenceInstrumentProfile(
        source_reference_id="ref_fixture",
        source_profile_id="song_fixture",
        instrument_family="bass",
        track_name="Fender Precision Bass",
        confidence=0.8,
        timbre=InstrumentTimbreProfile(midi_range=(28, 55), midi_program=33),
        symbolic_seed=notes,
        musical_memory=MusicalMemoryProfile(
            summary="Bass motif: two quarter notes on beats 0 and 2.",
            note_packs=[
                ReferenceNotePack(
                    pack_id="bass_verse_0_0",
                    instrument_family="bass",
                    section_name="Verse",
                    start_bar=0,
                    bar_count=1,
                    notes=notes,
                )
            ],
        ),
    )


def _drums_profile() -> ReferenceInstrumentProfile:
    notes = [
        ReferenceNoteSeed(bar=1, start_beat=0.0, duration_beats=0.5, pitch=42),
        ReferenceNoteSeed(bar=1, start_beat=1.0, duration_beats=0.5, pitch=38),
        ReferenceNoteSeed(bar=2, start_beat=0.0, duration_beats=0.5, pitch=36),
    ]
    return ReferenceInstrumentProfile(
        source_reference_id="ref_fixture",
        source_profile_id="song_fixture",
        instrument_family="drums",
        track_name="Drum Loops",
        confidence=0.8,
        timbre=InstrumentTimbreProfile(midi_program=0, midi_range=(0, 127), is_drum=True),
        symbolic_seed=notes,
        musical_memory=MusicalMemoryProfile(
            summary="Drum motif starts one bar after bass.",
            note_packs=[
                ReferenceNotePack(
                    pack_id="drums_intro_1_0",
                    instrument_family="drums",
                    section_name="Intro",
                    start_bar=1,
                    bar_count=2,
                    notes=notes,
                )
            ],
        ),
    )


def _late_guitar_profile() -> ReferenceInstrumentProfile:
    notes = [
        ReferenceNoteSeed(bar=31, start_beat=0.0, duration_beats=0.25, pitch=64),
        ReferenceNoteSeed(bar=31, start_beat=0.25, duration_beats=0.25, pitch=67),
    ]
    return ReferenceInstrumentProfile(
        source_reference_id="ref_fixture",
        source_profile_id="song_fixture",
        instrument_family="guitar",
        track_name="Lead Guitar",
        confidence=0.8,
        timbre=InstrumentTimbreProfile(midi_range=(40, 84), midi_program=26),
        symbolic_seed=notes,
        musical_memory=MusicalMemoryProfile(
            summary="Late lead guitar section.",
            note_packs=[
                ReferenceNotePack(
                    pack_id="guitar_verse_ii_31_0",
                    instrument_family="guitar",
                    section_name="Verse II",
                    start_bar=31,
                    bar_count=2,
                    notes=notes,
                )
            ],
        ),
    )


def test_literal_brief_uses_note_pack_id_and_summary_instead_of_full_reference_dump():
    knowledge = SongKnowledgeProfile(profile_id="song_fixture", identity=SongIdentity(title="Fixture Song"))
    intent = ReferenceTransferIntent(
        items=[
            ReferenceTransferItem(
                instrument_family="bass",
                reference_id="ref_fixture",
                transfer_mode="literal",
            )
        ]
    )

    result = BuildCompositionBrief().execute(
        "usa el mismo bajo",
        [knowledge],
        transfer_intent=intent,
        instrument_profiles={"ref_fixture": {"bass": _bass_profile()}},
    )

    request = result.brief.instrument_requests["bass"]
    assert request["literal_application"] is True
    assert request["note_pack_id"] == "bass_verse_0_0"
    assert "note_pack" in request
    assert "two quarter notes" in request["musical_memory_summary"]
    assert "reference_profile" not in request


def test_similar_brief_keeps_memory_summary_without_full_note_pack():
    knowledge = SongKnowledgeProfile(profile_id="song_fixture", identity=SongIdentity(title="Fixture Song"))
    intent = ReferenceTransferIntent(
        items=[
            ReferenceTransferItem(
                instrument_family="bass",
                reference_id="ref_fixture",
                transfer_mode="similar",
            )
        ]
    )

    result = BuildCompositionBrief().execute(
        "bajo parecido",
        [knowledge],
        transfer_intent=intent,
        instrument_profiles={"ref_fixture": {"bass": _bass_profile()}},
    )

    request = result.brief.instrument_requests["bass"]
    assert request["literal_application"] is False
    assert "note_pack" not in request
    assert "symbolic_seed" not in request
    assert "musical_memory_summary" in request


def test_literal_parts_materialize_note_pack_and_tile_to_song_length():
    knowledge = SongKnowledgeProfile(profile_id="song_fixture", identity=SongIdentity(title="Fixture Song"))
    brief = BuildCompositionBrief().execute(
        "usa el mismo bajo",
        [knowledge],
        transfer_intent=ReferenceTransferIntent(
            items=[
                ReferenceTransferItem(
                    instrument_family="bass",
                    reference_id="ref_fixture",
                    transfer_mode="literal",
                )
            ]
        ),
        instrument_profiles={"ref_fixture": {"bass": _bass_profile()}},
    ).brief
    assert brief is not None
    request_text = prompt_from_composition_brief(brief)
    assert '"note_pack_id":"bass_verse_0_0"' in request_text
    assert '"note_pack":' not in request_text
    assert '"pitch":' not in request_text
    parts = literal_parts_from_request(
        request_text,
        Header(genre="funk", key="E minor", tempo_bpm=110, num_bars=3),
        [RosterItem(id="bass", instrument="electric_bass", midi_range=(28, 55), role="bass")],
    )

    bass = parts["bass"]
    assert [note.bar for note in bass.notes] == [0, 0, 1, 1, 2, 2]
    assert [note.pitch for note in bass.notes[:2]] == [40, 43]
    assert bass.notes_summary == "literal reference pack bass_verse_0_0, tiled/truncated to 3 bars"


def test_full_song_literal_parts_preserve_timeline_offsets_instead_of_tiling_to_bar_zero():
    knowledge = SongKnowledgeProfile(profile_id="song_fixture", identity=SongIdentity(title="Fixture Song"))
    brief = BuildCompositionBrief().execute(
        "Intentá hacer una canción entera lo más igual posible a esta referencia",
        [knowledge],
        transfer_intent=ReferenceTransferIntent(
            items=[
                ReferenceTransferItem(
                    instrument_family="bass",
                    reference_id="ref_fixture",
                    transfer_mode="literal",
                ),
                ReferenceTransferItem(
                    instrument_family="drums",
                    reference_id="ref_fixture",
                    transfer_mode="literal",
                ),
            ]
        ),
        instrument_profiles={"ref_fixture": {"bass": _bass_profile(), "drums": _drums_profile()}},
    ).brief
    assert brief is not None
    request_text = prompt_from_composition_brief(brief)

    parts = literal_parts_from_request(
        request_text,
        Header(genre="funk", key="E minor", tempo_bpm=110, num_bars=4),
        [
            RosterItem(id="bass", instrument="electric_bass", midi_range=(28, 55), role="bass"),
            RosterItem(id="drums", instrument="drum_kit", midi_range=(0, 127), role="drums", is_drum=True),
        ],
    )

    assert [note.bar for note in parts["bass"].notes] == [0, 0]
    assert [note.bar for note in parts["drums"].notes] == [1, 1, 2]
    assert parts["drums"].notes_summary == "literal reference pack drums_intro_1_0, timeline-aligned to 4 bars"


def test_full_song_literal_pack_outside_window_is_not_moved_to_start():
    knowledge = SongKnowledgeProfile(profile_id="song_fixture", identity=SongIdentity(title="Fixture Song"))
    brief = BuildCompositionBrief().execute(
        "Intentá hacer una canción entera lo más igual posible a esta referencia",
        [knowledge],
        transfer_intent=ReferenceTransferIntent(
            items=[
                ReferenceTransferItem(
                    instrument_family="guitar",
                    reference_id="ref_fixture",
                    transfer_mode="literal",
                    section_name="Verse II",
                )
            ]
        ),
        instrument_profiles={"ref_fixture": {"guitar": _late_guitar_profile()}},
    ).brief
    assert brief is not None
    request_text = prompt_from_composition_brief(brief)

    parts, warnings = literal_parts_from_request(
        request_text,
        Header(genre="funk", key="E minor", tempo_bpm=110, num_bars=16),
        [RosterItem(id="guitar", instrument="electric_guitar", midi_range=(40, 84), role="lead")],
        include_warnings=True,
    )

    assert parts == {}
    assert warnings == ["literal guitar requested but note pack is outside the generated timeline"]


def test_literal_parts_match_noncanonical_bass_roster_by_instrument_alias():
    knowledge = SongKnowledgeProfile(profile_id="song_fixture", identity=SongIdentity(title="Fixture Song"))
    brief = BuildCompositionBrief().execute(
        "usa el mismo bajo",
        [knowledge],
        transfer_intent=ReferenceTransferIntent(
            items=[
                ReferenceTransferItem(
                    instrument_family="bass",
                    reference_id="ref_fixture",
                    transfer_mode="literal",
                )
            ]
        ),
        instrument_profiles={"ref_fixture": {"bass": _bass_profile()}},
    ).brief
    assert brief is not None
    request_text = prompt_from_composition_brief(brief)

    parts = literal_parts_from_request(
        request_text,
        Header(genre="funk", key="E minor", tempo_bpm=110, num_bars=2),
        [
            RosterItem(
                id="low_end",
                instrument="electric_bass",
                midi_range=(28, 55),
                role="rhythmic foundation",
            )
        ],
    )

    assert parts["low_end"].notes_summary.startswith("literal reference pack bass_verse_0_0")


def test_literal_parts_report_warning_when_no_matching_roster_item():
    knowledge = SongKnowledgeProfile(profile_id="song_fixture", identity=SongIdentity(title="Fixture Song"))
    brief = BuildCompositionBrief().execute(
        "usa el mismo bajo",
        [knowledge],
        transfer_intent=ReferenceTransferIntent(
            items=[
                ReferenceTransferItem(
                    instrument_family="bass",
                    reference_id="ref_fixture",
                    transfer_mode="literal",
                )
            ]
        ),
        instrument_profiles={"ref_fixture": {"bass": _bass_profile()}},
    ).brief
    assert brief is not None
    request_text = prompt_from_composition_brief(brief)

    parts, warnings = literal_parts_from_request(
        request_text,
        Header(genre="funk", key="E minor", tempo_bpm=110, num_bars=2),
        [RosterItem(id="lead", instrument="electric_guitar", midi_range=(40, 84), role="lead")],
        include_warnings=True,
    )

    assert parts == {}
    assert warnings == ["literal bass requested but no bass roster item was produced"]


def test_literal_materialization_warning_is_added_to_song_errors():
    knowledge = SongKnowledgeProfile(profile_id="song_fixture", identity=SongIdentity(title="Fixture Song"))
    brief = BuildCompositionBrief().execute(
        "usa el mismo bajo",
        [knowledge],
        transfer_intent=ReferenceTransferIntent(
            items=[
                ReferenceTransferItem(
                    instrument_family="bass",
                    reference_id="ref_fixture",
                    transfer_mode="literal",
                )
            ]
        ),
        instrument_profiles={"ref_fixture": {"bass": _bass_profile()}},
    ).brief
    assert brief is not None
    request_text = prompt_from_composition_brief(brief)
    song = run_instruments(
        SongState(
            request=request_text,
            header=Header(genre="funk", key="E minor", tempo_bpm=110, num_bars=2),
            roster=[RosterItem(id="lead", instrument="electric_guitar", midi_range=(40, 84), role="lead")],
        ),
        llm=None,
    )

    assert "literal bass requested but no bass roster item was produced" in song.errors
