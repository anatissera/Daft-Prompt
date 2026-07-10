from pathlib import Path

from music_assistant.canned import canned_song
from music_assistant.infrastructure.storage import render_artifacts as module


def test_musicxml_failure_keeps_midi_artifact(monkeypatch, tmp_path: Path):
    def fail_notation(*_args, **_kwargs):
        raise RuntimeError("notation unavailable")

    monkeypatch.setattr(module, "render_musicxml", fail_notation)

    rendered = module.render_artifacts(canned_song("blues"), tmp_path)

    assert "midi" in rendered
    assert "musicxml" not in rendered
    assert (tmp_path / "song.mid").is_file()
    assert not (tmp_path / "song.musicxml").exists()
