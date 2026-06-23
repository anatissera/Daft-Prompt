"""Export a SongState to MusicXML (always) and PDF (only if MuseScore/LilyPond is
available). MusicXML is what the browser renders via OpenSheetMusicDisplay, so PDF
is optional and the pipeline never fails just because no engraver is installed.
"""

from __future__ import annotations

from .to_music21 import song_to_score
from ..schema import SongState


def render_musicxml(song: SongState, path: str) -> str:
    """Write `song` to a `.musicxml` file at `path`; returns the path."""
    score = song_to_score(song)
    score.write("musicxml", fp=path)
    return path


def render_pdf(song: SongState, path: str) -> str | None:
    """Best-effort PDF via music21's configured engraver. Returns the path on
    success, or None if no engraver is available (MIDI/MusicXML still work)."""
    try:
        score = song_to_score(song)
        score.write("musicxml.pdf", fp=path)
        return path
    except Exception:
        return None
