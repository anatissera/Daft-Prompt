"""Render generated composition artifacts into a job directory."""

from __future__ import annotations

from pathlib import Path

from music_assistant.domain.song_state import SongState
from music_assistant.music.finalize import enforce_bass_downbeats
from music_assistant.music.render_midi import render_midi
from music_assistant.music.render_sheet import render_musicxml
from music_assistant.music.validators import errors_only, validate_song


def render_artifacts(song: SongState, job_dir: Path) -> None:
    # composition-finalization pass (idempotent): snap bass downbeat non-chord notes
    # to the nearest chord tone before validating/rendering, so the response, the
    # MIDI, and the score all reflect the same finalized song.
    enforce_bass_downbeats(song)
    song.errors = [issue.message for issue in errors_only(validate_song(song))]
    render_midi(song, str(job_dir / "song.mid"))
    render_musicxml(song, str(job_dir / "song.musicxml"))
