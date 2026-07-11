"""Transcription port for future listening workflows."""

from __future__ import annotations

from typing import Protocol

from music_assistant.domain.audio_profile import ReferenceSource
from music_assistant.domain.song_state import Note


class Transcriber(Protocol):
    def transcribe_melody(self, source: ReferenceSource) -> list[Note]:
        ...
