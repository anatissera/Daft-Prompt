"""Edit a previously generated song from a natural-language instruction.

The user iterates on the last output ("subí el pitch dos semitonos",
"reemplazá el piano por un rhodes", "sacá los vientos", "más lento").
One small LLM call translates the instruction into a structured `EditPlan`
over a CLOSED vocabulary of operations; the plan is applied
deterministically to the persisted `SongState` and re-rendered. The LLM
never touches notes directly — same philosophy as the patch vocabulary:
the model decides, deterministic code executes.
"""

from __future__ import annotations

import logging
from typing import Literal, Optional

from pydantic import BaseModel, Field

from music_assistant.domain.patch import (
    PATCH_SPEC,
    UnknownPatchError,
    family_pitch_range,
    reconcile_patch,
    resolve_patch,
)
from music_assistant.domain.song_state import SongState
from music_assistant.infrastructure.llm import make_llm

log = logging.getLogger(__name__)


class EditOp(BaseModel):
    op: Literal[
        "transpose",
        "replace_instrument",
        "remove_instrument",
        "add_instrument",
        "set_tempo",
        "scale_velocity",
    ]
    # Part id or instrument name to act on; "" or "all" = every melodic part.
    target: str = ""
    semitones: int = Field(default=0, ge=-24, le=24)
    new_patch: Optional[str] = None
    new_name: Optional[str] = None
    # add_instrument only: the musical role of the new part.
    role: str = ""
    tempo_bpm: float = Field(default=0, ge=0, lt=300)
    velocity_factor: float = Field(default=1.0, gt=0, le=4.0)


class EditPlan(BaseModel):
    operations: list[EditOp] = Field(default_factory=list)
    # One sentence describing what was done, in the user's language.
    summary: str = ""


_EDIT_SYSTEM = f"""You translate a music-edit instruction into an EditPlan —
a list of operations over the PREVIOUS song. Available operations:

- transpose: shift pitches by `semitones` (target part or all; drums are
  never transposed). "subí el pitch"/"raise the pitch" with no amount = +2.
  An octave = 12.
- replace_instrument: change `target`'s sound to `new_patch` (MUST be one
  of the closed vocabulary names below). Optionally set `new_name` for the
  display name. Notes are kept.
- remove_instrument: drop `target` entirely.
- add_instrument: add a NEW part. Set `new_patch` (from the vocabulary
  below), `new_name` (display name) and `role` (what it plays: "second
  piano comping in a higher register", "counter-melody violin"…). Its
  notes are composed afterwards by the fill pipeline.
- set_tempo: change the song tempo to `tempo_bpm`. "más rápido"/"faster"
  with no number = current +15%%; "más lento"/"slower" = current -15%%
  (compute the number yourself from the current tempo).
- scale_velocity: multiply `target`'s velocities by `velocity_factor`
  ("más fuerte" ≈ 1.3, "más suave" ≈ 0.7).

`target` must be one of the song's part ids (preferred) or its instrument
name. Emit the MINIMAL set of operations that fulfils the instruction —
nothing speculative. Set `summary` to one short sentence in the user's
language describing the change.

Valid patch names for replace_instrument:
{", ".join(sorted(PATCH_SPEC.keys()))}
"""


def plan_edit(instruction: str, song: SongState) -> EditPlan | None:
    """One small LLM call → EditPlan. Returns None when planning failed."""
    roster = [
        {"id": r.id, "instrument": r.instrument, "patch": r.patch, "is_drum": r.is_drum}
        for r in song.roster
    ]
    prompt = (
        f"INSTRUCTION:\n{instruction}\n\n"
        f"CURRENT SONG: genre={song.header.genre!r}, tempo={song.header.tempo_bpm} BPM, "
        f"key={song.header.key!r}\nROSTER: {roster}\n\n"
        "Return ONLY the structured EditPlan via the tool — no prose."
    )
    try:
        llm = make_llm(role="director").with_structured_output(EditPlan)
        for _ in range(2):  # parse-None flake retry, same as elsewhere
            result = llm.invoke([("system", _EDIT_SYSTEM), ("human", prompt)])
            if isinstance(result, EditPlan) and result.operations:
                return result
    except Exception as exc:
        log.warning("edit plan failed: %s: %s", type(exc).__name__, exc)
    return None


