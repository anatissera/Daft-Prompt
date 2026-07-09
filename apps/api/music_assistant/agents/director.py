"""Director agent — reasons an arrangement (header + roster) from a style string.

This is the first LLM node. It does NOT compose notes (that's the instrument agents);
it decides key/tempo/meter/form, chord progression, per-instrument playing style, and
the ordered composition groups that control layering order.
"""

from __future__ import annotations

import json
import re
from typing import Literal, Optional

from langsmith import traceable
from pydantic import BaseModel, Field

from ..domain.errors import OffTopicRequest
from ..domain.song_state import (
    ChordSpan,
    CompositionGroup,
    Header,
    RosterItem,
    Section,
    SongState,
)
from ..skills.progression import suggest_chord_progression, suggest_form

_DEFAULT_REFUSAL = (
    "I only handle music tasks: compose a short sketch, analyze an audio file you upload, "
    "or answer questions about a reference you already shared. Try \"compose a slow blues\"."
)

MIN_ROSTER = 3
MAX_ROSTER = 8
MIN_BARS = 4
MAX_BARS = 32


class ArrangementInstrument(BaseModel):
    id: str = Field(description="short unique id, e.g. 'bass', 'lead_synth'")
    instrument: str = Field(description="human name, e.g. 'electric_bass'")
    midi_program: int = Field(0, ge=0, le=127, description="General MIDI program")
    midi_low: int = Field(0, ge=0, le=127)
    midi_high: int = Field(127, ge=0, le=127)
    role: str = Field(description="this instrument's musical role in the arrangement")
    playing_style: str = Field(
        description=(
            "1-2 sentences of idiomatic technique for this instrument in this genre. "
            "Example: 'Anchor beat 1. Ghost notes on snare between 2 and 4. "
            "Hi-hat strictly 16ths, open on the and-of-4 in the last bar of each phrase.'"
        )
    )
    is_drum: bool = False


class ArrangementSection(BaseModel):
    name: str
    start_bar: int = Field(ge=0)
    end_bar: int = Field(ge=0)
    energy: Literal["low", "medium", "high"] = "medium"


class DirectorOutput(BaseModel):
    off_topic: bool = Field(
        False,
        description="true when the request is NOT a music-composition task (chit-chat, "
        "trivia, coding, lyrics-only, recommendations, etc.)",
    )
    refusal: str = Field(
        "",
        description="when off_topic, a short friendly message (in the user's language) "
        "stating you only handle music tasks and listing what you can do",
    )
    genre: str = ""
    key: str = Field("", description="e.g. 'F# minor', 'C major'")
    tempo_bpm: float = Field(120.0, gt=0)
    time_sig_numerator: int = Field(4, gt=0)
    time_sig_denominator: int = Field(4, gt=0)
    num_bars: int = Field(MIN_BARS, gt=0, description=f"between {MIN_BARS} and {MAX_BARS} bars")
    sections: list[ArrangementSection] = Field(
        default_factory=list,
        description="3-6 named sections covering all bars without overlap",
    )
    chord_progression: list[ChordSpan] = Field(
        default_factory=list,
        description="one ChordSpan per bar covering all bars (bar 0..num_bars-1)",
    )
    instruments: list[ArrangementInstrument] = Field(
        default_factory=list,
        description=f"between {MIN_ROSTER} and {MAX_ROSTER} instruments",
    )
    composition_groups: list[CompositionGroup] = Field(
        default_factory=list,
        description=(
            "ordered batches for layered composition. Each instrument_id must appear "
            "in exactly one group. Put rhythm foundation first, harmony second, "
            "melody/texture last."
        ),
    )


