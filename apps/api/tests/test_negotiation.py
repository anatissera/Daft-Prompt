"""Phase 5: batch sequencer graph — batches execute in order, intra-batch
mini-negotiation scoped to batch members, peer summaries propagate forward.
All LLMs mocked — no API key needed."""

from __future__ import annotations

import pytest

from music_assistant.agents.arbiter import ArbiterOutput, ArbiterResolution
from music_assistant.agents.instrument import InstrumentTurnOutput, NewRequest, RequestResolution

from music_assistant.agents.instrument import InstrumentRevisionOutput
from music_assistant.agents.director import DirectorOutput, ArrangementInstrument, ArrangementSection, CompositionGroup as DCompositionGroup
from music_assistant.graph import run_negotiation
from music_assistant.domain.song_state import (
    ChordSpan, CompositionGroup, Header, Note, RosterItem, SongState,
)

HEADER = Header(genre="funk", key="D minor", tempo_bpm=110, num_bars=4)
DRUMS = RosterItem(id="drums", instrument="kit", role="beat", is_drum=True)
BASS = RosterItem(id="bass", instrument="electric_bass", midi_range=(28, 55), role="groove")
EPIANO = RosterItem(id="epiano", instrument="rhodes", midi_range=(48, 72), role="harmony")

GROUPS = [
    CompositionGroup(name="rhythm", instrument_ids=["drums", "bass"], max_negotiation_rounds=2),
    CompositionGroup(name="harmony", instrument_ids=["epiano"], max_negotiation_rounds=0),
]


def _make_director_output(roster, groups):
    return DirectorOutput(
        genre="funk", key="D minor", tempo_bpm=110,
        time_sig_numerator=4, time_sig_denominator=4, num_bars=4,
        sections=[ArrangementSection(name="Verse", start_bar=0, end_bar=4, energy="medium")],
        chord_progression=[ChordSpan(bar=i, chord="Dm7") for i in range(4)],
        instruments=[
            ArrangementInstrument(
                id=r.id, instrument=r.instrument, midi_program=0,
                midi_low=r.midi_range[0], midi_high=r.midi_range[1],
                role=r.role, playing_style="play your role", is_drum=r.is_drum,
            )
            for r in roster
        ],
        composition_groups=[
            DCompositionGroup(name=g.name, instrument_ids=g.instrument_ids, max_negotiation_rounds=g.max_negotiation_rounds)
            for g in groups
        ],
    )


class DirectorLLM:
    """Returns a pre-built DirectorOutput."""

    def __init__(self, director_output):
        self._output = director_output

    def with_structured_output(self, schema):
        from music_assistant.agents.director import DirectorOutput as DO
        if schema is DO:
            return self
        raise AssertionError(f"DirectorLLM called with unexpected schema: {schema}")

    def invoke(self, _messages):
        return self._output


def _silent_note(pitch=40) -> Note:
    return Note(bar=0, start_beat=0.0, pitch=pitch, dur=1.0)


def _turn(pitch=40, summary="ok", requests=None, resolutions=None) -> InstrumentTurnOutput:
    return InstrumentTurnOutput(
        notes=[_silent_note(pitch)],
        notes_summary=summary,
        new_requests=requests or [],
        request_resolutions=resolutions or [],
    )


def test_batches_execute_in_order_and_peer_summaries_propagate():
    """The epiano (batch 2) must see drums and bass summaries in peer context.

    Drums never call the LLM (deterministic drum_pattern) and both scripted
    turns are valid + in range (the sanitize pass would silently fix anything
    else without spending a repair turn), so the call order is exactly:
    call 1 = bass (batch 1), call 2 = epiano (batch 2).
    """
    seen_peer_summaries = {}

    class SpyLLM:
        calls = 0

        def with_structured_output(self, schema):
            from music_assistant.agents.director import DirectorOutput as DO
            if schema is DO:
                return DirectorLLM(_make_director_output([DRUMS, BASS, EPIANO], GROUPS))
            assert schema is InstrumentTurnOutput
            return self

        def invoke(self, messages):
            self.calls += 1
            human_text = "\n".join(m for role, m in messages if role == "human")
            if self.calls == 1:
                return _turn(40, "bass groove part_1")  # in bass range (28, 55)
            seen_peer_summaries["epiano_saw"] = human_text
            return _turn(60, "epiano comp")  # in epiano range (48, 72)

    llm = SpyLLM()
    result = run_negotiation("funk", llm=llm)

    assert llm.calls == 2  # drums composed without the LLM
    # epiano should see the bass summary and the drums' deterministic pattern
    assert "epiano_saw" in seen_peer_summaries
    assert "part_1" in seen_peer_summaries["epiano_saw"]
    assert "pattern" in seen_peer_summaries["epiano_saw"]
    assert "epiano" in result.parts
    assert "drums" in result.parts
    assert "bass" in result.parts


