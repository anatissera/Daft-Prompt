"""Phase 4: instrument agent — single-pass composition + bounded repair loop
(LLM mocked — no API key needed)."""

from __future__ import annotations

import pytest

from music_assistant.agents.instrument import (
    MAX_REPAIRS,
    InstrumentOutput,
    InstrumentTurnOutput,
    _chord_map_text,
    _negotiation_etiquette,
    _peer_context,
    _section_map_text,
    compose_part,
    run_instrument_turn,
)
from music_assistant.domain.song_state import ChordSpan, Header, Note, RosterItem, Section
from music_assistant.infrastructure.llm import LLMQuotaExceeded
from music_assistant.skills._tables import DRUM_TOM_HIGH, DRUM_TOM_LOW, DRUM_TOM_MID


class _FakeStructured:
    def __init__(self, outputs):
        self._outputs = list(outputs)
        self.calls = 0

    def invoke(self, _messages):
        self.calls += 1
        # repeat the last output once exhausted, so a "never recovers" test doesn't crash
        out = self._outputs[min(self.calls - 1, len(self._outputs) - 1)]
        return out


class FakeLLM:
    def __init__(self, outputs):
        self.structured = _FakeStructured(outputs)

    def with_structured_output(self, schema):
        assert schema is InstrumentOutput
        return self.structured


HEADER = Header(genre="disco", key="C major", tempo_bpm=120, num_bars=4)
BASS = RosterItem(id="bass", instrument="electric_bass", midi_range=(28, 55), role="groove")
ROSTER = [BASS, RosterItem(id="drums", instrument="kit", role="beat", is_drum=True)]


def _valid_output() -> InstrumentOutput:
    return InstrumentOutput(
        notes=[Note(bar=0, start_beat=0.0, pitch=40, dur=1.0, velocity=100)],
        notes_summary="root notes on the downbeat",
    )


def _out_of_range_output() -> InstrumentOutput:
    return InstrumentOutput(
        notes=[Note(bar=0, start_beat=0.0, pitch=10, dur=1.0, velocity=100)],  # below bass range
        notes_summary="too low",
    )


def _empty_output() -> InstrumentOutput:
    # empty_part is the one validation error the sanitize pass cannot fix
    # mechanically, so it still exercises the LLM repair loop.
    return InstrumentOutput(notes=[], notes_summary="nothing yet")


def test_compose_part_accepts_valid_output_first_try():
    llm = FakeLLM([_valid_output()])
    part = compose_part(HEADER, BASS, ROSTER, {}, llm=llm)
    assert part.instrument_id == "bass"
    assert part.notes[0].pitch == 40
    assert llm.structured.calls == 1  # no repair needed


def test_compose_part_repairs_after_validation_failure():
    llm = FakeLLM([_empty_output(), _valid_output()])
    part = compose_part(HEADER, BASS, ROSTER, {}, llm=llm)
    assert part.notes[0].pitch == 40
    assert llm.structured.calls == 2  # one repair round-trip


def test_compose_part_never_crashes_when_repairs_exhausted():
    llm = FakeLLM([_empty_output()])  # always invalid
    part = compose_part(HEADER, BASS, ROSTER, {}, llm=llm)
    assert part.notes == []  # shipped as-is
    assert llm.structured.calls == 1 + MAX_REPAIRS


def test_compose_part_sanitizes_out_of_range_pitch_without_llm_repair():
    llm = FakeLLM([_out_of_range_output()])
    part = compose_part(HEADER, BASS, ROSTER, {}, llm=llm)
    assert part.notes[0].pitch == 34  # 10 octave-shifted up into (28, 55)
    assert llm.structured.calls == 1  # mechanical fix, no repair turn


def test_sanitize_clamps_velocity_and_trims_bar_overflow():
    out = InstrumentOutput(
        notes=[Note(bar=0, start_beat=3.0, pitch=40, dur=4.0, velocity=250)],
        notes_summary="loud overflow",
    )
    part = compose_part(HEADER, BASS, ROSTER, {}, llm=FakeLLM([out]))
    note = part.notes[0]
    assert note.velocity == 127
    assert note.start_beat + note.dur == pytest.approx(4.0)  # trimmed to bar end


def test_sanitize_drops_notes_outside_the_song():
    out = InstrumentOutput(
        notes=[
            Note(bar=99, start_beat=0.0, pitch=40, dur=1.0),
            Note(bar=0, start_beat=0.0, pitch=40, dur=1.0),
        ],
        notes_summary="one stray",
    )
    part = compose_part(HEADER, BASS, ROSTER, {}, llm=FakeLLM([out]))
    assert [n.bar for n in part.notes] == [0]


