"""Provider-backed LangChain chat-model factory with fallback/error handling."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from typing import Optional, TypeVar

from llm_band.config import DEFAULT_MODELS, Settings, get_settings

T = TypeVar("T")


class LLMError(RuntimeError):
    code = "llm_error"

    def __init__(self, *, provider: str, model: str, detail: str):
        self.provider = provider
        self.model = model
        self.detail = detail
        super().__init__(self.user_message)

    @property
    def user_message(self) -> str:
        return f"{self.provider}/{self.model} failed: {self.detail}"


class LLMQuotaExceeded(LLMError):
    code = "quota_exceeded"

    @property
    def user_message(self) -> str:
        return f"{self.provider}/{self.model} hit its quota or rate limit: {self.detail}"


class LLMProviderUnavailable(LLMError):
    code = "provider_unavailable"


class LLMStructuredOutputError(LLMError):
    code = "structured_output_error"


class LLMAllProvidersFailed(LLMError):
    code = "all_providers_failed"

    def __init__(self, failures: list[LLMError]):
        self.failures = failures
        detail = "; ".join(f"{f.provider}/{f.model}: {f.detail}" for f in failures) or "no models configured"
        super().__init__(provider="all", model="all", detail=detail)


def _csv(value: Optional[str]) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def _role_model(provider: str, role: str, settings: Settings) -> str:
    if provider == "openrouter":
        explicit = {
            "director": settings.openrouter_model_director,
            "instrument": settings.openrouter_model_instrument,
            "arbiter": settings.openrouter_model_arbiter,
        }.get(role)
        return explicit or DEFAULT_MODELS["openrouter"]

    explicit = {
        "director": settings.model_director,
        "instrument": settings.model_instrument,
        "arbiter": settings.model_arbiter or settings.model_director,
    }.get(role)
    return explicit or DEFAULT_MODELS[provider]


def model_plan(role: str, settings: Settings) -> list[tuple[str, str]]:
    if not settings.llm_provider:
        return []

    providers = _csv(settings.llm_fallback_providers)
    providers = [settings.llm_provider] + [p for p in providers if p != settings.llm_provider]

    plan: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for provider in providers:
        if provider not in DEFAULT_MODELS:
            continue
        if not settings.api_key_for(provider):
            continue
        models = [_role_model(provider, role, settings)]
        if provider == "gemini":
            models += _csv(settings.gemini_model_fallbacks)
        elif provider == "openrouter":
            models += _csv(settings.openrouter_model_fallbacks)

        for model in models:
            item = (provider, model)
            if item not in seen:
                plan.append(item)
                seen.add(item)
    return plan


def classify_llm_error(exc: Exception, *, provider: str, model: str) -> LLMError:
    if isinstance(exc, LLMError):
        return exc

    status = getattr(exc, "status_code", None) or getattr(getattr(exc, "response", None), "status_code", None)
    text = str(exc)
    lowered = text.lower()
    if status == 429 or "429" in lowered or "quota" in lowered or "resourceexhausted" in lowered or "rate limit" in lowered:
        return LLMQuotaExceeded(provider=provider, model=model, detail=text)
    return LLMProviderUnavailable(provider=provider, model=model, detail=text)


class _RateLimiter:
    def __init__(self):
        self._lock = threading.Lock()
        self._next_at = 0.0

    def wait(self, rpm_limit: int) -> None:
        if rpm_limit <= 0:
            return
        spacing = 60.0 / rpm_limit
        with self._lock:
            now = time.monotonic()
            if now < self._next_at:
                time.sleep(self._next_at - now)
                now = time.monotonic()
            self._next_at = now + spacing


_RATE_LIMITER = _RateLimiter()


def _build_chat_model(provider: str, model: str, settings: Settings):
    key = settings.api_key_for(provider)
    if provider == "gemini":
        from langchain_google_genai import ChatGoogleGenerativeAI

        return ChatGoogleGenerativeAI(model=model, google_api_key=key, temperature=0.7)

    if provider == "groq":
        from langchain_groq import ChatGroq

        return ChatGroq(model=model, api_key=key, temperature=0.7)

    if provider == "openrouter":
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            model=model,
            api_key=key,
            base_url="https://openrouter.ai/api/v1",
            temperature=0.7,
        )

    raise LLMProviderUnavailable(provider=provider, model=model, detail="unknown provider")


def with_fallbacks(role: str, settings: Settings, operation: Callable[[str, str], T]) -> T:
    failures: list[LLMError] = []
    for provider, model in model_plan(role, settings):
        try:
            return operation(provider, model)
        except Exception as exc:
            failure = classify_llm_error(exc, provider=provider, model=model)
            failures.append(failure)
            if isinstance(failure, LLMStructuredOutputError):
                break
            if isinstance(failure, LLMQuotaExceeded) and settings.llm_fail_fast_on_quota:
                continue
    raise LLMAllProvidersFailed(failures)


class _FallbackStructuredInvoker:
    def __init__(self, role: str, schema: type, settings: Settings):
        self.role = role
        self.schema = schema
        self.settings = settings

    def invoke(self, messages):
        def operation(provider: str, model: str):
            _RATE_LIMITER.wait(self.settings.llm_rpm_limit)
            chat = _build_chat_model(provider, model, self.settings)
            return chat.with_structured_output(self.schema).invoke(messages)

        return with_fallbacks(self.role, self.settings, operation)


class FallbackChatModel:
    def __init__(self, role: str, settings: Settings):
        self.role = role
        self.settings = settings

    def with_structured_output(self, schema: type[T]):
        return _FallbackStructuredInvoker(self.role, schema, self.settings)


def make_llm(role: str = "director", settings: Optional[Settings] = None):
    s = settings or get_settings()
    if not model_plan(role, s):
        raise RuntimeError(
            "No LLM configured. Set LLM_PROVIDER and the matching <PROVIDER>_API_KEY."
        )
    return FallbackChatModel(role, s)
