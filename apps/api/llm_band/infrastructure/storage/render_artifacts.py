"""Render generated composition artifacts into a job directory."""

from __future__ import annotations

from pathlib import Path

from llm_band.domain.song_state import SongState
from llm_band.music.render_midi import render_midi
from llm_band.music.render_sheet import render_musicxml
from llm_band.music.validators import errors_only, validate_song


def render_artifacts(song: SongState, job_dir: Path) -> None:
    song.errors = [issue.message for issue in errors_only(validate_song(song))]
    render_midi(song, str(job_dir / "song.mid"))
    render_musicxml(song, str(job_dir / "song.musicxml"))
