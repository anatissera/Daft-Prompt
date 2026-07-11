"""HTTP API behavior for the retired local-audio analysis product path."""

from __future__ import annotations

from fastapi.testclient import TestClient

import music_assistant.interfaces.api as api


def test_analyze_reference_upload_returns_unsupported_product_path():
    client = TestClient(api.app)

    response = client.post(
        "/references/analyze",
        files={"file": ("loop.wav", b"fake audio bytes", "audio/wav")},
    )

    assert response.status_code == 410
    detail = response.json()["detail"]
    assert "not a supported Daft Prompt path" in detail
    assert "Songsterr" in detail


def test_analyze_reference_upload_without_file_still_reports_unsupported_path():
    client = TestClient(api.app)

    response = client.post("/references/analyze", files={})

    assert response.status_code == 410
    assert "public evidence connectors" in response.json()["detail"]