# Post-efficiency negotiation fixtures: drums never call the LLM (deterministic
# drum_pattern, requests to them auto-declined), and round > 0 turns request
# InstrumentRevisionOutput (a diff) instead of InstrumentTurnOutput. Negotiation
# is therefore exercised between the two non-drum peers (bass ↔ epiano) with a
# dual-schema scripted fake that serves whichever schema the agent asks for.

MELODIC_GROUPS = [
    CompositionGroup(name="beat", instrument_ids=["drums"], max_negotiation_rounds=0),
    CompositionGroup(name="melodic", instrument_ids=["bass", "epiano"], max_negotiation_rounds=2),
]


def _revision(summary="revised", resolutions=None, requests=None) -> InstrumentRevisionOutput:
    return InstrumentRevisionOutput(
        edits=[],  # keep the existing part; negotiation bookkeeping is what's under test
        notes_summary=summary,
        request_resolutions=resolutions or [],
        new_requests=requests or [],
    )


class _Queue:
    def __init__(self, script):
        self.script = list(script)
        self.calls = 0

    def invoke(self, _messages):
        out = self.script[min(self.calls, len(self.script) - 1)] if self.script else None
        self.calls += 1
        return out


class DualSchemaLLM:
    """Scripted fake serving DirectorOutput, InstrumentTurnOutput (round 0),
    InstrumentRevisionOutput (round > 0), and ArbiterOutput on demand."""

    def __init__(self, director_output, turn_script, revision_script=None, arbiter_script=None):
        self._director = DirectorLLM(director_output)
        self.turns = _Queue(turn_script)
        self.revisions = _Queue(revision_script or [])
        self.arbiter = _Queue(arbiter_script or [ArbiterOutput(resolutions=[])])

    def with_structured_output(self, schema):
        from music_assistant.agents.director import DirectorOutput as DO
        if schema is DO:
            return self._director
        if schema is ArbiterOutput:
            return self.arbiter
        if schema is InstrumentRevisionOutput:
            return self.revisions
        assert schema is InstrumentTurnOutput
        return self.turns


def test_intra_batch_negotiation_resolves_within_group():
    director_out = _make_director_output([DRUMS, BASS, EPIANO], MELODIC_GROUPS)
    llm = DualSchemaLLM(
        director_out,
        turn_script=[
            _turn(40, "bass round0", requests=[NewRequest(to="epiano", bars=[0], request="leave beat 1", rationale="fill")]),
            _turn(60, "epiano round0"),
        ],
        revision_script=[
            _revision("epiano round1", resolutions=[RequestResolution(request_id="req_0_bass_0", accepted=True, resolution="done")]),
        ],
    )
    result = run_negotiation("funk", llm=llm)

    req = next((r for r in result.negotiation_requests if r.id == "req_0_bass_0"), None)
    assert req is not None
    assert req.status == "resolved"
    assert llm.revisions.calls == 1  # only epiano was re-run, as a diff turn


