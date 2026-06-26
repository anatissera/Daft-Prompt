"""LLM provider routing, quota classification, and fallback behavior."""

from __future__ import annotations

import pytest

from llm_band.config import Settings
from llm_band.infrastructure.llm import (
    LLMAllProvidersFailed,
    LLMProviderUnavailable,
    LLMQuotaExceeded,
    _build_chat_model,
    classify_llm_error,
    model_plan,
    with_fallbacks,
)


def test_classify_gemini_quota_error_from_message():
    exc = RuntimeError("ResourceExhausted: 429 You exceeded your current quota")

    classified = classify_llm_error(exc, provider="gemini", model="gemini-2.5-flash")

    assert isinstance(classified, LLMQuotaExceeded)
    assert classified.provider == "gemini"
    assert classified.model == "gemini-2.5-flash"
    assert "quota" in classified.user_message.lower()


def test_classify_openrouter_quota_error_from_status_code():
    class OpenRouterError(Exception):
        status_code = 429

    classified = classify_llm_error(OpenRouterError("rate limit exceeded"), provider="openrouter", model="openrouter/free")

    assert isinstance(classified, LLMQuotaExceeded)
    assert classified.provider == "openrouter"
    assert classified.model == "openrouter/free"


def test_model_plan_walks_configured_gemini_models_then_openrouter():
    settings = Settings(
        llm_provider="gemini",
        gemini_api_key="gem",
        openrouter_api_key="or",
        model_director="gemini-2.5-flash",
        gemini_model_fallbacks="gemini-2.5-flash-lite,gemini-2.0-flash",
        openrouter_model_director="openrouter/free",
        llm_fallback_providers="gemini,openrouter",
    )

    assert model_plan("director", settings) == [
        ("gemini", "gemini-2.5-flash"),
        ("gemini", "gemini-2.5-flash-lite"),
        ("gemini", "gemini-2.0-flash"),
        ("openrouter", "openrouter/free"),
    ]


def test_with_fallbacks_uses_next_model_after_quota_error():
    calls: list[tuple[str, str]] = []

    def operation(provider: str, model: str) -> str:
        calls.append((provider, model))
        if model == "gemini-2.5-flash":
            raise LLMQuotaExceeded(provider=provider, model=model, detail="quota")
        return model

    result = with_fallbacks(
        "director",
        Settings(
            llm_provider="gemini",
            gemini_api_key="gem",
            model_director="gemini-2.5-flash",
            gemini_model_fallbacks="gemini-2.0-flash",
        ),
        operation,
    )

    assert result == "gemini-2.0-flash"
    assert calls == [("gemini", "gemini-2.5-flash"), ("gemini", "gemini-2.0-flash")]


def test_with_fallbacks_raises_all_providers_failed_after_exhaustion():
    def operation(provider: str, model: str) -> str:
        raise LLMProviderUnavailable(provider=provider, model=model, detail="down")

    with pytest.raises(LLMAllProvidersFailed) as err:
        with_fallbacks(
            "instrument",
            Settings(
                llm_provider="openrouter",
                openrouter_api_key="or",
                model_instrument="openrouter/free",
            ),
            operation,
        )

    assert err.value.failures
    assert err.value.provider == "all"


def test_all_providers_failed_message_is_concise_and_actionable():
    err = LLMAllProvidersFailed(
        [
            LLMQuotaExceeded(provider="gemini", model="gemini-2.5-flash", detail="very long provider dump"),
            LLMProviderUnavailable(
                provider="openrouter",
                model="openrouter/free",
                detail="Install backend extra: pip install -e \".[openrouter]\"",
            ),
        ]
    )

    assert err.user_message == (
        "All configured LLM providers failed. Gemini quota or rate limit was reached for "
        "gemini-2.5-flash. OpenRouter is unavailable for openrouter/free: Install backend "
        "extra: pip install -e \".[openrouter]\"."
    )


def test_gemini_chat_model_uses_configured_retry_count(monkeypatch):
    captured = {}

    class FakeGemini:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    import llm_band.infrastructure.llm as llm_module

    monkeypatch.setattr(llm_module, "_import_gemini_chat", lambda: FakeGemini)

    _build_chat_model(
        "gemini",
        "gemini-2.5-flash",
        Settings(llm_provider="gemini", gemini_api_key="gem", llm_max_retries=0),
    )

    assert captured["retries"] == 0


def test_openrouter_missing_dependency_mentions_attempted_model(monkeypatch):
    import llm_band.infrastructure.llm as llm_module

    def missing_openrouter():
        raise ModuleNotFoundError("No module named 'langchain_openai'")

    monkeypatch.setattr(llm_module, "_import_openrouter_chat", missing_openrouter)

    with pytest.raises(LLMProviderUnavailable) as err:
        _build_chat_model(
            "openrouter",
            "openrouter/free",
            Settings(llm_provider="openrouter", openrouter_api_key="or"),
        )

    assert err.value.provider == "openrouter"
    assert err.value.model == "openrouter/free"
    assert "pip install" in err.value.detail
