"""Phase 4: graph fan-out — one node per roster entry, parts merged via the
state reducer (LLM mocked — no API key needed)."""

from __future__ import annotations

from music_assistant.agents.instrument import InstrumentOutput
from music_assistant.graph import run_instruments
from music_assistant.music.validators import errors_only, validate_song
from music_assistant.domain.song_state import Header, Note, RosterItem, SongState


class _FakeStructured:
    def invoke(self, messages):
        # the human peer-context message tells us which instrument is asking
        human = next(m for role, m in messages if role == "human")
        return InstrumentOutput(notes=[Note(bar=0, start_beat=0.0, pitch=60, dur=1.0)],
                                 notes_summary=f"part for {human[:5]}")


class FakeLLM:
    def with_structured_output(self, schema):
        return _FakeStructured()


def _song(n_instruments: int) -> SongState:
    header = Header(genre="disco", key="C major", tempo_bpm=120, num_bars=4)
    roster = [
        RosterItem(id=f"inst{i}", instrument="synth", midi_range=(0, 127), role="x")
        for i in range(n_instruments)
    ]
    return SongState(request="x", header=header, roster=roster)


def test_run_instruments_composes_one_part_per_roster_entry():
    song = run_instruments(_song(4), llm=FakeLLM())
    assert set(song.parts.keys()) == {"inst0", "inst1", "inst2", "inst3"}
    for rid, part in song.parts.items():
        assert part.instrument_id == rid
        assert len(part.notes) == 1


def test_run_instruments_with_empty_roster_is_a_noop():
    song = _song(0)
    result = run_instruments(song, llm=FakeLLM())
    assert result.parts == {}


def test_run_instruments_failure_in_one_part_never_crashes_the_run():
    # Empty parts are the one error the deterministic sanitize pass cannot fix,
    # so they exercise the never-crash contract end to end.
    class _BadStructured:
        def invoke(self, _messages):
            return InstrumentOutput(notes=[], notes_summary="broken")

    class BadLLM:
        def with_structured_output(self, schema):
            return _BadStructured()

    song = run_instruments(_song(2), llm=BadLLM())
    assert len(song.parts) == 2  # run still completes for all instruments
    issues = errors_only(validate_song(song))
    assert any(i.code == "empty_part" for i in issues)  # surfaced, not swallowed


def test_run_instruments_sanitizes_invalid_pitches_instead_of_shipping_them():
    class _OobStructured:
        def invoke(self, _messages):
            return InstrumentOutput(
                notes=[Note(bar=0, start_beat=0.0, pitch=200, dur=1.0)],  # invalid MIDI pitch
                notes_summary="broken",
            )

    class OobLLM:
        def with_structured_output(self, schema):
            return _OobStructured()

    song = run_instruments(_song(2), llm=OobLLM())
    issues = errors_only(validate_song(song))
    assert not any(i.code in ("pitch_oob_midi", "pitch_out_of_range") for i in issues)
    for part in song.parts.values():
        assert all(n.pitch is None or 0 <= n.pitch <= 127 for n in part.notes)
