from __future__ import annotations

from fastapi.testclient import TestClient

import music_assistant.interfaces.api as api
from music_assistant.infrastructure.llm import LLMQuotaExceeded


class FailingChatMusic:
    def handle(self, _req):
        raise LLMQuotaExceeded(provider="gemini", model="gemini-2.5-flash", detail="quota exceeded")


def test_chat_provider_error_returns_stable_chat_response(monkeypatch):
    monkeypatch.setattr(api, "_chat_music", lambda: FailingChatMusic())
    client = TestClient(api.app)

    response = client.post("/chat", json={"message": "compose something"})

    assert response.status_code == 200
    body = response.json()
    assert body["intent"] == "clarify"
    assert body["reply"] == "I could not compose because the LLM provider is unavailable."
    assert body["error"]["code"] == "quota_exceeded"
    assert "quota" in body["error"]["message"].lower()
    assert body["error"]["provider"] == "gemini"
    assert body["error"]["model"] == "gemini-2.5-flash"


def test_chat_compose_provider_error_uses_clear_composition_message(monkeypatch):
    monkeypatch.setattr(api, "_chat_music", lambda: FailingChatMusic())
    client = TestClient(api.app)

    response = client.post("/chat", json={"message": "compose a slow blues"})

    assert response.status_code == 200
    body = response.json()
    assert body["intent"] == "clarify"
    assert body["reply"] == "I could not compose because the LLM provider is unavailable."
    assert body["clarification"] == body["reply"]
    assert body["error"]["code"] == "quota_exceeded"
