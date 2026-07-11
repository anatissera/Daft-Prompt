"""Phase 1 smoke tests: the canned song renders to a re-parseable .mid and a
valid .musicxml, and POST /compose returns artifact URLs."""

from __future__ import annotations

import pretty_midi
from fastapi.testclient import TestClient

import music_assistant.interfaces.api as api
from music_assistant.canned import canned_song
from music_assistant.music.render_midi import render_midi
from music_assistant.music.render_sheet import render_musicxml


def test_canned_song_renders_reparseable_midi(tmp_path):
    song = canned_song("test")
    path = render_midi(song, str(tmp_path / "song.mid"))
    pm = pretty_midi.PrettyMIDI(path)  # re-parse round-trip
    assert len(pm.instruments) == 3
    drums = [i for i in pm.instruments if i.is_drum]
    assert len(drums) == 1  # drums route to the percussion channel
    assert any(len(i.notes) > 0 for i in pm.instruments)


def test_canned_song_renders_valid_musicxml(tmp_path):
    song = canned_song("test")
    path = render_musicxml(song, str(tmp_path / "song.musicxml"))
    text = open(path, encoding="utf-8").read()
    assert "score-partwise" in text  # well-formed MusicXML root


class _Cfg:
    llm_configured = True


def test_compose_endpoint_returns_artifacts(monkeypatch):
    # No LLM key in CI: drive the director path with the deterministic canned song so
    # the endpoint still produces real artifacts. (Without an LLM, /compose now returns
    # an explicit 503 config error instead of silently composing the demo song.)
    monkeypatch.setattr(api, "get_settings", lambda: _Cfg())
    monkeypatch.setattr(api, "run_negotiation", lambda style: canned_song(style))
    client = TestClient(api.app)
    resp = client.post("/compose", json={"style": "slow blues"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["song"]["request"] == "slow blues"
    assert body["artifacts"]["midi"].endswith("/song.mid")
    assert body["artifacts"]["musicxml"].endswith("/song.musicxml")

    # harmonic-fit quality metric is surfaced for the UI
    assert "harmonic_fit" in body
    assert "_overall" in body["harmonic_fit"]
    assert 0.0 <= body["harmonic_fit"]["_overall"] <= 1.0

    # the advertised artifact is actually downloadable
    midi_path = "/artifacts/" + body["job_id"] + "/song.mid"
    dl = client.get(midi_path)
    assert dl.status_code == 200
    assert dl.headers["content-type"] == "audio/midi"