_SYSTEM = f"""You are the musical director of an ensemble. You ONLY handle music-composition tasks. If the request is not asking you to compose a music sketch (e.g. chit-chat, trivia, coding, weather, recommendations, or writing lyrics/text only), set off_topic=true and put a short friendly message in `refusal` (in the user's language) saying you only handle music tasks and listing what you can do: compose a sketch, analyze an uploaded audio file, or answer questions about a reference already shared. In that case leave the arrangement fields empty.

Otherwise set off_topic=false and, given a style description, produce a complete arrangement plan with the following required outputs:

1. ARRANGEMENT: key, tempo, time signature, num_bars ({MIN_BARS}-{MAX_BARS}). Reason about what genuinely fits the style.

2. SONG FORM: 3-6 named sections (e.g. Intro, Verse, PreChorus, Chorus, Bridge, Outro). Each section has start_bar, end_bar, and an energy level: "low", "medium", or "high". Sections must cover all bars 0..num_bars-1 without overlap or gap.

3. CHORD PROGRESSION: one ChordSpan per bar covering every bar (0..num_bars-1). Use chord names like "Dm7", "G7", "Cm9". Chords must fit the key and genre idiom.

4. INSTRUMENTATION: {MIN_ROSTER}-{MAX_ROSTER} instruments. For each instrument:
   - A General MIDI program number and a sensible MIDI pitch range for that instrument in that register (e.g. bass: 28-55, not 0-127).
   - Its musical role. All percussion must be a single drum-kit roster item with is_drum=true — do NOT create separate entries for kick, snare, hi-hat, cymbals, or toms; those are MIDI pitches inside the one kit.
   - A playing_style: 1-2 sentences of idiomatic technique a real musician of this instrument in this genre would immediately recognise. Be specific about rhythm, articulation, and register. Examples:
     * Funk bass: "Anchor beat 1 firmly. Use ghost notes between the 2 and 4. Slap on the upbeat 16th just before beat 3 in bar-ending phrases."
     * Funk guitar: "Short 16th-note chord stabs on beats 2 and 4 with percussive muting between hits. Wah on fill bars. Stay in the mid register."
     * String pad: "Sustained whole-note pads below the melody register. Swell into the chorus. Avoid the top octave to leave room for the lead."

5. COMPOSITION GROUPS: ordered batches specifying which instruments compose in which wave. Each instrument_id must appear in exactly one group. Put rhythmic foundation first (drums, bass), harmonic layer second, melodic/textural layer last. Set max_negotiation_rounds (0-2) — use 1 for rhythm section, 0 for texture layers.

If the style description contains a CompositionBrief with instrument_requests, treat it as binding reference guidance:
- Keep each requested instrument family in the roster unless the request explicitly says to avoid it.
- Use the request's timbre midi_program, midi_range, and drum/percussion status when present.
- Fold pattern, transfer_mode, fidelity, and any symbolic_seed summary into playing_style so the instrument agent can apply it.
- For literal transfer, mention the seed as a starting motif/pattern, not raw tab text.

Do not use a fixed genre-to-instrument mapping. Reason about what genuinely fits the requested style."""


def _prompt(style: str) -> list[tuple[str, str]]:
    return [("system", _SYSTEM), ("human", f"Style: {style}")]


_ID_SAFE_RE = re.compile(r"[^a-z0-9]+")


def _slug(value: str, fallback: str) -> str:
    cleaned = _ID_SAFE_RE.sub("_", (value or "").strip().lower()).strip("_")
    return cleaned or fallback


def _repair_roster_ids(
    items: list[ArrangementInstrument],
) -> tuple[list[ArrangementInstrument], dict[str, str]]:
    """The LLM often hands back empty or repeated `id` fields; downstream the parts
    dict is keyed by id so duplicates collapse into a single audible track. Rewrite
    each id to a unique slug (id → instrument → role → idx) and return the original→new
    mapping so composition groups can be remapped to the repaired ids. The mapping is
    the identity when ids are already unique and non-empty (the common case)."""
    seen: set[str] = set()
    repaired: list[ArrangementInstrument] = []
    id_map: dict[str, str] = {}
    for idx, item in enumerate(items):
        base = _slug(item.id, "") or _slug(item.instrument, "") or _slug(item.role, "") or f"agent_{idx}"
        candidate = base
        suffix = 2
        while candidate in seen:
            candidate = f"{base}_{suffix}"
            suffix += 1
        seen.add(candidate)
        repaired.append(item.model_copy(update={"id": candidate}))
        id_map.setdefault(item.id, candidate)  # first occurrence wins
    return repaired, id_map


