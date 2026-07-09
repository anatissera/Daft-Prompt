"""Build compact instrument-reference profiles from scraped song evidence."""

from __future__ import annotations

import re
from typing import Any

from music_assistant.domain.audio_profile import (
    InstrumentPatternProfile,
    InstrumentTimbreProfile,
    MusicalMemoryProfile,
    ReferenceHarmonicContext,
    ReferenceInstrumentProfile,
    ReferenceMotif,
    ReferenceNotePack,
    ReferenceNoteSeed,
    ReferencePitchPattern,
    ReferenceProfile,
    ReferenceRhythmPattern,
)
from music_assistant.ports.songsterr_tab_store import SongsterrTabStore


_NOTE_PC = {
    "C": 0,
    "C#": 1,
    "DB": 1,
    "D": 2,
    "D#": 3,
    "EB": 3,
    "E": 4,
    "F": 5,
    "F#": 6,
    "GB": 6,
    "G": 7,
    "G#": 8,
    "AB": 8,
    "A": 9,
    "A#": 10,
    "BB": 10,
    "B": 11,
}


class ReferenceInstrumentProfileBuilder:
    def __init__(self, *, songsterr_tab_store: SongsterrTabStore | None = None) -> None:
        self.songsterr_tab_store = songsterr_tab_store

    def build(self, profile: ReferenceProfile) -> dict[str, ReferenceInstrumentProfile]:
        profiles: dict[str, ReferenceInstrumentProfile] = {}
        bundle = self.songsterr_tab_store.get(profile.reference_id) if self.songsterr_tab_store else None
        if bundle is not None:
            for track in bundle.tracks:
                family = _normalize_family(track.instrument_family)
                if family is None or family in profiles:
                    continue
                profiles[family] = _profile_from_songsterr_track(profile, track)
        _merge_knowledge_traits(profile, profiles)
        return profiles


def _profile_from_songsterr_track(profile: ReferenceProfile, track: Any) -> ReferenceInstrumentProfile:
    family = _normalize_family(track.instrument_family)
    assert family is not None
    seed, seed_notes = _seed_from_track(track, family)
    uncertainty: list[str] = []
    if track.note_count and not seed:
        uncertainty.append(f"{family} pitch data unavailable; using pattern and timbre traits only.")
    return ReferenceInstrumentProfile(
        source_reference_id=profile.reference_id,
        source_profile_id=profile.knowledge.profile_id if profile.knowledge else "",
        instrument_family=family,
        track_name=track.name,
        confidence=0.82 if track.note_count else 0.62,
        timbre=_timbre_for_track(track, family),
        pattern=_pattern_for_track(track, family, seed_notes),
        symbolic_seed=seed,
        musical_memory=_musical_memory_for_track(profile, track, family, seed_notes),
        evidence=[f"songsterr:part:{track.part_id}:instrument={family}"],
        uncertainty_notes=uncertainty,
    )


def _seed_from_track(track: Any, family: str) -> tuple[list[ReferenceNoteSeed], list[ReferenceNoteSeed]]:
    seeds: list[ReferenceNoteSeed] = []
    timing_notes: list[ReferenceNoteSeed] = []
    tuning = [_midi_from_note_name(item) for item in getattr(track, "tuning", [])]
    for measure in track.measures:
        signature = measure.signature or (4, 4)
        beats_per_bar = float(signature[0]) * (4.0 / float(signature[1]))
        events = [event for event in measure.events if not event.rest]
        for event in events:
            duration = _duration_beats(event.duration)
            start = min(beats_per_bar - 0.25, float(event.beat_index))
            pitch = _event_pitch(event, family, tuning)
            note = ReferenceNoteSeed(
                bar=measure.index,
                start_beat=round(max(0.0, start), 6),
                duration_beats=duration,
                pitch=pitch,
                section_name=_section_for_measure(track.measures, measure.index),
            )
            timing_notes.append(note)
            if pitch is not None:
                seeds.append(note)
            if len(seeds) >= 64:
                return seeds, timing_notes
    return seeds, timing_notes


