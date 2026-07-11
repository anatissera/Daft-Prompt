"""Deterministic validation of a SongState (no LLM).

Returns structured issues so an agent's repair loop (later phases) can be told
exactly what to fix. Severity:
- "error"   — musically/structurally invalid (out of range, overflows bar, bad index).
- "warning" — allowed but notable (a note that fits neither the active chord nor the
              key = possible intentional chromaticism, possible clash).

Drums (is_drum) are exempt from pitch-range and harmony checks: they use the GM
percussion map, not melodic pitch.
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel

from .theory import active_chord_at, beats_per_bar, chord_pitch_classes, in_key
from .theory_tools import detect_overlaps
from ..domain.song_state import SongState


_MONOPHONIC_KEYWORDS = ("bass", "lead", "solo", "melody", "vocal")


def _is_monophonic_by_convention(role: str, instrument: str) -> bool:
    """Heuristic: instruments whose role/name mentions bass/lead/solo/melody/vocal
    are assumed monophonic. Piano/guitar/pad/strings are not. False positives
    only surface as `error`s in the repair loop, which is safe: the LLM can
    respond by de-overlapping the two notes."""
    haystack = f"{role} {instrument}".lower()
    return any(word in haystack for word in _MONOPHONIC_KEYWORDS)

_EPS = 1e-6


class ValidationIssue(BaseModel):
    instrument_id: str
    severity: Literal["error", "warning"]
    code: str
    message: str
    bar: Optional[int] = None


def check_style_progression(song: SongState) -> list[ValidationIssue]:
    """Soft stylistic check: the produced chord progression is compared against
    the modal progression of the corpus for the same genre. When the two share
    zero root pitch classes, emit a single song-level warning — the arrangement
    may still be valid, but it drifts from the canonical shape of the style.

    Returns [] when there is no corpus, no progression, or the corpus has no
    matching genre (so this check never fails hard)."""
    prog = song.header.chord_progression
    if not prog:
        return []
    try:
        from ..corpus.retrieve import retrieve_style_examples
        examples = retrieve_style_examples(song.header.genre, energy="medium", n=5)
    except Exception:
        return []
    canonical_roots: set[str] = set()
    for ex in examples:
        for symbol in ex.progression:
            root = _root_letter(symbol)
            if root:
                canonical_roots.add(root)
    if not canonical_roots:
        return []
    produced_roots = {_root_letter(cs.chord) for cs in prog}
    produced_roots.discard("")
    overlap = produced_roots & canonical_roots
    if not overlap and produced_roots:
        return [ValidationIssue(
            instrument_id="_song", severity="warning", code="unusual_progression_for_genre",
            message=(
                f"progression roots {sorted(produced_roots)} share no root with the corpus "
                f"canonical set {sorted(canonical_roots)} for {song.header.genre!r}"
            ),
        )]
    return []


def _root_letter(symbol: str) -> str:
    s = (symbol or "").strip()
    if not s or s == "N.C.":
        return ""
    # 'A', 'Bb', 'C#', ...
    if len(s) >= 2 and s[1] in ("b", "#", "-"):
        return s[:2].replace("-", "b")
    return s[:1]


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

        # empty part: a rostered instrument that produced no sounding notes is almost
        # certainly a failed generation (the model describes a part in notes_summary but
        # returns an empty / all-rests note list — observed with the drum agent). Flag it
        # as an error so the repair loop asks the instrument to actually compose. Applies
        # to drums too, since they sound via the GM percussion map like any other part.
        if not any(n.pitch is not None for n in part.notes):
            issues.append(ValidationIssue(
                instrument_id=part_id, severity="error", code="empty_part",
                message=f"'{part_id}' produced no sounding notes — compose an actual part "
                        f"(a non-empty list of notes with real pitches)"))
            continue

        if not roster.is_drum and _is_monophonic_by_convention(roster.role, roster.instrument):
            for bar, msg in detect_overlaps(part, song.header):
                issues.append(ValidationIssue(
                    instrument_id=part_id, severity="error", code="note_overlap", bar=bar,
                    message=f"{roster.instrument} is monophonic; {msg}"))

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

            # instrument range: no per-roster clamp anymore — the instrument
            # agent picks its own register from playing_style + role instead of
            # the director declaring midi_low/midi_high. Absolute MIDI [0, 127]
            # is still enforced above.

            # harmony membership (warning only). Chord-aware: a note that is a tone of
            # the bar's active chord is fine even when it's outside the key (e.g. the
            # G# of an E7 secondary dominant in E minor), and a diatonic note is fine as
            # melodic tension/passing material. Only a note that fits NEITHER the active
            # chord NOR the key is flagged as a possible clash — we never enforce it
            # (warning), so intentional chromaticism and expressivity are preserved.
            active = active_chord_at(n.bar, song.header.chord_progression)
            chord_pcs = chord_pitch_classes(active) if active else frozenset()
            is_chord_tone = bool(chord_pcs) and (n.pitch % 12) in chord_pcs
            if not is_chord_tone and not in_key(n.pitch, song.header.key):
                where = f"{song.header.key}" + (f" or chord {active}" if active else "")
                issues.append(ValidationIssue(
                    instrument_id=part_id, severity="warning", code="out_of_key", bar=n.bar,
                    message=f"pitch {n.pitch} fits neither {where} (chromaticism?)"))

    issues.extend(check_style_progression(song))
    return issues


def harmonic_fit(song: SongState) -> dict[str, float]:
    """Objective harmony metric: fraction of a part's *evaluable* sounding notes that
    are tones of the active chord. A note is evaluable only when an active chord is
    known for its bar; drums and notes in chordless bars are ignored. Returns one entry
    per non-drum instrument plus "_overall". Empty parts / no evaluable notes → 1.0
    (nothing to fault). Useful for A/B-comparing compose runs without listening."""
    roster_by_id = {r.id: r for r in song.roster}
    progression = song.header.chord_progression
    per_instrument: dict[str, float] = {}
    total_eval = 0
    total_hits = 0
    for part_id, part in song.parts.items():
        roster = roster_by_id.get(part_id)
        if roster is None or roster.is_drum:
            continue
        evaluable = 0
        hits = 0
        for n in part.notes:
            if n.pitch is None:
                continue
            chord = active_chord_at(n.bar, progression)
            chord_pcs = chord_pitch_classes(chord) if chord else frozenset()
            if not chord_pcs:
                continue
            evaluable += 1
            if (n.pitch % 12) in chord_pcs:
                hits += 1
        per_instrument[part_id] = (hits / evaluable) if evaluable else 1.0
        total_eval += evaluable
        total_hits += hits
    per_instrument["_overall"] = (total_hits / total_eval) if total_eval else 1.0
    return per_instrument


def errors_only(issues: list[ValidationIssue]) -> list[ValidationIssue]:
    return [i for i in issues if i.severity == "error"]