def _remap_groups(
    groups: list[CompositionGroup], id_map: dict[str, str]
) -> list[CompositionGroup]:
    return [
        group.model_copy(
            update={"instrument_ids": [id_map.get(iid, iid) for iid in group.instrument_ids]}
        )
        for group in groups
    ]


_DRUM_KIT_ID = "drums"


def _collapse_drum_components(
    items: list[ArrangementInstrument], groups: list[CompositionGroup]
) -> tuple[list[ArrangementInstrument], list[CompositionGroup]]:
    """The director sometimes emits separate kick/snare/hi-hat roster items; each then
    becomes its own instrument agent composing a fragment of one kit. Collapse every
    is_drum item into a single canonical "drums" kit, and remap composition groups so
    the kit appears in exactly one group (the first that referenced any drum component),
    de-duplicating ids. A roster with 0 or 1 drum items is returned unchanged."""
    drum_ids = [item.id for item in items if item.is_drum]
    if len(drum_ids) <= 1:
        return items, groups

    kit = ArrangementInstrument(
        id=_DRUM_KIT_ID,
        instrument="drum_kit",
        midi_program=0,
        midi_low=35,
        midi_high=81,
        role="full percussion kit",
        playing_style="One coherent kit: kick on the downbeats, snare on the backbeat, "
        "steady hi-hat subdivision with fills into section changes.",
        is_drum=True,
    )
    collapsed: list[ArrangementInstrument] = []
    inserted = False
    for item in items:
        if item.is_drum:
            if not inserted:
                collapsed.append(kit)
                inserted = True
            continue
        collapsed.append(item)

    drum_id_set = set(drum_ids)
    new_groups: list[CompositionGroup] = []
    kit_assigned = False
    for group in groups:
        new_ids: list[str] = []
        for iid in group.instrument_ids:
            mapped = _DRUM_KIT_ID if iid in drum_id_set else iid
            if mapped == _DRUM_KIT_ID:
                if kit_assigned or _DRUM_KIT_ID in new_ids:
                    continue  # kit already placed (here or in an earlier group)
                new_ids.append(_DRUM_KIT_ID)
            elif mapped not in new_ids:
                new_ids.append(mapped)
        if _DRUM_KIT_ID in new_ids:
            kit_assigned = True
        new_groups.append(group.model_copy(update={"instrument_ids": new_ids}))
    return collapsed, new_groups


def _requested_instrument_families(style: str) -> list[str]:
    match = re.search(r"^instrument_requests_json:\s*(\{.*\})\s*$", style, re.MULTILINE)
    if not match:
        return []
    try:
        parsed = json.loads(match.group(1))
    except json.JSONDecodeError:
        return []
    if not isinstance(parsed, dict):
        return []
    families = []
    for family in ["drums", "bass", "guitar", "piano"]:
        if family in parsed:
            families.append(family)
    return families


def _canonicalize_requested_instrument_ids(
    style: str,
    items: list[ArrangementInstrument],
    groups: list[CompositionGroup],
) -> tuple[list[ArrangementInstrument], list[CompositionGroup]]:
    families = _requested_instrument_families(style)
    if not families:
        return items, groups
    used_ids = {item.id for item in items}
    id_map: dict[str, str] = {}
    updated = list(items)
    for family in families:
        if family in used_ids:
            continue
        for index, item in enumerate(updated):
            if item.id in id_map:
                continue
            if not _arrangement_item_matches_family(item, family):
                continue
            old_id = item.id
            updated[index] = item.model_copy(update={"id": family})
            used_ids.discard(old_id)
            used_ids.add(family)
            id_map[old_id] = family
            break
    if not id_map:
        return updated, groups
    return updated, _remap_groups(groups, id_map)


