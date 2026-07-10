"""Director agent — reasons an arrangement (header + roster) from a style string.

This is the first LLM node. It does NOT compose notes (that's the instrument agents);
it decides key/tempo/meter/form, chord progression, per-instrument playing style, and
the ordered composition groups that control layering order.
"""

from __future__ import annotations

import re
from typing import Literal, Optional

from langsmith import traceable
from pydantic import BaseModel, Field

from ..corpus.retrieve import LakhExample, retrieve_style_examples
from ..domain.audio_profile import ReferenceProfile
from ..domain.errors import OffTopicRequest
from ..domain.patch import PATCH_SPEC, Patch, UnknownPatchError, resolve_patch
from ..domain.song_state import (
    ChordSpan,
    CompositionGroup,
    Header,
    RosterItem,
    Section,
    SongState,
)

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
    # `instrument` used to be a free-text field alongside `patch`, and the LLM
    # kept desynchronising them (instrument='electric_guitar' + patch=
    # 'electric_grand_piano', instrument='synth_lead' + patch='soprano_sax').
    # The two carried the same signal so we dropped the free field: `patch`
    # from the closed vocab is now the single source of truth for the sound
    # AND the display name. Drums use `is_drum=True` with patch=None.
    # `patch` replaces the old (midi_program, synth_preset) pair. The LLM used
    # to memorise the 128-entry GM table and slip constantly ("Strings 1" →
    # program 101 which is FX 6 Goblins). Now the LLM picks a semantic name
    # from a closed vocabulary and the backend deterministically maps it to a
    # sampler patch or a Tone.js synth preset. There is no way to slip.
    patch: Optional[Patch] = Field(
        None,
        description=(
            "Semantic timbre for this instrument. Pick the one CLOSEST to the "
            "sound you want. Naming reflects the sound, not the GM number.\n"
            "Guitar family: 'distortion_guitar' (metal/hard-rock rhythm+lead), "
            "'overdriven_guitar' (crunchy rock), 'clean_electric_guitar' "
            "(clean Strat/Tele), 'muted_electric_guitar' (short-decay muted, "
            "NOT palm-muted-with-distortion), 'jazz_electric_guitar' (hollow-"
            "body clean), 'acoustic_guitar_steel', 'acoustic_guitar_nylon'.\n"
            "Bass: 'electric_bass' (finger), 'pick_bass', 'fretless_bass', "
            "'slap_bass', 'acoustic_bass', 'sub_bass' (synth 808/sine sub).\n"
            "Piano/keys: 'acoustic_grand_piano', 'bright_acoustic_piano', "
            "'honky_tonk_piano', 'electric_piano_rhodes', 'electric_piano_dx', "
            "'harpsichord', 'clavinet'.\n"
            "Organ: 'hammond_organ', 'rock_organ', 'church_organ'.\n"
            "Solo strings: 'violin', 'viola', 'cello', 'contrabass'.\n"
            "Section strings/choir: 'string_ensemble' (sustained orchestral "
            "strings), 'tremolo_strings', 'pizzicato_strings', 'choir_aahs', "
            "'voice_oohs'.\n"
            "Brass: 'trumpet', 'trombone', 'french_horn', 'tuba', "
            "'muted_trumpet', 'brass_section'.\n"
            "Reed / winds: 'alto_sax', 'tenor_sax', 'soprano_sax', "
            "'baritone_sax', 'clarinet', 'oboe', 'flute', 'piccolo', "
            "'pan_flute'.\n"
            "Chromatic perc: 'marimba', 'vibraphone', 'xylophone', "
            "'glockenspiel', 'music_box', 'celesta', 'tubular_bells'.\n"
            "Ethnic: 'sitar', 'banjo', 'kalimba', 'steel_drums'.\n"
            "Modern EDM synths (Tone.js native, NOT GM samples): "
            "'supersaw_lead' (detuned saw lead / hoover), 'sub_bass' (sine "
            "sub 808), 'pluck' (short staccato synth pluck / arp), "
            "'warm_pad' (sustained slow-attack pad), 'vocal_fx' (chopped "
            "pitched vocal fragments). Use these for EDM, future bass, trap, "
            "synthwave, house — they sound modern; GM synth patches sound "
            "8-bit.\n"
            "Leave null ONLY if the drum kit (set is_drum=true instead) — "
            "otherwise a null or unrecognised name causes the instrument to "
            "be DROPPED from the roster (there is no piano fallback anymore, "
            "so a slip means fewer instruments, not a mystery piano).\n"
            "IMPORTANT anti-bias note: do NOT default to a piano patch for a "
            "harmony / comping role. Piano fits jazz, ballads, pop, gospel, "
            "singer-songwriter; for rock, metal, punk, funk, EDM, hip-hop, "
            "reggae, country, salsa, cumbia, R&B etc. the harmony/comping "
            "role is a guitar, organ, Rhodes, brass section, synth pad, or "
            "similar — never grand piano. Pick piano only when a musician "
            "who plays this genre would say 'that's a piano song'."
        ),
    )
    role: str = Field(description="this instrument's musical role in the arrangement")
    fits_style: str = Field(
        "",
        description=(
            "One sentence justifying why THIS specific patch appears on typical "
            "records of the requested style. Name the mechanism ('drives the "
            "riff', 'anchors the low end', 'provides the shimmer over the "
            "chorus'), not a generic 'fits the genre'. If you cannot write "
            "this sentence honestly, you picked the wrong patch — swap it "
            "before finalising. Empty only for is_drum=true items."
        ),
    )
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
    # Structured chain-of-thought slot. The model must first commit to the
    # canonical instrumentation / tempo / mood of the requested style BEFORE
    # picking chords or a roster. This is emitted first in the JSON so the
    # generation is autoregressively conditioned on it: whatever roster it
    # writes downstream has to line up with what it just claimed is
    # idiomatic. Empty when off_topic.
    style_analysis: str = Field(
        "",
        description=(
            "2-4 sentences committing to the CANONICAL instrumentation, tempo range, "
            "key/mode tendency, and mood of the requested style — the way a musician "
            "who plays this genre every day would describe it. Be concrete about "
            "which instrument families actually appear on records of this style "
            "(and which ones would sound out of place). This field is a commitment: "
            "your later `instruments` roster must line up with it. Empty only when "
            "off_topic=true."
        ),
    )
    canonical_instruments: list[str] = Field(
        default_factory=list,
        description=(
            "Concrete list (3-8 entries) of the instrument families that would "
            "appear on a typical record of this style, e.g. "
            "['distortion guitar', 'bass guitar', 'drum kit', 'lead vocals'] "
            "for dark metal, or ['acoustic piano', 'upright bass', 'brush "
            "drums', 'tenor sax'] for a jazz ballad. Fill this AFTER "
            "style_analysis and BEFORE picking `instruments`. The patches you "
            "choose downstream must each be an obvious realisation of one of "
            "these families — if you find yourself picking a patch that is "
            "not on this list, either add it here (only if it honestly "
            "belongs on canonical records) or drop it. Empty only when "
            "off_topic=true."
        ),
    )
    rhythmic_feel: str = Field(
        "",
        description=(
            "3-6 sentences committing to the RHYTHMIC IDIOM of the requested "
            "style — the concrete groove skeleton the per-instrument agents "
            "will follow. Be specific per role: where the kick and snare sit "
            "(e.g. 'half-time: snare on beat 3, kicks on 1 and the offbeat "
            "of 3, hats in straight 16ths with accents on the -a of every "
            "beat'), what subdivision the bass articulates ('sub bass in "
            "sustained 8ths with pitch-drops at the top of every 2 bars'), "
            "how the harmony instruments phrase ('supersaw plays syncopated "
            "16th stabs on the offbeats, never on the downbeat'), and any "
            "signature feel like swing %, halftime, shuffle, four-on-the-"
            "floor, laid-back, or rushing. Do NOT default to a generic "
            "quarter-note pop feel. This field is a commitment: every "
            "per-instrument agent will read it and compose notes that fit "
            "it. Empty only when off_topic=true."
        ),
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

Otherwise set off_topic=false and, given a style description, produce a complete arrangement plan with the following required outputs.

Before anything else, fill `style_analysis` with 2-4 sentences committing to the canonical instrumentation, tempo range, key/mode tendency, and mood of the requested style. Be concrete about which instrument families actually appear on records of this genre (and which ones would sound out of place). Everything you emit afterwards MUST be consistent with what you just committed to here — do not pick a roster that contradicts your own analysis.

Then fill `canonical_instruments`: a concrete 3-8 item list of the instrument families that would honestly appear on a typical record of this style (e.g. dark metal → ['distortion guitar', 'bass guitar', 'drum kit', 'lead vocals']; jazz ballad → ['acoustic piano', 'upright bass', 'brush drums', 'tenor sax']). This is your working shortlist. Every patch you pick later must be an obvious realisation of an entry on this list — a `distortion_guitar` patch realises 'distortion guitar', a `string_ensemble` patch does NOT realise 'distortion guitar'. If a patch you want isn't covered here, either add its family to the list (only if it honestly belongs on canonical records of the style) or don't pick it.

Then fill `rhythmic_feel`: 3-6 sentences committing to the CONCRETE groove of this style. This is what the per-instrument agents will read to compose their notes. Be specific per role: kick/snare placement, hat subdivision, bass articulation, harmony phrasing, and any signature feel (half-time, swung, four-on-the-floor, laid-back, syncopated, on-top). Examples of the level of detail expected: 'Dubstep half-time: kick on 1 and 3.5, snare exactly on 3, hats in 16ths with accents on every -a; sub bass sustained across each bar with an octave-drop pickup on bar 4; supersaw stabs on the 2-and-3-and of every bar, never on downbeats; drop hits on bar 5 and 13.' Do NOT default to generic pop quarter-notes. A weak rhythmic_feel makes the arrangement sound like a chorale regardless of the roster you picked.

1. ARRANGEMENT: key, tempo, time signature, num_bars ({MIN_BARS}-{MAX_BARS}). Reason about what genuinely fits the style.

2. SONG FORM: 3-6 named sections (e.g. Intro, Verse, PreChorus, Chorus, Bridge, Outro). Each section has start_bar, end_bar, and an energy level: "low", "medium", or "high". Sections must cover all bars 0..num_bars-1 without overlap or gap.

3. CHORD PROGRESSION: one ChordSpan per bar covering every bar (0..num_bars-1). Use chord names like "Dm7", "G7", "Cm9". Chords must fit the key and genre idiom.

4. INSTRUMENTATION: {MIN_ROSTER}-{MAX_ROSTER} instruments. For each instrument:
   - A `patch` chosen from the closed vocabulary (see the field description on ArrangementInstrument.patch). The patch IS the instrument's identity — its value (e.g. 'distortion_guitar', 'electric_bass', 'warm_pad') is what the audience will hear AND how the instrument will be labelled downstream. Do NOT pick a patch that contradicts the role you have in mind: if you want a rock rhythm guitar, the patch must be a guitar-family value (`distortion_guitar`, `overdriven_guitar`, `clean_electric_guitar`, …), never a piano or a sax. Cross-check every patch against `canonical_instruments` and `style_analysis` before finalising.
   - Its musical role. All percussion must be a single drum-kit roster item with is_drum=true — do NOT create separate entries for kick, snare, hi-hat, cymbals, or toms; those are MIDI pitches inside the one kit.
   - A `fits_style` sentence naming the concrete mechanism by which THIS patch fits the requested style ("drives the main riff with palm-muted power chords", "carries the low-end pulse alongside the kick"). This is a self-check: if you cannot write a specific, honest sentence, you picked the wrong patch. A generic "fits the genre" is not acceptable.
   - A playing_style: 1-2 sentences of idiomatic technique a real musician of this instrument in this genre would immediately recognise. Be specific about rhythm, articulation, and register. Examples:
     * Funk bass: "Anchor beat 1 firmly. Use ghost notes between the 2 and 4. Slap on the upbeat 16th just before beat 3 in bar-ending phrases."
     * Funk guitar: "Short 16th-note chord stabs on beats 2 and 4 with percussive muting between hits. Wah on fill bars. Stay in the mid register."
     * String pad: "Sustained whole-note pads below the melody register. Swell into the chorus. Avoid the top octave to leave room for the lead."
   - (No separate synth_preset field — modern EDM archetypes are patch values like 'supersaw_lead', 'sub_bass', 'pluck', 'warm_pad', 'vocal_fx'. Choose them for EDM / future bass / trap / synthwave / house; use acoustic-family patch names for everything else.)

5. COMPOSITION GROUPS: ordered batches specifying which instruments compose in which wave. Each instrument_id must appear in exactly one group. Put rhythmic foundation first (drums, bass), harmonic layer second, melodic/textural layer last. Set max_negotiation_rounds (0-2) — use 1 for rhythm section, 0 for texture layers.

Do not use a fixed genre-to-instrument mapping. Reason about what genuinely fits the requested style."""


def _style_card(examples: list[LakhExample]) -> str:
    """Compact formatting of retrieved corpus exemplars for injection into the
    Director prompt. Guidance only — the Director still emits its own final
    arrangement. When `examples` is empty (no corpus present), returns "" so
    the prompt is unchanged from today's behaviour.

    We deliberately inject only progression + key + tempo. The corpus also
    carries per-segment role tags (bass/drums/reed/ensemble/…) but those bled
    generic-genre instrumentation into specific requests (rock metal → violin
    because a "rock" Lakh segment happened to include a string ensemble).
    Instrumentation is left entirely to the director's own reasoning plus the
    web-research card, which carry better signal for artist/style idiom."""
    if not examples:
        return ""
    lines = ["Canonical progressions for this style (guidance, not override):"]
    for i, ex in enumerate(examples, 1):
        prog = " | ".join(ex.progression) if ex.progression else "(none)"
        lines.append(f"  {i}. key={ex.key}, tempo={ex.tempo:.0f}, progression: {prog}")
    lines.append(
        "Use these as reference for progression idiom only. "
        "Do not copy verbatim; adapt to the requested style. "
        "Instrumentation is your own call — do not derive it from these examples."
    )
    return "\n".join(lines)


def _research_card(profile: ReferenceProfile | None) -> str:
    """Compact formatting of web-research findings (tempo, key, per-site claims)
    for injection into the Director prompt. Empty when the researcher returned
    nothing usable, so the prompt is unchanged from today's behaviour."""
    if profile is None or not profile.research_evidence:
        return ""
    lines = ["Web research on the requested style (evidence, not override):"]
    audio = profile.audio
    if audio is not None:
        if audio.tempo_bpm:
            lines.append(f"  fused tempo ≈ {audio.tempo_bpm:g} BPM")
        if audio.key:
            lines.append(f"  fused key ≈ {audio.key}")
    for ev in profile.research_evidence[:6]:
        snippet = ev.snippet.replace("\n", " ").strip()
        if len(snippet) > 140:
            snippet = snippet[:137] + "…"
        lines.append(f"  [{ev.site}] {ev.claim_type}={ev.value}  — {snippet}")
    lines.append(
        "Use this as background on the artist/song idiom. "
        "Adapt to the requested style; do not overfit to any single source."
    )
    return "\n".join(lines)


def _prompt(
    style: str,
    examples: list[LakhExample],
    research: ReferenceProfile | None = None,
) -> list[tuple[str, str]]:
    messages: list[tuple[str, str]] = [("system", _SYSTEM)]
    research_card = _research_card(research)
    if research_card:
        messages.append(("human", research_card))
    card = _style_card(examples)
    if card:
        messages.append(("human", card))
    messages.append(("human", f"Style: {style}"))
    return messages


_ID_SAFE_RE = re.compile(r"[^a-z0-9]+")
_ID_TRAILING_NUM_RE = re.compile(r"^(.*?)_?(\d+)$")


def _slug(value: str, fallback: str) -> str:
    cleaned = _ID_SAFE_RE.sub("_", (value or "").strip().lower()).strip("_")
    return cleaned or fallback


def _canonical_id(value: str) -> str:
    """Collapse zero-padded numeric suffixes so `inst_09` and `inst_9` match.
    The director LLM inconsistently pads roster ids vs the ids it emits inside
    composition_groups; normalising here lets `_remap_groups` reconcile them."""
    slug = _slug(value, "")
    m = _ID_TRAILING_NUM_RE.match(slug)
    if not m:
        return slug
    prefix, num = m.groups()
    return f"{prefix}_{int(num)}" if prefix else str(int(num))


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
        base = _slug(item.id, "") or _slug(str(item.patch or ""), "") or _slug(item.role, "") or f"agent_{idx}"
        candidate = base
        suffix = 2
        while candidate in seen:
            candidate = f"{base}_{suffix}"
            suffix += 1
        seen.add(candidate)
        repaired.append(item.model_copy(update={"id": candidate}))
        id_map.setdefault(item.id, candidate)  # first occurrence wins
        id_map.setdefault(_canonical_id(item.id), candidate)
        id_map.setdefault(_canonical_id(candidate), candidate)
    return repaired, id_map


def _remap_groups(
    groups: list[CompositionGroup], id_map: dict[str, str]
) -> list[CompositionGroup]:
    def lookup(iid: str) -> str:
        return id_map.get(iid) or id_map.get(_canonical_id(iid)) or iid

    return [
        group.model_copy(
            update={"instrument_ids": [lookup(iid) for iid in group.instrument_ids]}
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
        patch=None,  # drums route via is_drum=True, no patch lookup
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


def arrangement_to_song(style: str, out: DirectorOutput) -> SongState:
    clamped_instruments, id_map = _repair_roster_ids(_clamp_roster(out.instruments))
    groups = _remap_groups(out.composition_groups, id_map)
    clamped_instruments, groups = _collapse_drum_components(clamped_instruments, groups)
    num_bars = _clamp_num_bars(out.num_bars)
    _validate_groups(groups, clamped_instruments)
    header = Header(
        genre=out.genre,
        key=out.key,
        tempo_bpm=out.tempo_bpm,
        time_signature=(out.time_sig_numerator, out.time_sig_denominator),
        num_bars=num_bars,
        sections=_clamp_sections(out.sections, num_bars),
        chord_progression=list(out.chord_progression),
        rhythmic_feel=out.rhythmic_feel,
    )
    roster = []
    dropped_ids: set[str] = set()
    for i in clamped_instruments:
        # Derive numeric fields from the semantic patch. Drums bypass the
        # lookup and keep the mapping empty — playback uses the fixed
        # channel-10 percussion map instead of a program.
        if i.is_drum:
            program, preset = 0, None
            patch = None
            display = "drum_kit"
        else:
            # DROP instead of silently substituting grand piano. The old
            # `i.patch or "acoustic_grand_piano"` fallback quietly turned
            # every null/typo patch into a piano, which produced a piano
            # bias across genres where the director slipped on the vocab.
            if not i.patch:
                dropped_ids.add(i.id)
                continue
            try:
                program, preset = resolve_patch(i.patch)
            except UnknownPatchError:
                dropped_ids.add(i.id)
                continue
            patch = i.patch
            display = str(i.patch)
        roster.append(
            RosterItem(
                id=i.id,
                instrument=display,
                patch=patch,
                midi_program=program,
                synth_preset=preset,
                role=i.role,
                playing_style=i.playing_style,
                is_drum=i.is_drum,
            )
        )
    # Prune any composition-group references to instruments we dropped so
    # downstream `_validate_groups`-style checks stay consistent.
    if dropped_ids:
        groups = [
            g.model_copy(update={
                "instrument_ids": [iid for iid in g.instrument_ids if iid not in dropped_ids]
            })
            for g in groups
        ]
        groups = [g for g in groups if g.instrument_ids]
    return SongState(
        request=style,
        header=header,
        roster=roster,
        parts={},
        composition_groups=groups,
    )


def _research_style(query: str, *, timeout_seconds: float) -> ReferenceProfile | None:
    """Run the web researcher on the compose prompt with a hard time budget.

    Style prompts often name an artist or song ("como los Beatles", "tipo Radiohead");
    a quick DDG-backed lookup surfaces tempo/key/idiom evidence the director can lean
    on. Always safe: any failure or timeout returns None and the prompt falls back to
    LLM parametric knowledge.
    """
    from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout

    from ..infrastructure.web_research.researcher import DefaultSongResearcher

    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(DefaultSongResearcher().research, query)
            return future.result(timeout=timeout_seconds)
    except (FuturesTimeout, Exception):
        return None


class _CritiqueSwap(BaseModel):
    instrument_id: str = Field(description="id of the instrument being reviewed")
    verdict: Literal["keep", "replace"] = Field(
        description="'keep' if the patch fits the style, 'replace' if it doesn't"
    )
    new_patch: Optional[Patch] = Field(
        None,
        description=(
            "REQUIRED when verdict='replace'. A patch from the same closed "
            "vocabulary that a musician of the requested genre would honestly "
            "put on this record for this role. Do not swap patches for cosmetic "
            "reasons — only when the current pick would sound out of place."
        ),
    )
    reason: str = Field(
        "",
        description=(
            "One sentence naming the concrete idiomatic mismatch (e.g. 'string "
            "ensemble as harmony layer does not appear on typical dark-metal "
            "records; rock organ or another distorted guitar is the honest "
            "swap'). Empty for verdict='keep'."
        ),
    )


class RosterCritique(BaseModel):
    swaps: list[_CritiqueSwap] = Field(
        default_factory=list,
        description=(
            "One entry per instrument in the current roster. Most entries "
            "should be 'keep' — only mark 'replace' when the patch clearly "
            "would not appear on canonical records of the requested style."
        ),
    )


_CRITIC_SYSTEM = """You are a senior music producer reviewing another director's instrument choices for a specific style. You will get:
  - the requested style
  - the director's own style_analysis and canonical_instruments (their commitment)
  - the roster they picked (id, patch, role, fits_style)

Your job is to catch instruments that would not honestly appear on canonical records of the requested style — the kind of mismatch a working musician of that genre would immediately flag ('there is no string ensemble on a dark-metal record', 'a grand piano would not be the harmony layer on a reggaeton track').

For each instrument in the roster, emit one entry with verdict='keep' or 'replace'. When 'replace', propose a new_patch from the same closed vocabulary that fits the role AND the style. Be conservative: only replace when the mismatch is real. If the roster is already fine, return all 'keep'.

Do NOT change roles or ids — just patches."""


def _critique_roster(
    style: str,
    out: DirectorOutput,
    llm,
) -> RosterCritique | None:
    """Second-pass review of the director's roster. Returns None on any
    failure — never blocks the compose flow. Skips drums (their patch is
    None and their identity is fixed)."""
    reviewable = [
        {"id": i.id, "patch": i.patch, "role": i.role, "fits_style": i.fits_style}
        for i in out.instruments
        if not i.is_drum and i.patch
    ]
    if not reviewable:
        return None
    try:
        structured = llm.with_structured_output(RosterCritique)
        payload = (
            f"Requested style: {style}\n\n"
            f"Director's style_analysis: {out.style_analysis}\n\n"
            f"Director's canonical_instruments: {out.canonical_instruments}\n\n"
            f"Roster to review:\n{reviewable}"
        )
        critique = structured.invoke([("system", _CRITIC_SYSTEM), ("human", payload)])
        # Some models (and test fakes) answer with whatever schema they feel
        # like; only a real RosterCritique is usable downstream.
        if not isinstance(critique, RosterCritique):
            return None
        return critique
    except Exception:
        return None


def _apply_swaps(out: DirectorOutput, critique: RosterCritique) -> tuple[DirectorOutput, list[tuple[str, str, str]]]:
    """Apply the critic's 'replace' verdicts to the director output. Returns
    the mutated output plus a log of (instrument_id, from_patch, to_patch) so
    the trace can record what changed."""
    swaps_by_id = {
        s.instrument_id: s
        for s in critique.swaps
        if s.verdict == "replace" and s.new_patch
    }
    if not swaps_by_id:
        return out, []
    log: list[tuple[str, str, str]] = []
    new_instruments: list[ArrangementInstrument] = []
    for inst in out.instruments:
        swap = swaps_by_id.get(inst.id)
        if swap and swap.new_patch and inst.patch != swap.new_patch:
            log.append((inst.id, str(inst.patch), str(swap.new_patch)))
            new_instruments.append(inst.model_copy(update={"patch": swap.new_patch}))
        else:
            new_instruments.append(inst)
    return out.model_copy(update={"instruments": new_instruments}), log


@traceable(run_type="chain", name="director")
def run_director(style: str, llm=None, *, trace=None) -> SongState:
    """Run the director. Pass `llm` (a chat model) to inject a fake in tests;
    otherwise a provider model is built from settings. Pass `trace` (a
    :class:`RunTrace`) to persist an audit record of the director's input and
    output — the trace is optional so tests and older callers keep working."""
    if llm is None:
        from music_assistant.infrastructure.gemini.llm import make_llm

        llm = make_llm("director")
    structured = llm.with_structured_output(DirectorOutput)
    try:
        examples = retrieve_style_examples(style, energy="medium", n=3)
    except Exception:
        examples = []
    research = _research_style(style, timeout_seconds=15.0)
    messages = _prompt(style, examples, research)
    out: DirectorOutput = structured.invoke(messages)
    if out.off_topic:
        if trace is not None:
            trace.write_director(
                prompt_messages=messages,
                corpus_examples=examples,
                research=research,
                output=out,
            )
        raise OffTopicRequest(out.refusal.strip() or _DEFAULT_REFUSAL)
    # Critic pass — reviews the roster against the director's own
    # style_analysis/canonical_instruments and swaps out patches that a
    # musician of the requested style would not honestly put on the record.
    # Any failure is silently ignored: the original roster still ships.
    critique = _critique_roster(style, out, llm)
    swap_log: list[tuple[str, str, str]] = []
    if critique is not None:
        out, swap_log = _apply_swaps(out, critique)
    if swap_log:
        import logging
        logging.getLogger(__name__).info(
            "director critic swapped %d instrument(s): %s",
            len(swap_log),
            ", ".join(f"{iid}: {frm}→{to}" for iid, frm, to in swap_log),
        )
    if trace is not None:
        trace.write_director(
            prompt_messages=messages,
            corpus_examples=examples,
            research=research,
            output=out,
        )
    return arrangement_to_song(style, out)
