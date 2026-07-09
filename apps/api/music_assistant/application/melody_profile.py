"""Stable, bounded melody summaries built from symbolic transcription notes."""

from __future__ import annotations

from music_assistant.domain.audio_profile import MelodyEvent, MelodyProfile
from music_assistant.domain.song_state import Note


def melody_profile_from_notes(notes: list[Note]) -> MelodyProfile:
    pitched = sorted((note for note in notes if note.pitch is not None), key=lambda note: (note.bar, note.start_beat))
    pitches = [note.pitch for note in pitched if note.pitch is not None]
    return MelodyProfile(
        note_count=len(pitched),
        pitch_low=min(pitches) if pitches else None,
        pitch_high=max(pitches) if pitches else None,
        contour=_contour(pitches),
        representative_events=[
            MelodyEvent(
                bar=note.bar,
                start_beat=note.start_beat,
                duration_beats=note.dur,
                pitch=note.pitch,
            )
            for note in _representative_notes(pitched)
            if note.pitch is not None
        ],
        # Basic pitch events do not include calibrated confidence scores. Keep
        # the summary explicitly provisional instead of inventing precision.
        confidence=0.4 if pitched else 0.0,
    )


def _representative_notes(notes: list[Note], limit: int = 32) -> list[Note]:
    if len(notes) <= limit:
        return notes
    indexes = {round(index * (len(notes) - 1) / (limit - 1)) for index in range(limit)}
    return [note for index, note in enumerate(notes) if index in indexes]


def _contour(pitches: list[int], *, dead_zone: int = 2) -> str:
    if len(pitches) < 2:
        return "unknown"
    movement = pitches[-1] - pitches[0]
    if abs(movement) <= dead_zone:
        return "static"
    deltas = [later - earlier for earlier, later in zip(pitches, pitches[1:])]
    has_up = any(delta > 0 for delta in deltas)
    has_down = any(delta < 0 for delta in deltas)
    if has_up and has_down:
        return "mixed"
    return "rising" if movement > 0 else "falling"