def test_cross_batch_requests_are_not_dispatched_within_batch():
    """A request from the melodic batch to the drums (an earlier, closed batch)
    must not trigger extra melodic negotiation rounds — it survives as pending
    and is settled by the arbiter at the end."""
    director_out = _make_director_output(
        [DRUMS, BASS, EPIANO],
        [
            CompositionGroup(name="beat", instrument_ids=["drums"], max_negotiation_rounds=0),
            CompositionGroup(name="melodic", instrument_ids=["bass", "epiano"], max_negotiation_rounds=2),
        ],
    )
    llm = DualSchemaLLM(
        director_out,
        turn_script=[
            _turn(40, "bass round0", requests=[NewRequest(to="drums", bars=[0], request="less hats", rationale="space")]),
            _turn(60, "epiano round0"),
        ],
        arbiter_script=[
            ArbiterOutput(resolutions=[ArbiterResolution(request_id="req_0_bass_0", accepted=False, resolution="arbiter declined")]),
        ],
    )
    result = run_negotiation("funk", llm=llm)

    assert llm.turns.calls == 2  # bass + epiano round 0 only
    assert llm.revisions.calls == 0  # no negotiation round was dispatched for it
    req = next((r for r in result.negotiation_requests if r.id == "req_0_bass_0"), None)
    assert req is not None
    assert req.status == "declined"
    assert result.converged is True


def test_zero_new_requests_exits_batch_early():
    director_out = _make_director_output([DRUMS, BASS, EPIANO], MELODIC_GROUPS)
    llm = DualSchemaLLM(
        director_out,
        turn_script=[
            _turn(40, "bass no ask"),
            _turn(60, "epiano no ask"),
        ],
    )
    result = run_negotiation("funk", llm=llm)

    assert llm.turns.calls == 2  # only round 0 — no negotiation
    assert llm.revisions.calls == 0
    assert result.converged is True


def test_per_instrument_llm_failure_is_isolated_so_compose_finishes():
    """When one instrument's LLM call fails, the others' parts are preserved and the
    failing instrument ships an empty-part placeholder so the batch run still finishes.
    Drums compose deterministically, so their part must survive a bass LLM outage."""
    from music_assistant.infrastructure.llm import LLMQuotaExceeded

    director_out = _make_director_output([DRUMS, BASS], [
        CompositionGroup(name="rhythm", instrument_ids=["drums", "bass"], max_negotiation_rounds=0),
    ])

    class _QuotaQueue:
        def invoke(self, _messages):
            raise LLMQuotaExceeded(provider="gemini", model="gemini-2.5-flash", detail="quota")

    class FlakyInstrumentLLM:
        def with_structured_output(self, schema):
            from music_assistant.agents.director import DirectorOutput as DO
            if schema is DO:
                return DirectorLLM(director_out)
            if schema is ArbiterOutput:
                return _Queue([ArbiterOutput(resolutions=[])])
            assert schema is InstrumentTurnOutput  # only the bass reaches the LLM
            return _QuotaQueue()

    result = run_negotiation("funk", llm=FlakyInstrumentLLM())

    assert "pattern" in result.parts["drums"].notes_summary  # deterministic drum part survived
    assert result.parts["bass"].notes_summary.startswith("(failed to compose")
    assert result.converged is True


def test_arbiter_resolves_surviving_requests_after_all_batches():
    director_out = _make_director_output([DRUMS, BASS, EPIANO], [
        CompositionGroup(name="beat", instrument_ids=["drums"], max_negotiation_rounds=0),
        CompositionGroup(name="melodic", instrument_ids=["bass", "epiano"], max_negotiation_rounds=1),
    ])
    # bass raises a request that epiano never resolves → goes to arbiter
    llm = DualSchemaLLM(
        director_out,
        turn_script=[
            _turn(40, "bass round0", requests=[NewRequest(to="epiano", bars=[0], request="leave space", rationale="fill")]),
            _turn(60, "epiano round0"),
        ],
        revision_script=[
            _revision("epiano round1"),  # no resolutions
        ],
        arbiter_script=[
            ArbiterOutput(resolutions=[ArbiterResolution(request_id="req_0_bass_0", accepted=False, resolution="arbiter declined")]),
        ],
    )
    result = run_negotiation("funk", llm=llm)

    assert llm.revisions.calls == 1  # epiano got exactly one negotiation round
    req = next((r for r in result.negotiation_requests if r.id == "req_0_bass_0"), None)
    assert req is not None
    assert req.status == "declined"
    assert result.converged is True
