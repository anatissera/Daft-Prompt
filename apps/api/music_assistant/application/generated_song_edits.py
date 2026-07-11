"""Typed structural edits for generated SongState compositions."""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field

from music_assistant.application.reference_instruments import ReferenceInstrumentProfileBuilder
from music_assistant.domain.audio_profile import ReferenceProfile
from music_assistant.domain.song_state import CompositionGroup, Note, Part, RosterItem, SongState
from music_assistant.skills.harmony import fit_to_range
from music_assistant.ports.llm import ChatModel
from music_assistant.ports.songsterr_tab_store import SongsterrTabStore


EditOperation = Literal[
    "none",
    "tone_change",
    "chord_change",
    "replace_instrument",
    "add_instrument",
    "remove_instrument",
    "rebalance",
    "regenerate_part",
    "make_more_like_reference",
]


class GeneratedSongEditIntent(BaseModel):
    operation: EditOperation = "none"
    target_families: list[str] = Field(default_factory=list)
    replacement_families: list[str] = Field(default_factory=list)
    instruction: str = ""
    preserve_unaffected_tracks: bool = True


class BuildGeneratedSongEditIntent:
    def __init__(self, *, chat_model: ChatModel | None = None) -> None:
        self.chat_model = chat_model

    def execute(self, message: str) -> GeneratedSongEditIntent:
        deterministic = _deterministic_intent(message)
        if deterministic.operation != "none" or self.chat_model is None:
            return deterministic
        try:
            structured = self.chat_model.with_structured_output(GeneratedSongEditIntent)
            result = structured.invoke([
                {
                    "role": "system",
                    "content": (
                        "Classify one generated-song edit as a typed operation. Preserve unaffected tracks. "
                        "Use replace_instrument for replacement, add_instrument/remove_instrument for roster changes, "
                        "rebalance for relative layer balance, regenerate_part for note regeneration, "
                        "make_more_like_reference for a reference transformation, and none when no edit is clear."
                    ),
                },
                {"role": "user", "content": message},
            ])
            return _validated_intent(result, message)
        except Exception:
            return deterministic


def apply_generated_song_edit(
    song: SongState,
    intent: GeneratedSongEditIntent,
    *,
    reference: ReferenceProfile | None = None,
    songsterr_tab_store: SongsterrTabStore | None = None,
) -> SongState:
    if intent.operation == "none":
        return song
    if intent.operation == "rebalance":
        return _rebalance(song, intent)
    if intent.operation == "remove_instrument":
        return _remove_families(song, intent.target_families)
    if intent.operation == "add_instrument":
        return _add_families(song, intent.replacement_families or intent.target_families, reference, songsterr_tab_store)
    if intent.operation == "replace_instrument":
        revised = _remove_families(song, intent.target_families)
        return _add_families(revised, intent.replacement_families, reference, songsterr_tab_store, force_new=True)
    return song


def _deterministic_intent(message: str) -> GeneratedSongEditIntent:
    normalized = message.lower()
    target = _families_in_text(normalized)
    replacement = _families_after_with(normalized)
    if re.search(r"\b(replace|swap|substitute|remplaz|reemplaz|sustitu)", normalized) and target and replacement:
        target_text = re.split(r"\b(?:with|using|por|con)\b", normalized, maxsplit=1)[0]
        return GeneratedSongEditIntent(
            operation="replace_instrument",
            target_families=_families_in_text(target_text),
            replacement_families=replacement,
            instruction=message,
        )
    if re.search(r"\b(add|adding|sum[aá]|agreg[aá]|a[nñ]ad)", normalized) and target:
        return GeneratedSongEditIntent(operation="add_instrument", target_families=target, replacement_families=target, instruction=message)
    if re.search(r"\b(remove|delete|drop|quit[aá]|elimin[aá]|sac[aá])", normalized) and target:
        return GeneratedSongEditIntent(operation="remove_instrument", target_families=target, instruction=message)
    if re.search(r"\b(more|less|balance|dominant|m[aá]s|menos|equilibr)", normalized) and len(target) >= 2:
        return GeneratedSongEditIntent(operation="rebalance", target_families=target, instruction=message)
    if re.search(r"\b(more like|similar to|like the song|como la canci[oó]n|parecid[oa])", normalized):
        return GeneratedSongEditIntent(operation="make_more_like_reference", target_families=target, instruction=message)
    if re.search(r"\b(regenerate|rewrite|redo|regener[aá]|rehac[eé])", normalized) and target:
        return GeneratedSongEditIntent(operation="regenerate_part", target_families=target, instruction=message)
    return GeneratedSongEditIntent(instruction=message)


