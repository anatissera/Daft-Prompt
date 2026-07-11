"""Deterministic per-instrument fill used when the LLM fill call fails.

MiniMax M3 (via opencode-go) intermittently truncates tool-call JSON mid-note
or refuses to call the tool at all. Rather than leaving that instrument
silent — which turns "compose a 6-piece band" into "here's a solo drum
loop" — we synthesise a note pattern from the skeleton.

Patterns are genre-aware. A rock request produces driving eighth-note bass
and quarter-note power-chord comping; a ballad keeps the sparse whole-note
chord-tone pattern. Without this, every failed-fill song sounded like a
Bach chorale regardless of what the user asked for.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from music_assistant.music.theory import active_chord_at, chord_tone_names

from ..band_spec import BandSkeleton, InstrumentDecl, NotePlan

log = logging.getLogger(__name__)


_NOTE_NAME_TO_PC = {
    "C": 0, "C#": 1, "Db": 1, "D": 2, "D#": 3, "Eb": 3,
    "E": 4, "F": 5, "F#": 6, "Gb": 6, "G": 7, "G#": 8, "Ab": 8,
    "A": 9, "A#": 10, "Bb": 10, "B": 11,
}


def _pitch_class(name: str) -> int | None:
    return _NOTE_NAME_TO_PC.get(name)


def _chord_tone_pcs(chord: str) -> list[int]:
    """Ordered chord tones (root first) as pitch classes 0-11."""
    names = chord_tone_names(chord)
    pcs: list[int] = []
    for n in names:
        pc = _pitch_class(n)
        if pc is not None and pc not in pcs:
            pcs.append(pc)
    return pcs


def _chord_root_pc(chord: str) -> int | None:
    """Fast fallback root when chord_tone_names returns nothing (bad symbol)."""
    m = re.match(r"^([A-G][#b]?)", chord.strip())
    if not m:
        return None
    return _pitch_class(m.group(1))


def _nearest_pitch_in_range(pc: int, lo: int, hi: int) -> int:
    """Cheapest MIDI number with pitch class `pc` in [lo, hi]."""
    for octave in range((lo // 12) - 1, (hi // 12) + 2):
        p = octave * 12 + pc
        if lo <= p <= hi:
            return p
    return max(lo, min(hi, 60))


def _role_profile(instrument: InstrumentDecl) -> str:
    """Bucket the instrument into a synthesis strategy from id/role/instrument text."""
    hay = f"{instrument.id} {instrument.role} {instrument.instrument}".lower()
    if "bass" in hay:
        return "bass"
    if "pad" in hay or "atmosphere" in hay or "strings" in hay:
        return "pad"
    if "lead" in hay or "melody" in hay or "solo" in hay:
        return "lead"
    if "rhythm" in hay or "guitar" in hay or "pluck" in hay or "comp" in hay:
        return "rhythm"
    return "harmony"


# Genre buckets → drives the rhythm density of each role. "driving" is what
# rock / punk / metal / funk want; "syncopated" fits pop / edm / hiphop /
# reggaeton; "sparse" is for ballad / ambient / jazz / classical.
_DRIVING = {"rock", "punk", "metal", "grunge", "funk", "hard rock", "dark metal", "rap metal"}
_SYNCOPATED = {"pop", "edm", "hip-hop", "hiphop", "hip hop", "trap", "reggaeton", "house", "techno", "future bass", "synthwave", "dance"}
_SPARSE = {"ballad", "ambient", "jazz", "classical", "lofi", "lo-fi", "lo fi", "chill"}


def _rhythm_bucket(genre: str) -> str:
    g = (genre or "").lower().strip()
    for kw in _DRIVING:
        if kw in g:
            return "driving"
    for kw in _SYNCOPATED:
        if kw in g:
            return "syncopated"
    for kw in _SPARSE:
        if kw in g:
            return "sparse"
    return "driving"  # default: assume the user wants a band, not a hymn


def _bass_pattern(bucket: str, root_pc: int, fifth_pc: int, bar: int) -> list[NotePlan]:
    """Bass note plan for one bar."""
    root = _nearest_pitch_in_range(root_pc, 28, 43)
    fifth = _nearest_pitch_in_range(fifth_pc, 28, 43)
    if bucket == "driving":
        # Straight eighth-notes on the root — the engine of rock/punk/metal.
        return [
            NotePlan(bar=bar, start_beat=b * 0.5, pitch=root, dur=0.45, velocity=104)
            for b in range(8)
        ]
    if bucket == "syncopated":
        # Root on 1 & 3, off-beat pickup on 4.5, fifth on 2.5 for movement.
        return [
            NotePlan(bar=bar, start_beat=0.0, pitch=root, dur=0.9, velocity=104),
            NotePlan(bar=bar, start_beat=2.0, pitch=root, dur=0.9, velocity=100),
            NotePlan(bar=bar, start_beat=2.5, pitch=fifth, dur=0.4, velocity=88),
            NotePlan(bar=bar, start_beat=3.5, pitch=root, dur=0.4, velocity=96),
        ]
    # sparse: whole-note root
    return [NotePlan(bar=bar, start_beat=0.0, pitch=root, dur=4.0, velocity=88)]


def _rhythm_pattern(
    bucket: str, root_pc: int, third_pc: int, fifth_pc: int, bar: int
) -> list[NotePlan]:
    """Rhythm-guitar / comping plan for one bar. Emits stacked chord tones as
    a small dyad/triad so the render sounds like a real strum."""
    root = _nearest_pitch_in_range(root_pc, 48, 60)
    third = _nearest_pitch_in_range(third_pc, 48, 60)
    fifth = _nearest_pitch_in_range(fifth_pc, 55, 67)
    if bucket == "driving":
        # Power-chord style: root + fifth on straight quarter notes.
        notes: list[NotePlan] = []
        for beat in (0.0, 1.0, 2.0, 3.0):
            for p in (root, fifth):
                notes.append(NotePlan(bar=bar, start_beat=beat, pitch=p, dur=0.9, velocity=96))
        return notes
    if bucket == "syncopated":
        # Quarter-note strums on 1, 2.5, 4 — pop/dance comping.
        notes = []
        for beat in (0.0, 2.5, 3.5):
            for p in (root, third, fifth):
                notes.append(NotePlan(bar=bar, start_beat=beat, pitch=p, dur=0.8, velocity=88))
        return notes
    # sparse: half-note stacked triad
    return [
        NotePlan(bar=bar, start_beat=0.0, pitch=p, dur=2.0, velocity=80)
        for p in (root, third, fifth)
    ]


def _lead_pattern(
    bucket: str, root_pc: int, third_pc: int, fifth_pc: int, bar: int
) -> list[NotePlan]:
    """Melodic lead plan for one bar."""
    r = _nearest_pitch_in_range(root_pc, 67, 79)
    t = _nearest_pitch_in_range(third_pc, 67, 79)
    f = _nearest_pitch_in_range(fifth_pc, 67, 79)
    if bucket == "driving":
        # Punchy quarter-note motif that outlines the chord.
        return [
            NotePlan(bar=bar, start_beat=0.0, pitch=r, dur=0.9, velocity=108),
            NotePlan(bar=bar, start_beat=1.0, pitch=f, dur=0.9, velocity=104),
            NotePlan(bar=bar, start_beat=2.0, pitch=t, dur=0.9, velocity=104),
            NotePlan(bar=bar, start_beat=3.0, pitch=f, dur=0.9, velocity=104),
        ]
    if bucket == "syncopated":
        # Anacrusis + landing — sung-hook style.
        return [
            NotePlan(bar=bar, start_beat=0.5, pitch=r, dur=0.9, velocity=100),
            NotePlan(bar=bar, start_beat=1.5, pitch=t, dur=0.9, velocity=100),
            NotePlan(bar=bar, start_beat=2.5, pitch=f, dur=0.9, velocity=96),
            NotePlan(bar=bar, start_beat=3.5, pitch=r, dur=0.4, velocity=88),
        ]
    return [
        NotePlan(bar=bar, start_beat=0.0, pitch=r, dur=2.0, velocity=96),
        NotePlan(bar=bar, start_beat=2.0, pitch=f, dur=2.0, velocity=96),
    ]


def _pad_pattern(root_pc: int, third_pc: int, fifth_pc: int, bar: int) -> list[NotePlan]:
    return [
        NotePlan(
            bar=bar, start_beat=0.0,
            pitch=_nearest_pitch_in_range(pc, 60, 72),
            dur=4.0, velocity=64,
        )
        for pc in (root_pc, third_pc, fifth_pc)
    ]


def _harmony_pattern(
    bucket: str, root_pc: int, third_pc: int, fifth_pc: int, bar: int
) -> list[NotePlan]:
    """Keys / piano / harmony support."""
    if bucket == "driving":
        # Same power-chord as rhythm but one octave up, quarter notes.
        r = _nearest_pitch_in_range(root_pc, 60, 72)
        f = _nearest_pitch_in_range(fifth_pc, 60, 72)
        notes: list[NotePlan] = []
        for beat in (0.0, 1.0, 2.0, 3.0):
            for p in (r, f):
                notes.append(NotePlan(bar=bar, start_beat=beat, pitch=p, dur=0.9, velocity=84))
        return notes
    if bucket == "syncopated":
        # Off-beat piano stabs.
        r = _nearest_pitch_in_range(root_pc, 60, 72)
        t = _nearest_pitch_in_range(third_pc, 60, 72)
        f = _nearest_pitch_in_range(fifth_pc, 60, 72)
        return [
            NotePlan(bar=bar, start_beat=0.5, pitch=r, dur=0.4, velocity=90),
            NotePlan(bar=bar, start_beat=1.5, pitch=t, dur=0.4, velocity=90),
            NotePlan(bar=bar, start_beat=2.5, pitch=f, dur=0.4, velocity=90),
            NotePlan(bar=bar, start_beat=3.5, pitch=t, dur=0.4, velocity=90),
        ]
    # sparse: block-chord half notes
    return [
        NotePlan(
            bar=bar, start_beat=beat,
            pitch=_nearest_pitch_in_range(pc, 60, 72),
            dur=2.0, velocity=80,
        )
        for beat in (0.0, 2.0)
        for pc in (root_pc, third_pc, fifth_pc)
    ]


def llm_seeded_fill(
    skeleton: BandSkeleton, instrument: InstrumentDecl, llm
) -> list[NotePlan]:
    """Genre-agnostic LLM fallback used when both structured-output attempts
    fail in `_fill_one`. Asks the LLM for ONE bar of notes conditioned on the
    skeleton's `rhythmic_feel` (director's commitment) + the instrument's
    `playing_style` + the first chord, then replays that bar across the whole
    song, transposing per bar's root note (shortest signed path -6..+6). No
    genre rules — the pattern comes from the director's own text commitment.
    Returns [] on any failure so the caller falls through to
    `deterministic_fill`."""
    if instrument.is_drum:
        return []
    from pydantic import BaseModel, Field

    class _SeedNote(BaseModel):
        start_beat: float = Field(ge=0.0)
        pitch: int | None = Field(description="MIDI pitch 0-127, null for rest")
        dur: float = Field(gt=0.0)
        velocity: int = Field(ge=1, le=127, default=96)

    class _SeedOut(BaseModel):
        pattern: list[_SeedNote] = Field(
            description="notes for ONE bar; start_beat is 0-indexed within the bar",
        )

    first_chord = active_chord_at(0, skeleton.chord_progression) or ""
    if not first_chord:
        return []
    anchor_root = _chord_root_pc(first_chord)
    if anchor_root is None:
        return []
    beats_per_bar = skeleton.time_signature_numerator
    system = (
        "You are a specialist studio musician generating a ONE-BAR loopable "
        "pattern for a single instrument. Match the ensemble's committed "
        "rhythmic feel and this instrument's playing style. Emit only notes "
        "within bar 0 (start_beat between 0 and the beats-per-bar count). "
        "Pitches around the FIRST chord's root — the caller transposes per "
        "bar. Structured object only; do not think out loud."
    )
    payload = (
        f"Genre: {skeleton.genre}\n"
        f"Tempo: {skeleton.tempo_bpm} BPM\n"
        f"Time signature: {beats_per_bar}/{skeleton.time_signature_denominator}\n"
        f"Key: {skeleton.key}\n\n"
        f"Ensemble rhythmic_feel (director's commitment):\n{skeleton.rhythmic_feel}\n\n"
        f"This instrument: {instrument.instrument} ({instrument.role})\n"
        f"Playing style: {instrument.playing_style}\n\n"
        f"First chord: {first_chord}\n"
        f"Song length to replay across: {skeleton.num_bars} bars."
    )
    try:
        structured = llm.with_structured_output(_SeedOut)
        seed: _SeedOut = structured.invoke([("system", system), ("human", payload)])
    except Exception as exc:
        log.info("llm_seeded_fill fell through for %s: %s", instrument.id, exc)
        return []
    if not isinstance(seed, _SeedOutput) or not seed.pattern:
        return []

    notes: list[NotePlan] = []
    for bar in range(skeleton.num_bars):
        bar_chord = active_chord_at(bar, skeleton.chord_progression) or first_chord
        bar_root = _chord_root_pc(bar_chord) or anchor_root
        raw = (bar_root - anchor_root) % 12
        shift = raw if raw <= 6 else raw - 12
        for sn in seed.pattern:
            if sn.pitch is None:
                pitch = None
            else:
                pitch = max(0, min(127, sn.pitch + shift))
            notes.append(NotePlan(
                bar=bar,
                start_beat=max(0.0, min(float(beats_per_bar), sn.start_beat)),
                pitch=pitch,
                dur=sn.dur,
                velocity=sn.velocity,
            ))
    return notes


def deterministic_fill(
    skeleton: BandSkeleton, instrument: InstrumentDecl
) -> list[NotePlan]:
    """Return a note list that covers `skeleton.num_bars`, following the
    chord progression, the instrument's role, and the genre's rhythmic feel."""
    if instrument.is_drum:
        return []
    profile = _role_profile(instrument)
    bucket = _rhythm_bucket(skeleton.genre)
    notes: list[NotePlan] = []
    for bar in range(skeleton.num_bars):
        chord = active_chord_at(bar, skeleton.chord_progression)
        if not chord:
            continue
        tones = _chord_tone_pcs(chord)
        if not tones:
            root = _chord_root_pc(chord)
            if root is None:
                continue
            tones = [root]
        root_pc = tones[0]
        third_pc = tones[1] if len(tones) > 1 else root_pc
        fifth_pc = tones[2] if len(tones) > 2 else root_pc

        if profile == "bass":
            notes.extend(_bass_pattern(bucket, root_pc, fifth_pc, bar))
        elif profile == "pad":
            notes.extend(_pad_pattern(root_pc, third_pc, fifth_pc, bar))
        elif profile == "lead":
            notes.extend(_lead_pattern(bucket, root_pc, third_pc, fifth_pc, bar))
        elif profile == "rhythm":
            notes.extend(_rhythm_pattern(bucket, root_pc, third_pc, fifth_pc, bar))
        else:  # harmony / keys / piano
            notes.extend(_harmony_pattern(bucket, root_pc, third_pc, fifth_pc, bar))
    return notes


# ---------------------------------------------------------------------------
# Section-scoped variants used by the instrument agent's section-splitting
# loop (`agents.instrument.compose_part`). They keep the same deterministic
# behaviour as the whole-song version but only cover the requested bar range.
# ---------------------------------------------------------------------------


class _RoleShim:
    """Adapter so deterministic_fill can accept a `RosterItem` where
    `InstrumentDecl` is normally expected. Only the fields the profile
    heuristic reads (id/role/instrument/is_drum) are used."""

    def __init__(self, ri: Any):
        self.id = ri.id
        self.instrument = ri.instrument
        self.role = ri.role
        self.is_drum = ri.is_drum


def deterministic_section(header: Any, section: Any, roster_item: Any) -> list[Any]:
    """Deterministic fill scoped to a single section. Same rhythm/genre
    bucket logic as `deterministic_fill` but only emits bars
    `section.start_bar` through `section.end_bar - 1`. Returns
    `song_state.Note` objects (not `NotePlan`) so callers in the instrument
    agent can extend `Part.notes` directly."""
    from music_assistant.domain.song_state import Note

    if roster_item.is_drum:
        return []
    shim = _RoleShim(roster_item)
    profile = _role_profile(shim)
    bucket = _rhythm_bucket(header.genre)
    out: list[Note] = []
    for bar in range(section.start_bar, section.end_bar):
        chord = active_chord_at(bar, header.chord_progression)
        if not chord:
            continue
        tones = _chord_tone_pcs(chord)
        if not tones:
            root = _chord_root_pc(chord)
            if root is None:
                continue
            tones = [root]
        r, t, f = tones[0], tones[1] if len(tones) > 1 else tones[0], tones[2] if len(tones) > 2 else tones[0]
        if profile == "bass":
            plans = _bass_pattern(bucket, r, f, bar)
        elif profile == "pad":
            plans = _pad_pattern(r, t, f, bar)
        elif profile == "lead":
            plans = _lead_pattern(bucket, r, t, f, bar)
        elif profile == "rhythm":
            plans = _rhythm_pattern(bucket, r, t, f, bar)
        else:
            plans = _harmony_pattern(bucket, r, t, f, bar)
        for p in plans:
            out.append(Note(
                bar=p.bar,
                start_beat=p.start_beat,
                pitch=p.pitch,
                dur=p.dur,
                velocity=p.velocity,
            ))
    return out


def llm_seeded_section(header: Any, section: Any, roster_item: Any, llm) -> list[Any]:
    """Ask the LLM for ONE bar's worth of notes conditioned on the director's
    committed `rhythmic_feel` + this instrument's `playing_style` + the
    section's first chord, then replay that pattern across the section with
    each bar transposed to its own chord root. Uses the same LLM the caller
    passed in — no hardcoded genre rules, purely a smaller output ask when
    the full-section call couldn't complete.

    Returns [] on any failure so the caller falls through to
    `deterministic_section`."""
    from music_assistant.domain.song_state import ChordSpan, Note
    from pydantic import BaseModel, Field

    class _SeedNote(BaseModel):
        start_beat: float = Field(ge=0.0)
        pitch: int | None = Field(description="MIDI pitch 0-127 or null for a rest")
        dur: float = Field(gt=0.0, description="duration in beats")
        velocity: int = Field(ge=0, le=127, default=96)

    class _SeedOutput(BaseModel):
        # A single-bar loopable pattern. Kept schema-lean so the LLM only
        # spends output tokens on the note grid, not on prose or wrapping.
        pattern: list[_SeedNote] = Field(
            description="notes for ONE bar (start_beat is 0-indexed within the bar)",
        )

    first_chord = active_chord_at(section.start_bar, header.chord_progression) or ""
    if not first_chord:
        return []

    system = (
        "You are a specialist studio musician generating a ONE-BAR loopable "
        "pattern for a single instrument. Match the ensemble's committed "
        "rhythmic feel and this instrument's playing style. Emit only notes "
        "within bar 0 (start_beat between 0 and the beats-per-bar count). "
        "The pattern will be replayed across the section with each bar's "
        "root note substituted, so pick pitches around the FIRST chord's "
        "root — the caller will transpose per bar.\n\n"
        "Do not think out loud. Return the structured object only."
    )
    beats_per_bar = header.time_signature[0]
    payload = (
        f"Genre: {header.genre}\n"
        f"Tempo: {header.tempo_bpm} BPM\n"
        f"Time signature: {beats_per_bar}/{header.time_signature[1]}\n"
        f"Key: {header.key}\n\n"
        f"Ensemble rhythmic feel (director's commitment):\n{header.rhythmic_feel}\n\n"
        f"This instrument: {roster_item.instrument} ({roster_item.role})\n"
        f"Playing style: {roster_item.playing_style}\n\n"
        f"First chord of the section: {first_chord}\n"
        f"Section: '{section.name}', energy {section.energy}, "
        f"{section.end_bar - section.start_bar} bars long."
    )
    try:
        structured = llm.with_structured_output(_SeedOutput)
        seed: _SeedOutput = structured.invoke([("system", system), ("human", payload)])
    except Exception as exc:
        log.info("llm_seeded_section fell through for %s: %s", roster_item.id, exc)
        return []
    if not isinstance(seed, _SeedOutput) or not seed.pattern:
        return []

    # Root-based transposition per bar so the pattern actually follows the
    # section's chord progression instead of blaring the same chord for
    # every bar. Pitches in the seed pattern are interpreted as offsets
    # from the FIRST chord's root; we shift by the delta between each bar's
    # root and that anchor.
    anchor_root = _chord_root_pc(first_chord)
    if anchor_root is None:
        return []
    notes: list[Note] = []
    for bar in range(section.start_bar, section.end_bar):
        bar_chord = active_chord_at(bar, header.chord_progression) or first_chord
        bar_root = _chord_root_pc(bar_chord)
        if bar_root is None:
            bar_root = anchor_root
        # signed shortest-path shift (-6..+6 semitones) so a I→V move
        # doesn't jump an octave.
        raw = (bar_root - anchor_root) % 12
        shift = raw if raw <= 6 else raw - 12
        for sn in seed.pattern:
            if sn.pitch is None:
                pitch = None
            else:
                pitch = max(0, min(127, sn.pitch + shift))
            notes.append(Note(
                bar=bar,
                start_beat=max(0.0, min(float(beats_per_bar), sn.start_beat)),
                pitch=pitch,
                dur=sn.dur,
                velocity=sn.velocity,
            ))
    return notes