def _event_pitch(event: Any, family: str, tuning: list[int | None]) -> int | None:
    if isinstance(getattr(event, "pitch", None), int) and 0 <= event.pitch <= 127:
        return event.pitch
    raw = event.raw if isinstance(event.raw, dict) else {}
    for key in ["midi", "midiPitch", "pitch", "value", "drum"]:
        value = raw.get(key)
        if isinstance(value, int) and 0 <= value <= 127:
            return value
    if family == "drums" and event.fret is not None:
        fret = int(event.fret)
        if 35 <= fret <= 81:
            return fret
    if family in {"bass", "guitar"} and event.string is not None and event.fret is not None:
        index = int(event.string) - 1
        if 0 <= index < len(tuning) and tuning[index] is not None:
            return min(127, max(0, int(tuning[index]) + int(event.fret)))
    return None


def _pattern_for_track(track: Any, family: str, notes: list[ReferenceNoteSeed]) -> InstrumentPatternProfile:
    note_count = len(notes) or int(getattr(track, "note_count", 0) or 0)
    measure_count = max(1, len(getattr(track, "measures", []) or []))
    density_value = note_count / measure_count
    density = "low" if density_value < 2 else "medium" if density_value < 6 else "high"
    durations = sorted({_duration_label(note.duration_beats) for note in notes if note.duration_beats})
    accent_beats = []
    for note in notes:
        if note.start_beat not in accent_beats:
            accent_beats.append(note.start_beat)
        if len(accent_beats) >= 8:
            break
    contour = _pitch_contour([note.pitch for note in notes if note.pitch is not None])
    return InstrumentPatternProfile(
        density=density,
        subdivision="mixed" if len(durations) > 1 else (durations[0] if durations else ""),
        accent_beats=accent_beats,
        contour=contour,
        fill_frequency="section transitions" if family == "drums" and _has_markers(track) else "",
    )


def _musical_memory_for_track(
    profile: ReferenceProfile,
    track: Any,
    family: str,
    notes: list[ReferenceNoteSeed],
) -> MusicalMemoryProfile:
    pack_notes = notes if family == "drums" else [note for note in notes if note.pitch is not None]
    note_packs = _note_packs_for_track(track, family, pack_notes)
    rhythm_patterns = [_rhythm_pattern_for_pack(pack) for pack in note_packs]
    pitch_patterns = [_pitch_pattern_for_pack(pack) for pack in note_packs if any(n.pitch is not None for n in pack.notes)]
    motifs = _motifs_for_packs(note_packs)
    harmonic_context = _harmonic_context_from_profile(profile)
    summary = _memory_summary(track, note_packs, rhythm_patterns, pitch_patterns, motifs, harmonic_context)
    return MusicalMemoryProfile(
        summary=summary,
        note_packs=note_packs,
        rhythm_patterns=rhythm_patterns,
        pitch_patterns=pitch_patterns,
        harmonic_context=harmonic_context,
        motifs=motifs,
    )


def _note_packs_for_track(track: Any, family: str, notes: list[ReferenceNoteSeed]) -> list[ReferenceNotePack]:
    if not notes:
        return []
    by_section: dict[str, list[ReferenceNoteSeed]] = {}
    for note in notes:
        section = note.section_name or "unmarked"
        by_section.setdefault(section, []).append(note)

    packs: list[ReferenceNotePack] = []
    for section, section_notes in by_section.items():
        ordered = sorted(section_notes, key=lambda n: (n.bar, n.start_beat))
        start_bar = ordered[0].bar
        end_bar = ordered[-1].bar
        pack_id = f"{family}_{_slug(section)}_{start_bar}_0"
        packs.append(
            ReferenceNotePack(
                pack_id=pack_id,
                instrument_family=family,  # type: ignore[arg-type]
                section_name=section,
                start_bar=start_bar,
                bar_count=max(1, end_bar - start_bar + 1),
                notes=ordered[:64],
            )
        )
    return packs[:8]


