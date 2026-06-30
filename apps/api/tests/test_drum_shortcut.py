"""Phase 2 efficiency: drum parts skip the LLM and ship `drum_pattern` verbatim."""

from __future__ import annotations

from llm_band.agents.instrument import (
    _resolve_drum_style,
    compose_part,
    run_instrument_turn,
)
from llm_band.domain.song_state import Header, NegotiationRequest, RosterItem
from llm_band.skills._tables import DRUM_KICK, DRUM_SNARE
from llm_band.skills.rhythm import drum_pattern


class _ExplodingLLM:
    """If anything calls into this, the test fails — proves the drum shortcut is
    LLM-free."""

    def with_structured_output(self, schema):  # noqa: D401
        raise AssertionError(f"drum shortcut should not invoke LLM (asked for {schema!r})")


HEADER_HOUSE = Header(genre="house", key="A minor", tempo_bpm=124, num_bars=4)
HEADER_HIPHOP = Header(genre="hip_hop", key="F minor", tempo_bpm=88, num_bars=4)
DRUMS = RosterItem(id="drums", instrument="kit", role="beat", is_drum=True)
MELODIC_BASS = RosterItem(id="bass", instrument="bass", midi_range=(28, 55), role="groove")


def test_drum_shortcut_uses_pattern_from_genre():
    part = compose_part(HEADER_HOUSE, DRUMS, [DRUMS, MELODIC_BASS], {}, llm=_ExplodingLLM())
    expected = drum_pattern("four_on_floor", HEADER_HOUSE.time_signature, HEADER_HOUSE.num_bars)
    assert [(n.pitch, n.bar, n.start_beat, n.dur) for n in part.notes] == \
           [(n.pitch, n.bar, n.start_beat, n.dur) for n in expected]


def test_drum_shortcut_picks_pattern_from_role_override():
    drums_with_override = RosterItem(
        id="drums", instrument="kit", role="drums — boom_bap pocket", is_drum=True,
    )
    part = compose_part(HEADER_HOUSE, drums_with_override, [drums_with_override], {}, llm=_ExplodingLLM())
    # role wins over genre: house would have given four_on_floor, but role asked for boom_bap.
    expected = drum_pattern("boom_bap", HEADER_HOUSE.time_signature, HEADER_HOUSE.num_bars)
    assert [n.pitch for n in part.notes] == [n.pitch for n in expected]


def test_drum_shortcut_resolves_alias():
    style = _resolve_drum_style(HEADER_HIPHOP, DRUMS)
    assert style == "boom_bap"


def test_drum_shortcut_falls_back_when_no_match():
    header = Header(genre="klezmer-trap", key="C major", tempo_bpm=120, num_bars=2)
    style = _resolve_drum_style(header, DRUMS)
    assert style == "rock_basic"


def test_drum_shortcut_summary_describes_pattern():
    part = compose_part(HEADER_HOUSE, DRUMS, [DRUMS], {}, llm=_ExplodingLLM())
    assert "four_on_floor" in part.notes_summary
    assert "4 bars" in part.notes_summary
    assert part.self_notes.startswith("skill:drum_pattern")


def test_drum_shortcut_in_negotiation_turn_declines_pending_and_emits_no_requests():
    pending = [NegotiationRequest(
        id="req_1_bass_0", from_="bass", to="drums",
        round=1, bars=[2], request="leave bar 2 open", rationale="fill space",
    )]
    part, resolutions, new_requests = run_instrument_turn(
        HEADER_HOUSE, DRUMS, [DRUMS, MELODIC_BASS], {}, pending, existing_part=None,
        llm=_ExplodingLLM(),
    )
    assert part.notes  # drum pattern was emitted
    assert len(resolutions) == 1 and resolutions[0].accepted is False
    assert new_requests == []


def test_drum_shortcut_includes_kick_and_snare_for_default_pattern():
    part = compose_part(HEADER_HIPHOP, DRUMS, [DRUMS], {}, llm=_ExplodingLLM())
    pitches = {n.pitch for n in part.notes}
    assert DRUM_KICK in pitches
    assert DRUM_SNARE in pitches
