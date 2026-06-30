"""Phase 2 step 8: round > 0 instrument turns ship a diff (InstrumentRevisionOutput)
and apply it via apply_edits, instead of re-emitting the full note list."""

from __future__ import annotations

from llm_band.agents.instrument import (
    InstrumentRevisionOutput,
    InstrumentTurnOutput,
    NewRequest,
    RequestResolution,
    run_instrument_turn,
)
from llm_band.domain.song_state import Header, NegotiationRequest, Note, Part, RosterItem
from llm_band.skills.edits import NoteEdit


HEADER = Header(genre="disco", key="C major", tempo_bpm=120, num_bars=4)
LEAD = RosterItem(id="lead", instrument="lead_synth", midi_range=(48, 84), role="hook")
BASS = RosterItem(id="bass", instrument="bass", midi_range=(28, 55), role="groove")
ROSTER = [BASS, LEAD]


def _existing_part() -> Part:
    return Part(
        instrument_id="lead",
        notes=[
            Note(bar=0, start_beat=0.0, pitch=60, dur=1.0, velocity=96),
            Note(bar=1, start_beat=0.0, pitch=62, dur=1.0, velocity=96),
            Note(bar=2, start_beat=0.0, pitch=64, dur=1.0, velocity=96),
        ],
        notes_summary="ascending hook on every downbeat",
    )


class _RevisionLLM:
    def __init__(self, outputs):
        self._outputs = list(outputs)
        self.calls = 0
        self.last_schema = None

    def with_structured_output(self, schema):
        self.last_schema = schema
        return self

    def invoke(self, _messages):
        out = self._outputs[min(self.calls, len(self._outputs) - 1)]
        self.calls += 1
        return out


def test_revision_uses_revision_schema_not_full_schema():
    out = InstrumentRevisionOutput(
        edits=[NoteEdit(op="replace", bar=1, start_beat=0.0,
                        note=Note(bar=1, start_beat=0.0, pitch=65, dur=1.0))],
        notes_summary="raised bar 1 a minor third",
    )
    llm = _RevisionLLM([out])
    part, resolutions, new_requests = run_instrument_turn(
        HEADER, LEAD, ROSTER, {}, [], _existing_part(), llm=llm,
    )
    assert llm.last_schema is InstrumentRevisionOutput
    assert llm.calls == 1
    assert resolutions == [] and new_requests == []
    assert part.instrument_id == "lead"


def test_revision_applies_edits_to_existing_part():
    out = InstrumentRevisionOutput(
        edits=[
            NoteEdit(op="replace", bar=1, start_beat=0.0,
                     note=Note(bar=1, start_beat=0.0, pitch=65, dur=1.0)),
            NoteEdit(op="remove", bar=2, start_beat=0.0),
            NoteEdit(op="add", bar=3, start_beat=0.0,
                     note=Note(bar=3, start_beat=0.0, pitch=67, dur=1.0)),
        ],
        notes_summary="raised, trimmed, extended",
    )
    llm = _RevisionLLM([out])
    part, _, _ = run_instrument_turn(HEADER, LEAD, ROSTER, {}, [], _existing_part(), llm=llm)
    pitches_by_bar = {n.bar: n.pitch for n in part.notes}
    assert pitches_by_bar == {0: 60, 1: 65, 3: 67}  # bar 2 removed


def test_revision_round0_still_uses_full_schema_when_no_existing_part():
    out = InstrumentTurnOutput(
        notes=[Note(bar=0, start_beat=0.0, pitch=60, dur=1.0)],
        notes_summary="fresh compose",
    )
    llm = _RevisionLLM([out])
    part, _, _ = run_instrument_turn(HEADER, LEAD, ROSTER, {}, [], None, llm=llm)
    assert llm.last_schema is InstrumentTurnOutput
    assert part.notes[0].pitch == 60


def test_revision_carries_request_resolutions_and_new_requests():
    out = InstrumentRevisionOutput(
        edits=[],
        notes_summary="no changes needed",
        request_resolutions=[RequestResolution(request_id="req_0_bass_0", accepted=True, resolution="ok")],
        new_requests=[NewRequest(to="bass", bars=[2], request="walk down", rationale="lead is static")],
    )
    pending = [NegotiationRequest(
        id="req_0_bass_0", from_="bass", to="lead", round=1,
        bars=[0], request="brighten", rationale="too dark",
    )]
    llm = _RevisionLLM([out])
    _, resolutions, new_requests = run_instrument_turn(
        HEADER, LEAD, ROSTER, {}, pending, _existing_part(), llm=llm,
    )
    assert len(resolutions) == 1 and resolutions[0].accepted is True
    assert len(new_requests) == 1 and new_requests[0].to == "bass"


def test_revision_falls_back_to_existing_part_when_structured_output_is_none():
    llm = _RevisionLLM([None])
    existing = _existing_part()
    part, resolutions, new_requests = run_instrument_turn(
        HEADER, LEAD, ROSTER, {}, [], existing, llm=llm,
    )
    # an absent diff is interpreted as "no change" rather than wiping the part
    assert [n.pitch for n in part.notes] == [n.pitch for n in existing.notes]
    assert resolutions == [] and new_requests == []


def test_revision_repairs_invalid_edits_via_repair_loop():
    bad = InstrumentRevisionOutput(
        edits=[NoteEdit(op="replace", bar=1, start_beat=0.0,
                        note=Note(bar=1, start_beat=0.0, pitch=200, dur=1.0))],  # out of MIDI
        notes_summary="bad pitch",
    )
    good = InstrumentRevisionOutput(
        edits=[NoteEdit(op="replace", bar=1, start_beat=0.0,
                        note=Note(bar=1, start_beat=0.0, pitch=65, dur=1.0))],
        notes_summary="fixed",
    )
    llm = _RevisionLLM([bad, good])
    part, _, _ = run_instrument_turn(HEADER, LEAD, ROSTER, {}, [], _existing_part(), llm=llm)
    bar1 = next(n for n in part.notes if n.bar == 1)
    assert bar1.pitch == 65
    assert llm.calls == 2


def test_revision_repair_loop_handles_unmatched_edit_then_recovers():
    # First diff targets a note that doesn't exist (bar 5 — out of range too).
    # The repair prompt should mention the failure and the agent gets a second shot.
    bad = InstrumentRevisionOutput(
        edits=[NoteEdit(op="remove", bar=5, start_beat=0.0)],
        notes_summary="phantom remove",
    )
    good = InstrumentRevisionOutput(
        edits=[NoteEdit(op="remove", bar=2, start_beat=0.0)],
        notes_summary="real remove",
    )
    llm = _RevisionLLM([bad, good])
    part, _, _ = run_instrument_turn(HEADER, LEAD, ROSTER, {}, [], _existing_part(), llm=llm)
    bars = sorted(n.bar for n in part.notes)
    assert 2 not in bars
    assert llm.calls == 2


def test_revision_does_not_emit_full_note_list_in_output():
    # Sanity: the LLM contract is the *edit* schema, so even a heavy revision
    # only sends the diff back. Validate by introspecting what the agent returned.
    out = InstrumentRevisionOutput(
        edits=[NoteEdit(op="remove", bar=0, start_beat=0.0)],
        notes_summary="trimmed",
    )
    llm = _RevisionLLM([out])
    part, _, _ = run_instrument_turn(HEADER, LEAD, ROSTER, {}, [], _existing_part(), llm=llm)
    # output had 1 edit and resulting part has 2 notes (3 → 1 removed). The diff
    # is strictly smaller than the materialized result — the whole point.
    assert len(out.edits) < len(part.notes)
