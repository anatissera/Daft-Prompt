"""Deterministic validation of a SongState (no LLM).

Returns structured issues so an agent's repair loop (later phases) can be told
exactly what to fix. Severity:
- "error"   — musically/structurally invalid (out of range, overflows bar, bad index).
- "warning" — allowed but notable (out-of-key note = possible intentional chromaticism).

Drums (is_drum) are exempt from pitch-range and key checks: they use the GM
percussion map, not melodic pitch.
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel

from .theory import beats_per_bar, in_key
from ..domain.song_state import SongState

_EPS = 1e-6


class ValidationIssue(BaseModel):
    instrument_id: str
    severity: Literal["error", "warning"]
    code: str
    message: str
    bar: Optional[int] = None


def validate_song(song: SongState) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    bpb = beats_per_bar(song.header.time_signature)
    num_bars = song.header.num_bars
    roster_by_id = {r.id: r for r in song.roster}

    # roster sanity
    seen: set[str] = set()
    for r in song.roster:
        if r.id in seen:
            issues.append(ValidationIssue(
                instrument_id=r.id, severity="error", code="duplicate_roster_id",
                message=f"roster id '{r.id}' appears more than once"))
        seen.add(r.id)

    for part_id, part in song.parts.items():
        roster = roster_by_id.get(part_id)
        if roster is None:
            issues.append(ValidationIssue(
                instrument_id=part_id, severity="error", code="part_without_roster",
                message=f"part '{part_id}' has no matching roster entry"))
            continue

        lo, hi = roster.midi_range
        for n in part.notes:
            # bar index
            if n.bar < 0 or n.bar >= num_bars:
                issues.append(ValidationIssue(
                    instrument_id=part_id, severity="error", code="bar_oob", bar=n.bar,
                    message=f"bar {n.bar} outside [0, {num_bars})"))

            # start beat within bar
            if n.start_beat < -_EPS or n.start_beat >= bpb + _EPS:
                issues.append(ValidationIssue(
                    instrument_id=part_id, severity="error", code="beat_oob", bar=n.bar,
                    message=f"start_beat {n.start_beat} outside [0, {bpb})"))

            # duration / bar overflow ("bad bar sums")
            if n.dur <= 0:
                issues.append(ValidationIssue(
                    instrument_id=part_id, severity="error", code="nonpositive_dur", bar=n.bar,
                    message=f"duration {n.dur} must be > 0"))
            elif n.start_beat + n.dur > bpb + _EPS:
                issues.append(ValidationIssue(
                    instrument_id=part_id, severity="error", code="note_overflows_bar", bar=n.bar,
                    message=f"note at beat {n.start_beat} dur {n.dur} overflows the {bpb}-beat bar"))

            # velocity
            if not (0 <= n.velocity <= 127):
                issues.append(ValidationIssue(
                    instrument_id=part_id, severity="error", code="velocity_oob", bar=n.bar,
                    message=f"velocity {n.velocity} outside [0, 127]"))

            if n.pitch is None:
                continue  # rest — nothing pitch-related to check

            # absolute MIDI bounds
            if not (0 <= n.pitch <= 127):
                issues.append(ValidationIssue(
                    instrument_id=part_id, severity="error", code="pitch_oob_midi", bar=n.bar,
                    message=f"pitch {n.pitch} outside MIDI [0, 127]"))
                continue

            if roster.is_drum:
                continue  # drums: skip range + key checks

            # instrument range
            if not (lo <= n.pitch <= hi):
                issues.append(ValidationIssue(
                    instrument_id=part_id, severity="error", code="pitch_out_of_range", bar=n.bar,
                    message=f"pitch {n.pitch} outside {roster.instrument} range [{lo}, {hi}]"))

            # key membership (warning only)
            if not in_key(n.pitch, song.header.key):
                issues.append(ValidationIssue(
                    instrument_id=part_id, severity="warning", code="out_of_key", bar=n.bar,
                    message=f"pitch {n.pitch} not in {song.header.key} (chromaticism?)"))

    return issues


def errors_only(issues: list[ValidationIssue]) -> list[ValidationIssue]:
    return [i for i in issues if i.severity == "error"]
