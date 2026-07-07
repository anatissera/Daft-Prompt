"""Materialize literal reference note packs into SongState parts."""

from __future__ import annotations

import json
import re
from typing import Any

from music_assistant.domain.song_state import Header, Note, Part, RosterItem
from music_assistant.skills.harmony import fit_to_range


_NOTE_PACK_REGISTRY: dict[tuple[str, str], dict[str, Any]] = {}


def register_literal_note_pack(
    *,
    reference_id: str,
    note_pack_id: str,
    note_pack: dict[str, Any],
) -> None:
    if not note_pack_id:
        return
    _NOTE_PACK_REGISTRY[(reference_id, note_pack_id)] = note_pack


def literal_parts_from_request(
    request_text: str,
    header: Header,
    roster: list[RosterItem],
    *,
    include_warnings: bool = False,
) -> dict[str, Part] | tuple[dict[str, Part], list[str]]:
    instrument_requests = _instrument_requests_from_text(request_text)
    if not instrument_requests:
        return ({}, []) if include_warnings else {}
    parts: dict[str, Part] = {}
    warnings: list[str] = []
    for family, payload in instrument_requests.items():
        if not payload.get("literal_application"):
            continue
        note_pack = _note_pack_for_payload(payload)
        if not isinstance(note_pack, dict):
            warnings.append(f"literal {family} requested but no note pack is available")
            continue
        roster_item = _roster_for_family(family, roster)
        if roster_item is None:
            warnings.append(f"literal {family} requested but no {family} roster item was produced")
            continue
        mode = str(payload.get("literal_mode") or "literal_loop")
        notes = (
            _timeline_note_pack(note_pack, header, roster_item)
            if mode == "literal_timeline"
            else _tile_note_pack(note_pack, header, roster_item)
        )
        if not notes:
            if mode == "literal_timeline":
                warnings.append(f"literal {family} requested but note pack is outside the generated timeline")
            else:
                warnings.append(f"literal {family} requested but note pack produced no notes")
            continue
        pack_id = str(payload.get("note_pack_id") or note_pack.get("pack_id") or "reference")
        summary_mode = "timeline-aligned" if mode == "literal_timeline" else "tiled/truncated"
        parts[roster_item.id] = Part(
            instrument_id=roster_item.id,
            notes=notes,
            notes_summary=f"literal reference pack {pack_id}, {summary_mode} to {header.num_bars} bars",
            self_notes=f"reference_literal:{pack_id}",
        )
    return (parts, warnings) if include_warnings else parts


def _note_pack_for_payload(payload: dict[str, Any]) -> dict[str, Any] | None:
    inline = payload.get("note_pack")
    if isinstance(inline, dict):
        return inline
    note_pack_id = str(payload.get("note_pack_id") or "")
    intent = payload.get("intent")
    reference_id = ""
    if isinstance(intent, dict):
        reference_id = str(intent.get("reference_id") or "")
    if not note_pack_id:
        return None
    return _NOTE_PACK_REGISTRY.get((reference_id, note_pack_id)) or _NOTE_PACK_REGISTRY.get(("", note_pack_id))


def _instrument_requests_from_text(request_text: str) -> dict[str, Any]:
    match = re.search(r"^instrument_requests_json:\s*(\{.*\})\s*$", request_text, re.MULTILINE)
    if not match:
        return {}
    try:
        parsed = json.loads(match.group(1))
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _roster_for_family(family: str, roster: list[RosterItem]) -> RosterItem | None:
    normalized = family.lower()
    for item in roster:
        if normalized == "drums" and item.is_drum:
            return item
        if _roster_item_matches_family(item, normalized):
            return item
    return None


def _roster_item_matches_family(item: RosterItem, family: str) -> bool:
    haystack = f"{item.id} {item.instrument} {item.role}".lower()
    if family in haystack:
        return True
    aliases = {
        "bass": ["electric_bass", "bass_guitar", "low_end", "low end"],
        "guitar": ["electric_guitar", "acoustic_guitar", "rhythm_guitar", "lead_guitar"],
        "piano": ["piano", "electric_piano", "keyboard", "keys", "rhodes"],
        "drums": ["drum_kit", "drums", "percussion"],
    }
    return any(alias in haystack for alias in aliases.get(family, []))


def _tile_note_pack(note_pack: dict[str, Any], header: Header, roster_item: RosterItem) -> list[Note]:
    raw_notes = note_pack.get("notes")
    if not isinstance(raw_notes, list):
        return []
    bar_count = int(note_pack.get("bar_count") or 1)
    start_bar = int(note_pack.get("start_bar") or 0)
    bar_count = max(1, bar_count)
    notes: list[Note] = []
    for offset in range(0, header.num_bars, bar_count):
        for raw in raw_notes:
            if not isinstance(raw, dict):
                continue
            source_bar = int(raw.get("bar") or 0) - start_bar
            target_bar = offset + source_bar
            if target_bar < 0 or target_bar >= header.num_bars:
                continue
            pitch = raw.get("pitch")
            if pitch is not None:
                pitch = int(pitch)
                if not roster_item.is_drum:
                    pitch = fit_to_range(pitch, roster_item.midi_range[0], roster_item.midi_range[1])
            notes.append(
                Note(
                    bar=target_bar,
                    start_beat=float(raw.get("start_beat") or 0.0),
                    pitch=pitch,
                    dur=float(raw.get("duration_beats") or raw.get("dur") or 1.0),
                    velocity=int(raw.get("velocity") or 96),
                )
            )
    return sorted(notes, key=lambda note: (note.bar, note.start_beat, note.pitch or -1))


def _timeline_note_pack(note_pack: dict[str, Any], header: Header, roster_item: RosterItem) -> list[Note]:
    raw_notes = note_pack.get("notes")
    if not isinstance(raw_notes, list):
        return []
    notes: list[Note] = []
    for raw in raw_notes:
        if not isinstance(raw, dict):
            continue
        target_bar = int(raw.get("bar") or 0)
        if target_bar < 0 or target_bar >= header.num_bars:
            continue
        pitch = raw.get("pitch")
        if pitch is not None:
            pitch = int(pitch)
            if not roster_item.is_drum:
                pitch = fit_to_range(pitch, roster_item.midi_range[0], roster_item.midi_range[1])
        notes.append(
            Note(
                bar=target_bar,
                start_beat=float(raw.get("start_beat") or 0.0),
                pitch=pitch,
                dur=float(raw.get("duration_beats") or raw.get("dur") or 1.0),
                velocity=int(raw.get("velocity") or 96),
            )
        )
    return sorted(notes, key=lambda note: (note.bar, note.start_beat, note.pitch or -1))