def _arrangement_item_matches_family(item: ArrangementInstrument, family: str) -> bool:
    haystack = f"{item.id} {item.instrument} {item.role}".lower()
    if family == "drums":
        return item.is_drum or any(alias in haystack for alias in ["drums", "drum_kit", "percussion"])
    aliases = {
        "bass": ["bass", "electric_bass", "low_end", "low end"],
        "guitar": ["guitar", "electric_guitar", "acoustic_guitar", "rhythm_guitar", "lead_guitar"],
        "piano": ["piano", "electric_piano", "keyboard", "keys", "rhodes"],
    }
    return any(alias in haystack for alias in aliases.get(family, [family]))


def _normalize_guitar_items(
    items: list[ArrangementInstrument],
    groups: list[CompositionGroup],
) -> tuple[list[ArrangementInstrument], list[CompositionGroup]]:
    used_ids = {item.id for item in items}
    id_map: dict[str, str] = {}
    updated: list[ArrangementInstrument] = []
    for item in items:
        if not _arrangement_item_matches_family(item, "guitar"):
            updated.append(item)
            continue

        role_kind = _guitar_role_kind(item)
        target_id = "lead_guitar" if role_kind == "lead" else "rhythm_guitar"
        new_id = item.id
        if _guitar_id_should_be_normalized(item):
            used_ids.discard(item.id)
            new_id = _unique_id(target_id, used_ids)
            used_ids.add(new_id)
            id_map[item.id] = new_id

        instrument = _guitar_instrument_name(item, role_kind)
        playing_style = _guitar_playing_style(item, role_kind)
        updated.append(
            item.model_copy(
                update={
                    "id": new_id,
                    "instrument": instrument,
                    "playing_style": playing_style,
                }
            )
        )
    if not id_map:
        return updated, groups
    return updated, _remap_groups(groups, id_map)


def _guitar_id_should_be_normalized(item: ArrangementInstrument) -> bool:
    text = f"{item.id} {item.instrument}".lower()
    return any(
        marker in text
        for marker in [
            "hard rock",
            "hard_rock",
            "heavy",
            "distortion",
            "distorted",
            "overdrive",
            "overdriven",
        ]
    )


def _guitar_role_kind(item: ArrangementInstrument) -> Literal["rhythm", "lead"]:
    text = f"{item.id} {item.instrument} {item.role} {item.playing_style}".lower()
    if any(token in text for token in ["lead", "solo", "melody", "melodic", "hook", "fill"]):
        return "lead"
    return "rhythm"


def _guitar_instrument_name(item: ArrangementInstrument, role_kind: str) -> str:
    text = f"{item.id} {item.instrument} {item.role} {item.playing_style}".lower()
    if role_kind == "lead" or any(
        token in text for token in ["hard rock", "heavy", "distort", "overdrive", "overdriven", "grunge"]
    ):
        return "electric_guitar_overdriven"
    return "electric_guitar_clean"


def _guitar_playing_style(item: ArrangementInstrument, role_kind: str) -> str:
    base = item.playing_style.strip()
    if role_kind == "lead":
        guidance = (
            "Band guidance: use short guitar hooks and fills between phrases, "
            "answer the rhythm riff, approximate bends/slides with nearby MIDI notes, "
            "and avoid constant keyboard-like scale runs."
        )
    else:
        guidance = (
            "Band guidance: use repeated riff cells, power chords, palm-muted eighths, "
            "occasional syncopated strums, and leave room for the lead guitar."
        )
    return f"{base} {guidance}".strip() if base else guidance


def _unique_id(base: str, used_ids: set[str]) -> str:
    candidate = base
    suffix = 2
    while candidate in used_ids:
        candidate = f"{base}_{suffix}"
        suffix += 1
    return candidate


def _clamp_roster(items: list[ArrangementInstrument]) -> list[ArrangementInstrument]:
    return items[:MAX_ROSTER]


def _clamp_num_bars(value: int) -> int:
    return max(MIN_BARS, min(MAX_BARS, value))