def _validated_intent(intent: GeneratedSongEditIntent, message: str) -> GeneratedSongEditIntent:
    if intent.operation == "replace_instrument" and not intent.target_families:
        return _deterministic_intent(message)
    return intent.model_copy(update={"instruction": intent.instruction or message})


def _families_in_text(text: str) -> list[str]:
    aliases = {
        "drums": ("drum", "drums", "batería", "bateria"),
        "bass": ("bass", "bajo"),
        "guitar": ("guitar", "guitars", "guitarra", "guitarras"),
        "piano": ("piano", "keyboard", "keys", "teclado"),
        "synth": ("synth", "synthesizer", "pad"),
    }
    return [family for family, words in aliases.items() if any(word in text for word in words)]


def _families_after_with(text: str) -> list[str]:
    match = re.search(r"\b(?:with|using|por|con)\s+(.+)$", text)
    return _families_in_text(match.group(1)) if match else []


def _remove_families(song: SongState, families: list[str]) -> SongState:
    targets = [item.id for item in song.roster if any(_matches(item, family) for family in families)]
    if not targets:
        return song
    roster = [item for item in song.roster if item.id not in targets]
    parts = {part_id: part for part_id, part in song.parts.items() if part_id not in targets}
    groups = _groups_with_roster(song.composition_groups, roster, [])
    return song.model_copy(deep=True, update={"roster": roster, "parts": parts, "composition_groups": groups})


def _add_families(
    song: SongState,
    families: list[str],
    reference: ReferenceProfile | None,
    songsterr_tab_store: SongsterrTabStore | None,
    force_new: bool = False,
) -> SongState:
    revised = song.model_copy(deep=True)
    existing = {family for family in ["drums", "bass", "guitar", "piano", "synth"] if any(_matches(item, family) for item in revised.roster)}
    for family in dict.fromkeys(families):
        if family not in {"drums", "bass", "guitar", "piano", "synth"} or (family in existing and not force_new):
            continue
        item = _new_roster_item(family, revised.roster)
        revised.roster.append(item)
        revised.parts[item.id] = Part(
            instrument_id=item.id,
            notes=_reference_notes(family, item, revised, reference, songsterr_tab_store),
            notes_summary=f"Structural edit added {family} material from the requested reference/style.",
        )
        existing.add(family)
        revised.composition_groups = _groups_with_roster(revised.composition_groups, revised.roster, [item.id])
    return revised


def _rebalance(song: SongState, intent: GeneratedSongEditIntent) -> SongState:
    revised = song.model_copy(deep=True)
    guitar_items = [item for item in revised.roster if _matches(item, "guitar")]
    piano_items = [item for item in revised.roster if _matches(item, "piano")]
    if not guitar_items:
        revised = _add_families(revised, ["guitar"], None, None)
        guitar_items = [item for item in revised.roster if _matches(item, "guitar")]
    guitar_count = sum(len(revised.parts.get(item.id).notes) for item in guitar_items if revised.parts.get(item.id))
    for item in piano_items:
        part = revised.parts.get(item.id)
        if part is None or len(part.notes) < guitar_count:
            continue
        revised.parts[item.id] = part.model_copy(update={"notes": part.notes[: max(0, guitar_count - 1)]})
    return revised


def _new_roster_item(family: str, roster: list[RosterItem]) -> RosterItem:
    defaults = {
        "drums": ("drums", "drum_kit", 0, (35, 81), "rhythm foundation", True),
        "bass": ("bass", "electric_bass", 33, (28, 55), "low-end pulse", False),
        "guitar": ("guitar", "electric_guitar_clean", 27, (40, 84), "reference-inspired guitar", False),
        "piano": ("piano", "acoustic_piano", 0, (36, 96), "harmonic support", False),
        "synth": ("synth", "synth_pad", 89, (48, 96), "texture", False),
    }
    base, instrument, program, midi_range, role, is_drum = defaults[family]
    used = {item.id for item in roster}
    identifier = base
    suffix = 2
    while identifier in used:
        identifier = f"{base}_{suffix}"
        suffix += 1
    return RosterItem(
        id=identifier,
        instrument=instrument,
        midi_program=program,
        midi_range=midi_range,
        role=role,
        playing_style=f"Original {family} material with section-aware variation.",
        is_drum=is_drum,
    )