def _rhythm_pattern_for_pack(pack: ReferenceNotePack) -> ReferenceRhythmPattern:
    accent_beats: list[float] = []
    durations: list[float] = []
    for note in pack.notes:
        if note.start_beat not in accent_beats:
            accent_beats.append(note.start_beat)
        if note.duration_beats not in durations:
            durations.append(note.duration_beats)
    density_value = len(pack.notes) / max(1, pack.bar_count)
    density = "low" if density_value < 2 else "medium" if density_value < 6 else "high"
    return ReferenceRhythmPattern(
        pattern_id=f"rhythm_{pack.pack_id}",
        section_name=pack.section_name,
        density=density,
        accent_beats=accent_beats[:16],
        durations=durations[:16],
        subdivision="mixed" if len(durations) > 1 else (_duration_label(durations[0]) if durations else ""),
    )


def _pitch_pattern_for_pack(pack: ReferenceNotePack) -> ReferencePitchPattern:
    pitches = [note.pitch for note in pack.notes if note.pitch is not None]
    intervals: list[int] = []
    notes_by_bar: dict[int, list[ReferenceNoteSeed]] = {}
    for note in pack.notes:
        notes_by_bar.setdefault(note.bar, []).append(note)
    for bar_notes in notes_by_bar.values():
        bar_pitches = [note.pitch for note in sorted(bar_notes, key=lambda n: n.start_beat) if note.pitch is not None]
        for interval in [b - a for a, b in zip(bar_pitches, bar_pitches[1:])]:
            if interval not in intervals:
                intervals.append(interval)
    return ReferencePitchPattern(
        pattern_id=f"pitch_{pack.pack_id}",
        section_name=pack.section_name,
        register=[min(pitches), max(pitches)] if pitches else [],
        pitch_classes=sorted({pitch % 12 for pitch in pitches}),
        intervals=intervals[:32],
        contour=_pitch_contour(pitches),
    )


def _motifs_for_packs(packs: list[ReferenceNotePack]) -> list[ReferenceMotif]:
    motifs: list[ReferenceMotif] = []
    for pack in packs:
        by_bar: dict[int, list[ReferenceNoteSeed]] = {}
        for note in pack.notes:
            by_bar.setdefault(note.bar, []).append(note)
        signatures: dict[str, tuple[int, int, str, str]] = {}
        counts: dict[str, int] = {}
        for bar, notes in sorted(by_bar.items()):
            rhythm = ",".join(f"{n.start_beat:g}:{n.duration_beats:g}" for n in sorted(notes, key=lambda n: n.start_beat))
            pitches = [n.pitch for n in sorted(notes, key=lambda n: n.start_beat) if n.pitch is not None]
            intervals = ",".join(str(b - a) for a, b in zip(pitches, pitches[1:]))
            signature = rhythm + "|" + intervals
            signatures.setdefault(signature, (bar, 1, rhythm, intervals))
            counts[signature] = counts.get(signature, 0) + 1
        for signature, repetitions in counts.items():
            if repetitions < 2:
                continue
            start_bar, bar_count, rhythm, intervals = signatures[signature]
            motifs.append(
                ReferenceMotif(
                    motif_id=f"motif_{pack.pack_id}_{len(motifs)}",
                    section_name=pack.section_name,
                    start_bar=start_bar,
                    bar_count=bar_count,
                    repetitions=repetitions,
                    rhythm_signature=rhythm,
                    interval_signature=intervals,
                )
            )
    return motifs[:8]