def test_compose_part_falls_back_when_structured_output_is_none():
    llm = FakeLLM([None, None])
    part = compose_part(HEADER, BASS, ROSTER, {}, llm=llm)

    assert part.instrument_id == "bass"
    assert part.notes == []
    assert "structured output" in part.notes_summary
    assert llm.structured.calls == 2


def test_compose_part_propagates_quota_errors_instead_of_empty_fallback():
    class QuotaStructured:
        def invoke(self, _messages):
            raise LLMQuotaExceeded(provider="gemini", model="gemini-2.5-flash", detail="quota")

    class QuotaLLM:
        def with_structured_output(self, schema):
            assert schema is InstrumentOutput
            return QuotaStructured()

    with pytest.raises(LLMQuotaExceeded):
        compose_part(HEADER, BASS, ROSTER, {}, llm=QuotaLLM())


def test_compose_part_uses_deterministic_drum_fills_without_llm():
    class NoCallLLM:
        def with_structured_output(self, _schema):
            raise AssertionError("drum parts should not call the LLM")

    drums = RosterItem(id="drums", instrument="kit", role="disco beat", is_drum=True)
    part = compose_part(HEADER, drums, [drums, BASS], {}, llm=NoCallLLM())
    fill_pitches = [note.pitch for note in part.notes if note.bar == 3 and note.start_beat >= 3.0]

    assert DRUM_TOM_HIGH in fill_pitches
    assert DRUM_TOM_MID in fill_pitches
    assert DRUM_TOM_LOW in fill_pitches
    assert "transition_fills" in part.self_notes


def test_run_instrument_turn_falls_back_when_structured_output_is_none():
    class TurnLLM(FakeLLM):
        def with_structured_output(self, schema):
            assert schema is InstrumentTurnOutput
            return self.structured

    llm = TurnLLM([None, None])
    part, resolutions, new_requests = run_instrument_turn(
        HEADER, BASS, ROSTER, {}, [], [], None, llm=llm
    )

    assert part.instrument_id == "bass"
    assert part.notes == []
    assert "structured output" in part.notes_summary
    assert resolutions == []
    assert new_requests == []
    assert llm.structured.calls == 2


def test_peer_context_uses_summary_strings_not_note_lists():
    text = _peer_context(ROSTER, "bass", {"drums": "four-on-the-floor kick"})
    assert "four-on-the-floor kick" in text
    assert "bass" not in text  # self excluded
    assert "[" not in text  # no serialized note list leaking in


def test_chord_map_text_formats_bar_chord_pairs():
    chords = [ChordSpan(bar=0, chord="Dm7"), ChordSpan(bar=1, chord="G7"), ChordSpan(bar=2, chord="Cm9")]
    text = _chord_map_text(chords)
    assert "bar 0: Dm7" in text
    assert "bar 1: G7" in text
    assert "bar 2: Cm9" in text


def test_chord_map_text_with_empty_list_returns_placeholder():
    assert "no chord" in _chord_map_text([]).lower()


def test_section_map_text_includes_energy_and_bar_range():
    sections = [
        Section(name="Intro", start_bar=0, end_bar=4, energy="low"),
        Section(name="Chorus", start_bar=8, end_bar=12, energy="high"),
    ]
    text = _section_map_text(sections)
    assert "Intro" in text
    assert "low" in text
    assert "Chorus" in text
    assert "high" in text
    assert "0" in text and "4" in text


def test_section_map_text_with_empty_list_returns_placeholder():
    assert "no section" in _section_map_text([]).lower()


def test_negotiation_etiquette_includes_scope_hint_when_batch_peers_provided():
    text = _negotiation_etiquette(["drums", "bass"])
    assert "drums" in text
    assert "bass" in text
    assert "only" in text.lower() or "group" in text.lower()


def test_negotiation_etiquette_no_scope_hint_when_no_peers():
    text = _negotiation_etiquette([])
    # should still return the base etiquette text
    assert "request" in text.lower()


def test_song_system_prompt_and_instrument_intro_cover_song_and_instrument_context():
    """Efficiency refactor split the old _system_prompt into a cacheable
    song-level system message + a per-instrument human intro."""
    from music_assistant.agents.instrument import _instrument_intro, _song_system_prompt
    from music_assistant.domain.song_state import Header, RosterItem, ChordSpan, Section
    header = Header(
        genre="funk", key="D minor", tempo_bpm=110, num_bars=8,
        chord_progression=[ChordSpan(bar=i, chord="Dm7") for i in range(8)],
        sections=[Section(name="Verse", start_bar=0, end_bar=8, energy="medium")],
    )
    roster_item = RosterItem(
        id="bass", instrument="Electric Bass", midi_range=(28, 55),
        role="groove", playing_style="Lock to the kick.",
    )
    song = _song_system_prompt(header)
    intro = _instrument_intro(roster_item)
    assert "Dm7" in song
    assert "Verse" in song
    assert "medium" in song
    assert "Electric Bass" in intro
    assert "Lock to the kick." in intro
    assert "Electric Bass" not in song
    assert "Lock to the kick." not in song