def _reference_notes(
    family: str,
    item: RosterItem,
    song: SongState,
    reference: ReferenceProfile | None,
    songsterr_tab_store: SongsterrTabStore | None,
) -> list[Note]:
    if reference is not None:
        profiles = ReferenceInstrumentProfileBuilder(songsterr_tab_store=songsterr_tab_store).build(reference)
        profile = profiles.get(family)
        if profile is not None:
            seeds = profile.symbolic_seed or [note for pack in profile.musical_memory.note_packs for note in pack.notes]
            if seeds:
                return [
                    Note(
                        bar=seed.bar % song.header.num_bars,
                        start_beat=seed.start_beat,
                        pitch=None if seed.pitch is None else fit_to_range(seed.pitch, *item.midi_range),
                        dur=seed.duration_beats,
                        velocity=seed.velocity,
                    )
                    for seed in seeds[: max(16, song.header.num_bars * 8)]
                ]
    if family == "drums":
        return [Note(bar=bar, start_beat=0.0, pitch=36, dur=0.25, velocity=100) for bar in range(song.header.num_bars)]
    notes: list[Note] = []
    for bar in range(song.header.num_bars):
        chord = next((span.chord for span in song.header.chord_progression if span.bar == bar), "C")
        root = _chord_root_pitch(chord, item.midi_range)
        notes.extend([
            Note(bar=bar, start_beat=0.0, pitch=root, dur=1.0, velocity=96),
            Note(bar=bar, start_beat=2.0, pitch=fit_to_range(root + 7, *item.midi_range), dur=0.5, velocity=82),
        ])
    return notes


def _chord_root_pitch(chord: str, midi_range: tuple[int, int]) -> int:
    match = re.match(r"^([A-G](?:#|b)?)", chord)
    roots = {"C": 0, "C#": 1, "Db": 1, "D": 2, "D#": 3, "Eb": 3, "E": 4, "F": 5, "F#": 6, "Gb": 6, "G": 7, "G#": 8, "Ab": 8, "A": 9, "A#": 10, "Bb": 10, "B": 11}
    pitch_class = roots.get(match.group(1) if match else "C", 0)
    return next((pitch for pitch in range(midi_range[0], midi_range[1] + 1) if pitch % 12 == pitch_class), midi_range[0])


def _matches(item: RosterItem, family: str) -> bool:
    text = f"{item.id} {item.instrument} {item.role}".lower()
    aliases = {
        "drums": ("drum", "percussion"),
        "bass": ("bass", "bajo"),
        "guitar": ("guitar", "guitarra"),
        "piano": ("piano", "keyboard", "keys", "rhodes"),
        "synth": ("synth", "pad", "supersaw"),
    }
    return (family == "drums" and item.is_drum) or any(alias in text for alias in aliases[family])


def _groups_with_roster(groups: list[CompositionGroup], roster: list[RosterItem], added_ids: list[str]) -> list[CompositionGroup]:
    roster_ids = {item.id for item in roster}
    updated = [group.model_copy(update={"instrument_ids": [iid for iid in group.instrument_ids if iid in roster_ids]}) for group in groups]
    updated = [group for group in updated if group.instrument_ids]
    missing = [item_id for item_id in roster_ids if item_id not in {iid for group in updated for iid in group.instrument_ids}]
    missing = list(dict.fromkeys([*added_ids, *missing]))
    if not updated and roster_ids:
        updated = [CompositionGroup(name="arrangement", instrument_ids=[])]
    if updated:
        ids = list(updated[0].instrument_ids)
        updated[0] = updated[0].model_copy(update={"instrument_ids": ids + [item_id for item_id in missing if item_id not in ids]})
    return updated