def apply_additions(song: SongState, plan: EditPlan) -> tuple[SongState, list[str]]:
    """Generate notes for `add_instrument` ops by reusing the fill pipeline:
    a skeleton is rebuilt from the existing song (chords, feel, sections,
    ensemble) and ONLY the new instrument is filled — targeted generation,
    not a recompose. Deterministic enforcement (register/density) applies."""
    from music_assistant.band_agent.band_spec import (
        BandSkeleton,
        ChordSpanPlan,
        InstrumentDecl,
        SectionPlan,
    )
    from music_assistant.band_agent.pipeline import _fill_section, _sections_for_fill
    from music_assistant.band_agent.tools.groove_enforce import enforce_register
    from music_assistant.domain.song_state import Note, Part, RosterItem

    adds = [op for op in plan.operations if op.op == "add_instrument" and op.new_patch]
    if not adds:
        return song, []
    song = song.model_copy(deep=True)
    changes: list[str] = []
    header = song.header
    skeleton = BandSkeleton(
        genre=header.genre,
        rhythmic_feel=header.rhythmic_feel,
        key=header.key,
        tempo_bpm=max(21.0, min(299.0, header.tempo_bpm)),
        time_signature_numerator=header.time_signature[0],
        time_signature_denominator=header.time_signature[1],
        num_bars=max(4, min(128, header.num_bars)),
        sections=[
            SectionPlan(name=s.name, start_bar=s.start_bar, end_bar=s.end_bar, energy=s.energy)
            for s in header.sections
        ],
        chord_progression=[
            ChordSpanPlan(bar=c.bar, chord=c.chord) for c in header.chord_progression
        ],
    )
    skeleton_ctx = skeleton.model_dump(mode="json", exclude={"instruments"})
    skeleton_ctx["ensemble"] = [
        {"id": r.id, "instrument": r.instrument, "role": r.role,
         "playing_style": r.playing_style, "is_drum": r.is_drum}
        for r in song.roster
    ]
    existing = {r.id for r in song.roster}
    for op in adds:
        patch = reconcile_patch(op.new_name or op.new_patch, op.new_patch)
        try:
            program, preset = resolve_patch(patch)
        except UnknownPatchError:
            changes.append(f"(unknown patch {op.new_patch!r} — skipped)")
            continue
        base_id = (op.new_name or patch).lower().replace(" ", "_")[:24] or "added"
        new_id = base_id
        n = 2
        while new_id in existing:
            new_id = f"{base_id}_{n}"
            n += 1
        existing.add(new_id)
        decl = InstrumentDecl(
            id=new_id,
            instrument=op.new_name or patch.replace("_", " "),
            patch=patch,  # type: ignore[arg-type]
            role=op.role or "added by user request",
            playing_style=op.role or "",
        )
        notes = []
        for section in _sections_for_fill(skeleton_ctx):
            try:
                notes.extend(_fill_section(skeleton_ctx, decl, section))
            except Exception as exc:
                log.info("add_instrument fill failed for %s: %s", new_id, exc)
        fam = family_pitch_range(decl.instrument, patch)
        if fam:
            notes = enforce_register(notes, fam[0], fam[1], instrument_id=new_id)
        if not notes:
            changes.append(f"(could not compose notes for {new_id} — skipped)")
            continue
        song.roster.append(RosterItem(
            id=new_id,
            instrument=decl.instrument,
            patch=patch,
            midi_program=program,
            synth_preset=preset,
            role=decl.role,
            playing_style=decl.playing_style,
        ))
        song.parts[new_id] = Part(
            instrument_id=new_id,
            notes=[Note(bar=x.bar, start_beat=x.start_beat, pitch=x.pitch,
                        dur=max(0.05, x.dur), velocity=x.velocity) for x in notes],
        )
        changes.append(f"added {new_id} ({patch}, {len(notes)} notes)")
    return song, changes