def test_guitar_intro_contains_band_like_idiomatic_constraints():
    from music_assistant.agents.instrument import _instrument_intro

    header = Header(genre="grunge rock", key="F minor", tempo_bpm=117, num_bars=8)
    rhythm = RosterItem(
        id="rhythm_guitar",
        instrument="electric_guitar_overdriven",
        midi_range=(40, 84),
        role="rhythm guitar riff",
        playing_style="Aggressive mid-register part.",
    )
    lead = RosterItem(
        id="lead_guitar",
        instrument="electric_guitar_overdriven",
        midi_range=(52, 88),
        role="lead guitar hook",
        playing_style="Answer the riff.",
    )

    rhythm_intro = _instrument_intro(rhythm, header)
    lead_intro = _instrument_intro(lead, header)

    assert "power chord" in rhythm_intro.lower()
    assert "palm-muted" in rhythm_intro.lower()
    assert "repeated riff" in rhythm_intro.lower()
    assert "keyboard-like" in rhythm_intro.lower()
    assert "short motifs" in lead_intro.lower()
    assert "fills between phrases" in lead_intro.lower()
    assert "call-and-response" in lead_intro.lower()


def test_run_instrument_turn_accepts_batch_peer_ids():
    from music_assistant.agents.instrument import InstrumentTurnOutput, run_instrument_turn
    from music_assistant.domain.song_state import Header, Note, RosterItem

    class TurnLLM:
        def with_structured_output(self, schema):
            assert schema is InstrumentTurnOutput
            return self

        def invoke(self, _messages):
            return InstrumentTurnOutput(
                notes=[Note(bar=0, start_beat=0.0, pitch=40, dur=1.0)],
                notes_summary="bass root note",
            )

    header = Header(genre="funk", key="D minor", tempo_bpm=110, num_bars=4)
    bass = RosterItem(id="bass", instrument="Electric Bass", midi_range=(28, 55), role="groove")
    roster = [bass, RosterItem(id="drums", instrument="kit", role="beat", is_drum=True)]

    part, resolutions, new_requests = run_instrument_turn(
        header, bass, roster, {}, ["drums"], [], None, llm=TurnLLM()
    )
    assert part.instrument_id == "bass"
    assert resolutions == []
    assert new_requests == []


def test_instrument_revision_includes_the_user_instruction_in_its_prompt():
    from music_assistant.agents.instrument import InstrumentRevisionOutput
    from music_assistant.domain.song_state import Note, Part

    class RevisionLLM:
        def __init__(self) -> None:
            self.messages = None

        def with_structured_output(self, schema):
            assert schema is InstrumentRevisionOutput
            return self

        def invoke(self, messages):
            self.messages = messages
            return InstrumentRevisionOutput(notes_summary="simplified bass line")

    existing = Part(
        instrument_id="bass",
        notes=[Note(bar=0, start_beat=0.0, pitch=40, dur=1.0)],
        notes_summary="busy bass line",
    )
    llm = RevisionLLM()

    part, resolutions, new_requests = run_instrument_turn(
        HEADER,
        BASS,
        ROSTER,
        {},
        [],
        [],
        existing,
        llm=llm,
        revision_instruction="Make the bass less busy and leave more space for the kick.",
    )

    assert part.notes_summary == "simplified bass line"
    assert resolutions == []
    assert new_requests == []
    prompt = "\n".join(content for _role, content in llm.messages)
    assert "User-requested revision" in prompt
    assert "Make the bass less busy" in prompt


def test_user_requested_drum_revision_uses_the_revision_agent():
    from music_assistant.agents.instrument import InstrumentRevisionOutput
    from music_assistant.domain.song_state import Part

    drums = ROSTER[1]
    existing = Part(
        instrument_id="drums",
        notes=[Note(bar=0, start_beat=0.0, pitch=36, dur=0.25)],
        notes_summary="basic kick pattern",
    )

    class DrumRevisionLLM:
        def with_structured_output(self, schema):
            assert schema is InstrumentRevisionOutput
            return self

        def invoke(self, _messages):
            return InstrumentRevisionOutput(
                edits=[],
                notes_summary="sparser kick pattern with room for the bass",
            )

    part, resolutions, new_requests = run_instrument_turn(
        HEADER,
        drums,
        ROSTER,
        {},
        [],
        [],
        existing,
        llm=DrumRevisionLLM(),
        revision_instruction="Make the drums less busy.",
    )

    assert part.notes_summary == "sparser kick pattern with room for the bass"
    assert resolutions == []
    assert new_requests == []
