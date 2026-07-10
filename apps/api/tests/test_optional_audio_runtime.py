"""Default Docker runtime keeps local audio analysis intentionally optional."""

from types import SimpleNamespace

from fastapi.testclient import TestClient

import music_assistant.interfaces.api as api


def test_audio_upload_returns_actionable_opt_in_guidance(monkeypatch):
    monkeypatch.setattr(api, "get_settings", lambda: SimpleNamespace(enable_audio_analysis=False))

    response = TestClient(api.app).post(
        "/references/analyze",
        files={"file": ("loop.wav", b"fake audio", "audio/wav")},
    )

    assert response.status_code == 503
    detail = response.json()["detail"]
    assert "optional" in detail.lower()
    assert "docker-compose.audio.yml" in detail
