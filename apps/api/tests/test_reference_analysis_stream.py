"""Streaming upload-analysis endpoint is retired from the Daft Prompt product."""

from __future__ import annotations

from fastapi.testclient import TestClient

import music_assistant.interfaces.api as api


def test_analyze_reference_stream_returns_unsupported_product_path():
    client = TestClient(api.app)

    response = client.post(
        "/references/analyze/stream",
        files={"file": ("loop.wav", b"fake audio bytes", "audio/wav")},
    )

    assert response.status_code == 410
    assert "Songsterr" in response.json()["detail"]