def _memory_summary(
    track: Any,
    note_packs: list[ReferenceNotePack],
    rhythm_patterns: list[ReferenceRhythmPattern],
    pitch_patterns: list[ReferencePitchPattern],
    motifs: list[ReferenceMotif],
    harmonic_context: ReferenceHarmonicContext,
) -> str:
    pieces = [f"{track.name}"]
    if rhythm_patterns:
        rhythm = rhythm_patterns[0]
        pieces.append(
            f"{rhythm.density} density rhythm with accents at "
            f"{', '.join(f'{beat:g}' for beat in rhythm.accent_beats[:6]) or 'unknown beats'}"
        )
    if pitch_patterns and pitch_patterns[0].register:
        pitch = pitch_patterns[0]
        pieces.append(f"register {pitch.register[0]}-{pitch.register[1]} with {pitch.contour or 'compact'} contour")
    if motifs:
        pieces.append(f"main motif repeats {motifs[0].repetitions} times")
    if note_packs:
        pieces.append(f"primary note_pack={note_packs[0].pack_id}")
    if harmonic_context.chord_progression:
        chords = "-".join(harmonic_context.chord_progression[:4])
        romans = "-".join(harmonic_context.roman_progression[:4])
        pieces.append(f"harmony {chords}" + (f" ({romans})" if romans else ""))
    return "; ".join(pieces)


def _harmonic_context_from_profile(profile: ReferenceProfile) -> ReferenceHarmonicContext:
    knowledge = profile.knowledge
    if knowledge is None:
        return ReferenceHarmonicContext()
    key_claim = next((claim for claim in knowledge.evidence_claims if claim.claim_type == "key"), None)
    chord_claim = next(
        (claim for claim in knowledge.evidence_claims if claim.claim_type == "chord_progression" and claim.confidence >= 0.5),
        None,
    )
    key_name = (key_claim.normalized_value or key_claim.value).strip() if key_claim else None
    chords = _parse_chord_progression(chord_claim.normalized_value or chord_claim.value) if chord_claim else []
    romans = _roman_progression(key_name, chords) if key_name and chords else []
    return ReferenceHarmonicContext(
        key=key_name,
        chord_progression=chords[:32],
        roman_progression=romans[:32],
        harmonic_rhythm="compact scraped progression" if chords else "",
    )


def _parse_chord_progression(value: str) -> list[str]:
    tokens = re.split(r"\s+|\|+|,+|/+|>+", value)
    chords: list[str] = []
    for token in tokens:
        cleaned = token.strip()
        if not cleaned or not re.match(r"^[A-G](?:#|b)?(?:m|min|maj|dim|aug|sus|add|[0-9()]|/|#|b)*$", cleaned):
            continue
        chords.append(cleaned)
    return chords


def _roman_progression(key_name: str, chords: list[str]) -> list[str]:
    try:
        from music21 import harmony, key as m21_key, roman
    except Exception:  # pragma: no cover - optional dependency guard
        return []
    try:
        parts = key_name.strip().split()
        if len(parts) >= 2 and parts[1].lower().startswith(("maj", "min")):
            mode = "minor" if parts[1].lower().startswith("min") else "major"
            tonal_key = m21_key.Key(parts[0], mode)
        else:
            tonal_key = m21_key.Key(key_name)
    except Exception:
        return []
    romans: list[str] = []
    for chord_name in chords:
        try:
            symbol = harmony.ChordSymbol(chord_name)
            romans.append(_compact_roman(roman.romanNumeralFromChord(symbol, tonal_key).figure, tonal_key.mode))
        except Exception:
            continue
    return romans


def _compact_roman(figure: str, mode: str) -> str:
    if mode == "minor":
        for flat_degree in ["bIII", "bVI", "bVII"]:
            figure = figure.replace(flat_degree, flat_degree[1:])
    return figure


def _timbre_for_track(track: Any, family: str) -> InstrumentTimbreProfile:
    text = f"{track.name} {track.instrument}".lower()
    program, midi_range, technique = _gm_program_for_text(family, text)
    return InstrumentTimbreProfile(
        instrument_name=track.name,
        source_label=track.instrument,
        midi_program=program,
        midi_range=midi_range,
        technique=technique,
        is_drum=family == "drums",
    )


