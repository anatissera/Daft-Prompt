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
from ..domain.patch import (
    PATCH_SPEC,
    Patch,
    UnknownPatchError,
    is_native_synth_patch,
    reconcile_patch,
    resolve_patch,
)
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
    "I only handle music tasks: compose a short sketch, answer source-backed song questions, "
    "or work from a reference profile already researched. Try \"compose a slow blues\"."
)

MIN_ROSTER = 1
MAX_ROSTER = 8
MIN_BARS = 4
MAX_BARS = 32


class ArrangementInstrument(BaseModel):
    id: str = Field(description="short unique id, e.g. 'bass', 'lead_synth'")
    instrument: str = Field(description="human name, e.g. 'electric_bass'")
    patch: Optional[Patch] = Field(
        None,
        description=(
            "Optional semantic timbre name from the closed Patch vocabulary. "
            "When provided, the backend resolves it to midi_program and an optional synth preset. "
            "Leave null only when unsure; midi_program remains the fallback."
        ),
    )
    midi_program: int = Field(0, ge=0, le=127, description="General MIDI program")
    midi_low: int = Field(0, ge=0, le=127)
    midi_high: int = Field(127, ge=0, le=127)
    role: str = Field(min_length=1, description="this instrument's musical role in the arrangement")
    playing_style: str = Field(
        min_length=1,
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


_SYSTEM = f"""You are the musical director of an ensemble. You ONLY handle music-composition tasks. If the request is not asking you to compose a music sketch (e.g. chit-chat, trivia, coding, weather, recommendations, or writing lyrics/text only), set off_topic=true and put a short friendly message in `refusal` (in the user's language) saying you only handle music tasks and listing what you can do: compose a sketch, answer source-backed song questions, or work from a reference profile already researched. In that case leave the arrangement fields empty.

Otherwise set off_topic=false and, given a style description, produce a complete arrangement plan with the following required outputs:

1. ARRANGEMENT: key, tempo, time signature, num_bars ({MIN_BARS}-{MAX_BARS}). Reason about what genuinely fits the style.

2. SONG FORM: 3-6 named sections (e.g. Intro, Verse, PreChorus, Chorus, Bridge, Outro). Each section has start_bar, end_bar, and an energy level: "low", "medium", or "high". Sections must cover all bars 0..num_bars-1 without overlap or gap.

3. CHORD PROGRESSION: one ChordSpan per bar covering every bar (0..num_bars-1). Use chord names like "Dm7", "G7", "Cm9". Chords must fit the key and genre idiom.

4. INSTRUMENTATION: First choose the smallest ensemble capable of an authentic arrangement, then return {MIN_ROSTER}-{MAX_ROSTER} instruments. A solo or duo is valid. Silence and omitted layers are valid; never add an instrument merely because an agent is available. For each instrument:
   - When possible, set `patch` to a semantic timbre from the closed Patch vocabulary. This avoids GM-number mistakes. If `patch` is set, it is the source of truth for playback; keep `midi_program` compatible as a fallback.
   - A General MIDI program number and a sensible MIDI pitch range for that instrument in that register (e.g. bass: 28-55, not 0-127).
   - Its musical role. All percussion must be a single drum-kit roster item with is_drum=true — do NOT create separate entries for kick, snare, hi-hat, cymbals, or toms; those are MIDI pitches inside the one kit.
   - A concise stylistic justification in its role or playing_style: explain why this genre/request needs that voice. Every instrument must have a distinct purpose.
   - A playing_style: 1-2 sentences of idiomatic technique a real musician of this instrument in this genre would immediately recognise. Be specific about rhythm, articulation, and register. Examples:
     * Funk bass: "Anchor beat 1 firmly. Use ghost notes between the 2 and 4. Slap on the upbeat 16th just before beat 3 in bar-ending phrases."
     * Funk guitar: "Short 16th-note chord stabs on beats 2 and 4 with percussive muting between hits. Wah on fill bars. Stay in the mid register."
     * String pad: "Sustained whole-note pads below the melody register. Swell into the chorus. Avoid the top octave to leave room for the lead."

5. COMPOSITION GROUPS: ordered batches specifying which instruments compose in which wave. Each instrument_id must appear in exactly one group. Put rhythmic foundation first (drums, bass), harmonic layer second, melodic/textural layer last. Independent instruments in the same layer MUST share one batch: put the drum kit and bass together in the first batch unless the request explicitly makes one depend on the other. Do not create one-instrument batches merely to impose a conventional layering order; use a later batch only when it needs the earlier batch's peer summary. For a compact three-part groove, prefer exactly two batches: [drums, bass], then [lead or harmony]. Set max_negotiation_rounds (0-2) — use 1 for rhythm section, 0 for texture layers.

If the style description contains a CompositionBrief with instrument_requests, treat it as binding reference guidance:
- Keep each requested instrument family in the roster unless the request explicitly says to avoid it.
- Use the request's timbre midi_program, midi_range, and drum/percussion status when present.
- Fold pattern, transfer_mode, fidelity, and any symbolic_seed summary into playing_style so the instrument agent can apply it.
- For literal transfer, mention the seed as a starting motif/pattern, not raw tab text.
If the CompositionBrief contains playable_parts_to_preserve or preservation_requests, keep those instrument families in the roster and name the preservation constraint in role or playing_style. Do not claim perfect copying; treat source-backed tabs as exact constraints only where the brief marks them for preservation.

When `fidelity_mode` is `very_similar` or `exact_or_as_close_as_possible`, treat `reference_instrumentation_json` as a strong roster constraint: retain the source-backed instrument families and their salience (for example, guitar-led with restrained piano support). Do not replace a guitar/bass/drums reference with piano or synth filler. Avoid unsupported synths and keyboards unless the user explicitly asks for them or the evidence supports them. For `similar`, use the same evidence as a creative anchor but keep room for an original variation. `style_guardrails_json` contains non-binding quality checks, not a deterministic genre template; follow the LLM's musical judgment while avoiding obvious mismatches.

Genre compatibility is mandatory. Do not add synth leads, synth pads, electronic textures, or keyboard-like filler to grunge, punk, blues, folk, garage rock, or acoustic music unless the user explicitly requests that electronic voice. Prefer drums/bass/guitar or a still smaller idiomatic ensemble where appropriate. Do not use more instruments to make the plan look more sophisticated.

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


def _composition_prompt_context(style: str) -> tuple[str, dict, dict, str]:
    fidelity_match = re.search(r"^fidelity_mode:\s*(.+?)\s*$", style, re.MULTILINE)
    user_request_match = re.search(r"^user_request:\s*(.+?)\s*$", style, re.MULTILINE)
    instrumentation_match = re.search(r"^reference_instrumentation_json:\s*(\{.*\})\s*$", style, re.MULTILINE)
    guardrails_match = re.search(r"^style_guardrails_json:\s*(\{.*\})\s*$", style, re.MULTILINE)
    try:
        instrumentation = json.loads(instrumentation_match.group(1)) if instrumentation_match else {}
    except json.JSONDecodeError:
        instrumentation = {}
    try:
        guardrails = json.loads(guardrails_match.group(1)) if guardrails_match else {}
    except json.JSONDecodeError:
        guardrails = {}
    return (
        fidelity_match.group(1).strip() if fidelity_match else "similar",
        instrumentation if isinstance(instrumentation, dict) else {},
        guardrails if isinstance(guardrails, dict) else {},
        user_request_match.group(1).strip() if user_request_match else style,
    )


def _reference_families(instrumentation: dict) -> tuple[set[str], dict[str, bool]]:
    families: set[str] = set()
    salient: dict[str, bool] = {}
    for item in instrumentation.values():
        if not isinstance(item, dict):
            continue
        families.update(str(family) for family in item.get("families", []) if family)
        salience = item.get("salience")
        if isinstance(salience, dict):
            for family, enabled in {
                "guitar": salience.get("guitar_led"),
                "piano": salience.get("piano_support"),
                "synth": salience.get("synth_supported"),
            }.items():
                if enabled:
                    salient[family] = True
    return families, salient


def _fallback_arrangement_item(family: str) -> ArrangementInstrument | None:
    defaults = {
        "drums": ("drums", "drum_kit", 0, 35, 81, "rhythm foundation", True),
        "bass": ("bass", "electric_bass", 33, 28, 55, "low-end pulse", False),
        "guitar": ("rhythm_guitar", "electric_guitar_clean", 27, 40, 84, "source-backed guitar role", False),
        "piano": ("piano", "acoustic_piano", 0, 36, 96, "restrained harmonic support", False),
        "synth": ("synth", "synth_pad", 89, 48, 96, "source-supported electronic texture", False),
    }
    values = defaults.get(family)
    if values is None:
        return None
    instrument_id, instrument, program, low, high, role, is_drum = values
    return ArrangementInstrument(
        id=instrument_id,
        instrument=instrument,
        midi_program=program,
        midi_low=low,
        midi_high=high,
        role=role,
        playing_style=f"Evidence-guided {family} role; vary phrases by section and leave space for the ensemble.",
        is_drum=is_drum,
    )


def _enforce_reference_instrumentation(
    style: str,
    items: list[ArrangementInstrument],
    groups: list[CompositionGroup],
) -> tuple[list[ArrangementInstrument], list[CompositionGroup]]:
    fidelity, instrumentation, guardrails, user_request = _composition_prompt_context(style)
    reference_families, salient = _reference_families(instrumentation)
    if not reference_families and not guardrails:
        return items, groups
    explicit = {
        family
        for family, aliases in {
            "piano": ["piano", "keyboard", "keys"],
            "synth": ["synth", "synthesizer", "pad"],
            "guitar": ["guitar"],
            "bass": ["bass"],
            "drums": ["drum", "drums"],
        }.items()
        if any(alias in user_request.lower() for alias in aliases)
    }
    existing = {family for family in ["drums", "bass", "guitar", "piano", "synth"] if any(_arrangement_item_matches_family(item, family) for item in items)}
    required = set(reference_families)
    if fidelity == "similar":
        required = {family for family in required if family not in {"piano", "synth"} or salient.get(family, False)}
    required.update(family for family in guardrails.get("expected_families", []) if family in {"drums", "bass", "guitar"})
    missing = [family for family in ["drums", "bass", "guitar", "piano", "synth"] if family in required and family not in existing]
    updated = list(items)
    used_ids = {item.id for item in updated}
    added_ids: list[str] = []
    for family in missing:
        fallback = _fallback_arrangement_item(family)
        if fallback is None:
            continue
        fallback = fallback.model_copy(update={"id": _unique_id(fallback.id, used_ids)})
        used_ids.add(fallback.id)
        updated.append(fallback)
        added_ids.append(fallback.id)

    forbidden = {"synth"} if "synth_default" in guardrails.get("discouraged_families", []) else set()
    if "unsupported_synth" in guardrails.get("discouraged_families", []) and "synth" not in reference_families:
        forbidden.add("synth")
    if "piano_heavy_balance" in guardrails.get("discouraged_families", []) and "piano" not in reference_families:
        forbidden.add("piano")
    removable = {
        item.id
        for item in updated
        if any(
            _arrangement_item_matches_family(item, family)
            and family not in explicit
            and family not in reference_families
            for family in forbidden
        )
    }
    if removable and len(updated) > len(removable):
        updated = [item for item in updated if item.id not in removable]

    if added_ids or removable:
        filtered_groups = [
            group.model_copy(update={"instrument_ids": [iid for iid in group.instrument_ids if iid not in removable]})
            for group in groups
        ]
        filtered_groups = [group for group in filtered_groups if group.instrument_ids]
        if not filtered_groups and updated:
            filtered_groups = [CompositionGroup(name="rhythm", instrument_ids=[])]
        if filtered_groups:
            ids = list(filtered_groups[0].instrument_ids)
            filtered_groups[0] = filtered_groups[0].model_copy(update={"instrument_ids": ids + [iid for iid in added_ids if iid not in ids]})
        groups = filtered_groups
    return updated, groups


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


_ROOTS_GENRE_RE = re.compile(r"\b(grunge|punk|blues|folk|garage(?:\s+rock)?|acoustic)\b", re.IGNORECASE)
_EXPLICIT_ELECTRONIC_RE = re.compile(r"\b(synth|synthesizer|electronic|pad|keyboard|keys)\b", re.IGNORECASE)


def _remove_unrequested_electronic_textures(
    style: str,
    items: list[ArrangementInstrument],
    groups: list[CompositionGroup],
) -> tuple[list[ArrangementInstrument], list[CompositionGroup]]:
    if not _ROOTS_GENRE_RE.search(style) or _EXPLICIT_ELECTRONIC_RE.search(style):
        return items, groups
    removable = {
        item.id
        for item in items
        if 80 <= item.midi_program <= 103
        or _is_electronic_patch(item.patch)
        or _EXPLICIT_ELECTRONIC_RE.search(f"{item.id} {item.instrument} {item.role}")
    }
    kept = [item for item in items if item.id not in removable]
    if not kept:
        return items, groups
    filtered_groups = [
        group.model_copy(update={"instrument_ids": [iid for iid in group.instrument_ids if iid not in removable]})
        for group in groups
    ]
    return kept, [group for group in filtered_groups if group.instrument_ids]


def _is_electronic_patch(patch: Patch | None) -> bool:
    if patch is None:
        return False
    value = str(patch)
    if is_native_synth_patch(value):
        return True
    spec = PATCH_SPEC.get(value)
    if not spec:
        return False
    return value.startswith("gm_") and any(token in value for token in ("lead", "pad", "synth", "fx"))


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
    clamped_instruments, groups = _enforce_reference_instrumentation(style, clamped_instruments, groups)
    clamped_instruments, groups = _normalize_guitar_items(clamped_instruments, groups)
    clamped_instruments, groups = _remove_unrequested_electronic_textures(style, clamped_instruments, groups)
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
        _roster_item_from_arrangement(i)
        for i in clamped_instruments
    ]
    return SongState(
        request=style,
        header=header,
        roster=roster,
        parts={},
        composition_groups=groups,
    )


def _roster_item_from_arrangement(item: ArrangementInstrument) -> RosterItem:
    patch = reconcile_patch(item.instrument, str(item.patch)) if item.patch else None
    midi_program = item.midi_program
    synth_preset = None
    if patch:
        try:
            midi_program, synth_preset = resolve_patch(patch)
        except UnknownPatchError:
            patch = None
            synth_preset = None
            midi_program = item.midi_program
    return RosterItem(
        id=item.id,
        instrument=item.instrument,
        patch=patch,
        midi_program=midi_program,
        midi_range=(min(item.midi_low, item.midi_high), max(item.midi_low, item.midi_high)),
        role=item.role,
        playing_style=item.playing_style,
        is_drum=item.is_drum,
        synth_preset=synth_preset,
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