def _match_part(song: SongState, target: str) -> list[str]:
    """Resolve a target string to part ids. "" / "all" = all melodic parts."""
    t = (target or "").strip().lower()
    if t in ("", "all", "todos", "todo", "everything"):
        return [r.id for r in song.roster if not r.is_drum]
    for r in song.roster:
        if r.id.lower() == t:
            return [r.id]
    hits = [
        r.id for r in song.roster
        if t in r.instrument.lower() or t in (r.patch or "").lower() or t in r.id.lower()
    ]
    return hits[:1]


def apply_edit(song: SongState, plan: EditPlan) -> tuple[SongState, list[str]]:
    """Apply the plan to a deep copy of the song. Returns (song, change log)."""
    song = song.model_copy(deep=True)
    changes: list[str] = []
    for op in plan.operations:
        if op.op == "set_tempo" and op.tempo_bpm > 20:
            changes.append(f"tempo {song.header.tempo_bpm:.0f} → {op.tempo_bpm:.0f} BPM")
            song.header.tempo_bpm = op.tempo_bpm
            continue

        ids = _match_part(song, op.target)
        if not ids and op.op != "set_tempo":
            changes.append(f"({op.op}: no match for {op.target!r} — skipped)")
            continue

        if op.op == "transpose" and op.semitones:
            roster_by_id = {r.id: r for r in song.roster}
            for pid in ids:
                r = roster_by_id.get(pid)
                if r is None or r.is_drum:
                    continue
                part = song.parts.get(pid)
                if not part:
                    continue
                for n in part.notes:
                    if n.pitch is not None:
                        n.pitch = max(0, min(127, n.pitch + op.semitones))
            changes.append(f"transposed {', '.join(ids)} by {op.semitones:+d} semitones")

        elif op.op == "replace_instrument" and op.new_patch:
            pid = ids[0]
            for r in song.roster:
                if r.id != pid:
                    continue
                if r.is_drum:
                    # Drum parts live on the GM percussion channel where the
                    # patch is meaningless — renaming them to "piano" would
                    # lie in the UI while still sounding like drums.
                    changes.append(f"{r.instrument}: sigue siendo batería (no se convierte)")
                    break
                # The plan's patch is authoritative here. reconcile_patch
                # keyword-matches the *name* — and the LLM often echoes the
                # OLD name in new_name ("electric_guitar_rhythm"), which
                # would silently veto the user's requested sound (piano →
                # clean_electric_guitar). Only fall back to reconciliation
                # when the patch itself isn't in the vocabulary.
                patch = op.new_patch
                try:
                    program, preset = resolve_patch(patch)
                except UnknownPatchError:
                    patch = reconcile_patch(op.new_name or op.new_patch, op.new_patch)
                    try:
                        program, preset = resolve_patch(patch)
                    except UnknownPatchError:
                        changes.append(f"(unknown patch {op.new_patch!r} — skipped)")
                        break
                old = r.patch
                old_name = r.instrument
                r.patch = patch
                r.midi_program = program
                r.synth_preset = preset
                # Always rename: keeping "electric_guitar_rhythm" on a part
                # that now plays a piano patch reads as a bug in the UI. An
                # echoed old name counts as "no name given".
                if op.new_name and op.new_name != old_name:
                    r.instrument = op.new_name
                else:
                    r.instrument = patch.replace("_", " ")
                # Fold the existing notes into the NEW instrument's physical
                # register (a piano line handed to a bass must drop octaves).
                fam = family_pitch_range(r.instrument, patch)
                part = song.parts.get(pid)
                if fam and part:
                    low, high = fam
                    for n in part.notes:
                        if n.pitch is None:
                            continue
                        q = n.pitch
                        while q > high:
                            q -= 12
                        while q < low:
                            q += 12
                        n.pitch = min(high, q)
                changes.append(f"{pid}: {old} → {patch}")
                break

        elif op.op == "remove_instrument":
            pid = ids[0]
            song.roster = [r for r in song.roster if r.id != pid]
            song.parts.pop(pid, None)
            changes.append(f"removed {pid}")

        elif op.op == "scale_velocity":
            for pid in ids:
                part = song.parts.get(pid)
                if not part:
                    continue
                for n in part.notes:
                    n.velocity = max(1, min(127, round(n.velocity * op.velocity_factor)))
            changes.append(
                f"velocity ×{op.velocity_factor:.2f} on {', '.join(ids)}"
            )
    return song, changes