def _gm_program_for_text(family: str, text: str) -> tuple[int, tuple[int, int], str | None]:
    if family == "drums":
        return 0, (35, 81), "GM drum kit"
    if family == "bass":
        if "slap" in text:
            return 36, (28, 60), "slap"
        if "pick" in text:
            return 34, (28, 55), "picked"
        if "fretless" in text:
            return 35, (28, 55), "fretless"
        return 33, (28, 55), "finger"
    if family == "guitar":
        if "nylon" in text:
            return 24, (40, 84), "nylon"
        if "acoustic" in text or "steel" in text:
            return 25, (40, 84), "acoustic"
        if "distort" in text:
            return 30, (40, 84), "distorted"
        if "overdrive" in text:
            return 29, (40, 84), "overdriven"
        return 26, (40, 84), "clean"
    if "rhodes" in text or "electric piano" in text:
        return 4, (36, 96), "electric piano"
    if "organ" in text:
        return 16, (36, 96), "organ"
    if "pad" in text:
        return 88, (48, 96), "pad"
    if "lead" in text or "synth" in text:
        return 80, (48, 96), "synth"
    return 0, (36, 96), "piano"


def _merge_knowledge_traits(
    profile: ReferenceProfile,
    profiles: dict[str, ReferenceInstrumentProfile],
) -> None:
    knowledge = profile.knowledge
    if knowledge is None:
        return
    for trait in knowledge.traits:
        family = _normalize_family(trait.instrument)
        if family is None or family in profiles:
            continue
        profiles[family] = ReferenceInstrumentProfile(
            source_reference_id=profile.reference_id,
            source_profile_id=knowledge.profile_id,
            instrument_family=family,
            track_name=trait.instrument,
            confidence=trait.confidence,
            pattern=InstrumentPatternProfile(
                density=_trait_density(trait.traits.get("density", "")),
                subdivision=trait.traits.get("subdivision", ""),
                contour=trait.traits.get("contour", ""),
            ),
            evidence=[f"knowledge:trait:{claim_id}" for claim_id in trait.source_claim_ids],
        )


def _normalize_family(value: str) -> str | None:
    normalized = value.strip().lower()
    aliases = {
        "drum": "drums",
        "drums": "drums",
        "bass": "bass",
        "guitar": "guitar",
        "piano": "piano",
        "keyboard": "piano",
        "keys": "piano",
        "synth": "piano",
    }
    return aliases.get(normalized)


def _section_for_measure(measures: list[Any], index: int) -> str | None:
    current: str | None = None
    for measure in sorted(measures, key=lambda m: m.index):
        if measure.marker:
            current = str(measure.marker)
        if measure.index == index:
            return current
    return current


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_") or "section"


def _trait_density(value: str) -> str:
    return value if value in {"low", "medium", "high"} else "medium"


def _midi_from_note_name(value: str) -> int | None:
    numeric = str(value).strip()
    if re.match(r"^\d+(?:\.0+)?$", numeric):
        midi = int(float(numeric))
        return midi if 0 <= midi <= 127 else None
    match = re.match(r"^\s*([A-Ga-g])([#bB]?)(-?\d+)\s*$", value)
    if not match:
        return None
    name = (match.group(1).upper() + match.group(2).replace("b", "B").upper()).strip()
    octave = int(match.group(3))
    pc = _NOTE_PC.get(name)
    if pc is None:
        return None
    return (octave + 1) * 12 + pc


def _duration_beats(value: str) -> float:
    match = re.match(r"^\s*(\d+(?:\.\d+)?)/(\d+(?:\.\d+)?)\s*$", value or "")
    if not match:
        return 1.0
    numerator = float(match.group(1))
    denominator = float(match.group(2))
    if denominator <= 0:
        return 1.0
    return max(0.125, 4.0 * numerator / denominator)


def _duration_label(duration: float) -> str:
    if duration <= 0.5:
        return "eighths"
    if duration <= 1.0:
        return "quarters"
    if duration <= 2.0:
        return "halves"
    return "long"


def _pitch_contour(pitches: list[int]) -> str:
    if len(pitches) < 2:
        return ""
    if pitches[-1] > pitches[0]:
        return "rising"
    if pitches[-1] < pitches[0]:
        return "falling"
    return "static"


def _has_markers(track: Any) -> bool:
    return any(measure.marker for measure in getattr(track, "measures", []) or [])
