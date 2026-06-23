"""Rendering application service for generated composition artifacts."""

from __future__ import annotations

from pathlib import Path

from .music.render_midi import render_midi
from .music.render_sheet import render_musicxml
from .music.validators import errors_only, validate_song
from .schema import SongState


def render_artifacts(song: SongState, job_dir: Path) -> None:
    song.errors = [issue.message for issue in errors_only(validate_song(song))]
    render_midi(song, str(job_dir / "song.mid"))
    render_musicxml(song, str(job_dir / "song.musicxml"))