def _clamp_sections(sections: list[ArrangementSection], num_bars: int) -> list[Section]:
    clamped = []
    for section in sections:
        start = max(0, min(section.start_bar, num_bars - 1))
        end = max(start + 1, min(section.end_bar, num_bars))
        clamped.append(
            Section(name=section.name, start_bar=start, end_bar=end, energy=section.energy)
        )
    return clamped


def _validate_groups(
    groups: list[CompositionGroup], instruments: list[ArrangementInstrument]
) -> None:
    instrument_ids = {i.id for i in instruments}
    seen: set[str] = set()
    for group in groups:
        for iid in group.instrument_ids:
            if iid not in instrument_ids:
                raise ValueError(f"composition group references unknown instrument: {iid!r}")
            if iid in seen:
                raise ValueError(
                    f"instrument {iid!r} appears in multiple composition groups"
                )
            seen.add(iid)
    missing = instrument_ids - seen
    if missing:
        raise ValueError(f"instruments not assigned to any group: {missing}")


def _backfill_chord_progression(
    spans: list[ChordSpan], key: str, mood: str, num_bars: int, sections: list[Section]
) -> list[ChordSpan]:
    """Guarantee every bar has a chord. The director's own spans win; bars it
    left uncovered (or placed out of range) are filled deterministically from
    the progression skill so downstream instruments, harmonic-fit scoring, and
    bass-downbeat enforcement always have a complete harmonic anchor."""
    in_range = [s for s in spans if 0 <= s.bar < num_bars]
    covered = {s.bar for s in in_range}
    if len(covered) >= num_bars:
        return sorted(in_range, key=lambda s: s.bar)
    by_bar = {s.bar: s for s in suggest_chord_progression(key, mood, num_bars, sections)}
    for span in in_range:
        by_bar[span.bar] = span
    return [by_bar[bar] for bar in range(num_bars)]


def arrangement_to_song(style: str, out: DirectorOutput) -> SongState:
    clamped_instruments, id_map = _repair_roster_ids(_clamp_roster(out.instruments))
    groups = _remap_groups(out.composition_groups, id_map)
    clamped_instruments, groups = _collapse_drum_components(clamped_instruments, groups)
    clamped_instruments, groups = _canonicalize_requested_instrument_ids(style, clamped_instruments, groups)
    clamped_instruments, groups = _normalize_guitar_items(clamped_instruments, groups)
    num_bars = _clamp_num_bars(out.num_bars)
    _validate_groups(groups, clamped_instruments)
    sections = _clamp_sections(out.sections, num_bars) or suggest_form(out.genre, num_bars)
    header = Header(
        genre=out.genre,
        key=out.key,
        tempo_bpm=out.tempo_bpm,
        time_signature=(out.time_sig_numerator, out.time_sig_denominator),
        num_bars=num_bars,
        sections=sections,
        chord_progression=_backfill_chord_progression(
            list(out.chord_progression), out.key, out.genre, num_bars, sections
        ),
    )
    roster = [
        RosterItem(
            id=i.id,
            instrument=i.instrument,
            midi_program=i.midi_program,
            midi_range=(min(i.midi_low, i.midi_high), max(i.midi_low, i.midi_high)),
            role=i.role,
            playing_style=i.playing_style,
            is_drum=i.is_drum,
        )
        for i in clamped_instruments
    ]
    return SongState(
        request=style,
        header=header,
        roster=roster,
        parts={},
        composition_groups=groups,
    )


@traceable(run_type="chain", name="director")
def run_director(style: str, llm=None) -> SongState:
    """Run the director. Pass `llm` (a chat model) to inject a fake in tests;
    otherwise a provider model is built from settings."""
    if llm is None:
        from music_assistant.infrastructure.gemini.llm import make_llm

        llm = make_llm("director")
    structured = llm.with_structured_output(DirectorOutput)
    out: DirectorOutput = structured.invoke(_prompt(style))
    if out.off_topic:
        raise OffTopicRequest(out.refusal.strip() or _DEFAULT_REFUSAL)
    return arrangement_to_song(style, out)
