"""Tests for the optional shared-secret gate and the CORS allowlist.

Both default to off, so the important case is that an unconfigured deployment
behaves exactly as it did before these knobs existed.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import music_assistant.interfaces.api as api
from music_assistant import config
from music_assistant.interfaces.security import cors_options


@pytest.fixture
def client() -> TestClient:
    return TestClient(api.app)


@pytest.fixture(autouse=True)
def clear_settings_cache():
    config.get_settings.cache_clear()
    yield
    config.get_settings.cache_clear()


def test_llm_routes_are_open_when_no_api_key_is_configured(monkeypatch, client):
    monkeypatch.delenv("API_KEY", raising=False)
    config.get_settings.cache_clear()

    response = client.post("/chat", json={"message": "hola"})

    assert response.status_code != 401


def test_llm_routes_reject_a_request_without_the_key(monkeypatch, client):
    monkeypatch.setenv("API_KEY", "s3cret")
    config.get_settings.cache_clear()

    response = client.post("/chat", json={"message": "hola"})

    assert response.status_code == 401


def test_llm_routes_reject_a_wrong_key(monkeypatch, client):
    monkeypatch.setenv("API_KEY", "s3cret")
    config.get_settings.cache_clear()

    response = client.post("/chat", json={"message": "hola"}, headers={"X-API-Key": "nope"})

    assert response.status_code == 401


def test_llm_routes_accept_the_configured_key(monkeypatch, client):
    monkeypatch.setenv("API_KEY", "s3cret")
    config.get_settings.cache_clear()

    response = client.post("/chat", json={"message": "hola"}, headers={"X-API-Key": "s3cret"})

    assert response.status_code != 401


@pytest.mark.parametrize("path", ["/chat", "/chat/stream", "/compose", "/compose/stream"])
def test_every_llm_route_is_guarded(monkeypatch, client, path):
    monkeypatch.setenv("API_KEY", "s3cret")
    config.get_settings.cache_clear()

    assert client.post(path, json={"message": "hola", "style": "disco"}).status_code == 401


def test_analysis_upload_stays_unguarded(monkeypatch, client):
    """The browser uploads audio directly, so it cannot carry the shared secret."""
    monkeypatch.setenv("API_KEY", "s3cret")
    config.get_settings.cache_clear()

    response = client.post("/references/analyze")

    # 400 "missing audio file" — the route ran, it did not reject on auth.
    assert response.status_code == 400


def test_health_stays_unguarded(monkeypatch, client):
    monkeypatch.setenv("API_KEY", "s3cret")
    config.get_settings.cache_clear()

    assert client.get("/health").status_code == 200


def test_cors_defaults_to_allowing_every_origin(monkeypatch):
    monkeypatch.delenv("CORS_ALLOW_ORIGINS", raising=False)
    monkeypatch.delenv("CORS_ALLOW_ORIGIN_REGEX", raising=False)
    config.get_settings.cache_clear()

    assert cors_options() == {"allow_origins": ["*"]}


def test_cors_uses_the_configured_allowlist(monkeypatch):
    monkeypatch.setenv("CORS_ALLOW_ORIGINS", "https://example.com, https://other.example.com")
    monkeypatch.delenv("CORS_ALLOW_ORIGIN_REGEX", raising=False)
    config.get_settings.cache_clear()

    assert cors_options() == {
        "allow_origins": ["https://example.com", "https://other.example.com"]
    }


def test_cors_carries_the_regex_for_generated_preview_hostnames(monkeypatch):
    monkeypatch.setenv("CORS_ALLOW_ORIGINS", "https://example.com")
    monkeypatch.setenv("CORS_ALLOW_ORIGIN_REGEX", r"^https://app-.*\.example\.com$")
    config.get_settings.cache_clear()

    options = cors_options()

    assert options["allow_origins"] == ["https://example.com"]
    assert options["allow_origin_regex"] == r"^https://app-.*\.example\.com$"
