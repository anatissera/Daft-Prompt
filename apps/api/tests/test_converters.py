"""Phase 2: deterministic converters (MIDI / MusicXML / PDF)."""

from __future__ import annotations

import pretty_midi

from llm_band.music.render_midi import render_midi, song_to_pretty_midi
from llm_band.music.render_sheet import render_musicxml, render_pdf
from llm_band.domain.song_state import Header, Note, Part, RosterItem, SongState


def test_midi_round_trips(sample_song, tmp_path):
    path = render_midi(sample_song, str(tmp_path / "s.mid"))
    pm = pretty_midi.PrettyMIDI(path)
    assert len(pm.instruments) == len(sample_song.parts)
    assert sum(len(i.notes) for i in pm.instruments) > 0


def test_drums_route_to_percussion_channel(sample_song):
    pm = song_to_pretty_midi(sample_song)
    drums = [i for i in pm.instruments if i.is_drum]
    assert len(drums) == 1  # pretty_midi maps is_drum to GM channel 10


def test_musicxml_is_valid(sample_song, tmp_path):
    path = render_musicxml(sample_song, str(tmp_path / "s.musicxml"))
    text = open(path, encoding="utf-8").read()
    assert "score-partwise" in text


def test_quantization_handles_ragged_durations(tmp_path):
    third = 1.0 / 3.0  # 0.333… — not representable on a binary grid
    roster = [RosterItem(id="lead", instrument="lead", midi_range=(0, 127))]
    notes = [Note(bar=0, start_beat=i * third, pitch=60 + i, dur=third) for i in range(3)]
    song = SongState(
        request="triplets",
        header=Header(genre="t", key="C major", tempo_bpm=100, num_bars=1),
        roster=roster,
        parts={"lead": Part(instrument_id="lead", notes=notes)},
    )
    # must not raise on un-griddable durations
    path = render_musicxml(song, str(tmp_path / "trip.musicxml"))
    assert "score-partwise" in open(path, encoding="utf-8").read()


def test_render_pdf_degrades_gracefully(sample_song, tmp_path):
    # no MuseScore/LilyPond installed in this environment -> returns None, no raise
    result = render_pdf(sample_song, str(tmp_path / "s.pdf"))
    assert result is None or result.endswith(".pdf")
