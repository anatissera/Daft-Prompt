"""Local audio analysis is no longer a supported Daft Prompt product path."""

from types import SimpleNamespace

from fastapi.testclient import TestClient

import music_assistant.interfaces.api as api


def test_audio_upload_returns_connector_guidance(monkeypatch):
    monkeypatch.setattr(api, "get_settings", lambda: SimpleNamespace(enable_audio_analysis=False))

    response = TestClient(api.app).post(
        "/references/analyze",
        files={"file": ("loop.wav", b"fake audio", "audio/wav")},
    )

    assert response.status_code == 410
    detail = response.json()["detail"]
    assert "not a supported Daft Prompt path" in detail
    assert "Songsterr" in detail
