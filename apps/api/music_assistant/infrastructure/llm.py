"""Provider-backed LangChain chat-model factory with fallback/error handling."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from typing import Any, Optional, TypeVar

from music_assistant.config import DEFAULT_MODELS, Settings, get_settings
from music_assistant.domain.cancellation import CancelledCompose, current_cancel_token
from music_assistant.domain.usage import USAGE_TRACKER, UsageTracker

T = TypeVar("T")

PROVIDER_LABELS = {
    "gemini": "Gemini",
    "groq": "Groq",
    "openrouter": "OpenRouter",
    "vertexai": "Vertex AI",
}


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

    @property
    def user_message(self) -> str:
        if not self.failures:
            return "No configured LLM provider is available."

        pieces = ["All configured LLM providers failed."]
        for failure in self.failures:
            provider = PROVIDER_LABELS.get(failure.provider, failure.provider.capitalize())
            if isinstance(failure, LLMQuotaExceeded):
                pieces.append(f"{provider} quota or rate limit was reached for {failure.model}.")
            else:
                pieces.append(f"{provider} is unavailable for {failure.model}: {failure.detail}.")
        return " ".join(pieces)


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


def _import_gemini_chat():
    from langchain_google_genai import ChatGoogleGenerativeAI

    return ChatGoogleGenerativeAI


def _import_openrouter_chat():
    from langchain_openai import ChatOpenAI

    return ChatOpenAI


# Per-role sampling temperature. The director picks style-defining fields
# (key, tempo, roster) that should converge to the genre mode; high temp made
# it slip into off-genre patches (clean_guitar/orchestral_harp on dark metal
# runs). Instrument agents stay expressive at the default.
_ROLE_TEMPERATURE = {"director": 0.3, "arbiter": 0.2}


def _temperature_for(role: str) -> float:
    return _ROLE_TEMPERATURE.get(role, 0.7)


def _build_chat_model(provider: str, model: str, settings: Settings, role: str = "director"):
    key = settings.api_key_for(provider)
    temperature = _temperature_for(role)
    if provider == "gemini":
        ChatGoogleGenerativeAI = _import_gemini_chat()

        return ChatGoogleGenerativeAI(
            model=model,
            google_api_key=key,
            temperature=temperature,
            retries=max(0, settings.llm_max_retries),
        )

    if provider == "groq":
        from langchain_groq import ChatGroq

        return ChatGroq(model=model, api_key=key, temperature=temperature)

    if provider == "openrouter":
        try:
            ChatOpenAI = _import_openrouter_chat()
        except ModuleNotFoundError as exc:
            raise LLMProviderUnavailable(
                provider=provider,
                model=model,
                detail='Install backend extra: pip install -e ".[openrouter]"',
            ) from exc

        # Give the ChatOpenAI a dedicated httpx.Client we control so that when
        # the request-scoped CancelToken fires we can .close() this client and
        # tear the socket down mid-request.
        #
        # `streaming` is auto-toggled: only real openrouter.ai supports the
        # exact streaming tool-call chunk format langchain_openai expects.
        # Any other base_url (llama-server, vLLM, LiteLLM, LAN IP, custom
        # hostname) makes langchain_openai raise "Error in input stream"
        # while parsing structured output, so we default those to
        # streaming=False and let it read the full JSON response.
        # For real OpenRouter we keep streaming=True to preserve the mid-token
        # GPU kill (peer-disconnect stops the remote decode).
        base_url = settings.openrouter_base_url or ""
        # Classify the target: real cloud OpenAI-compat gateway (openrouter.ai,
        # opencode.ai) vs. a local llama.cpp / vLLM. The three flags differ:
        #  - `is_local`: send `cache_prompt: true` so llama.cpp reuses KV cache.
        #  - `is_metered_openrouter`: cap `max_tokens` because openrouter.ai
        #    reserves credits against it up-front; opencode.ai is a flat-fee
        #    subscription and doesn't charge per-token, so no cap.
        #  - streaming: on for real cloud gateways, off for llama.cpp
        #    (langchain_openai flakes on llama.cpp's SSE format).
        is_local = ("localhost" in base_url) or ("127.0.0.1" in base_url) or ("0.0.0.0" in base_url)
        is_metered_openrouter = "openrouter.ai" in base_url
        extra_body = {"cache_prompt": True} if is_local else {}
        # OpenRouter reserves credits against max_tokens up-front, so we cap
        # tight there. Opencode-go is a flat subscription — no credit issue,
        # but we still request a generous budget explicitly so tool-call
        # arguments (structured-output JSON) never get truncated mid-note.
        # Local llama-server: unbounded.
        if is_metered_openrouter:
            max_tokens = 6000
        elif is_local:
            max_tokens = None
        else:
            # Flat-fee gateway (opencode.ai): budget must fit the LARGEST
            # structured output we ask for. A dense 8-bar drum slice is
            # ~200 notes ≈ 5-6k tokens of JSON plus the model's reasoning
            # tokens — 8000 truncated exactly those calls, which then
            # burned a rich+minimal retry pair per slice before falling to
            # the deterministic pattern (the "drums never sound like the
            # genre" failure mode).
            max_tokens = 16000
        # Streaming ON only for real openrouter.ai — everything else
        # (llama.cpp, opencode.ai) mangles the OpenAI SSE format enough that
        # `with_structured_output` fails at the incremental JSON parse
        # ("expected value at line 1 column 1"). Non-streaming gives us the
        # full response body and lets langchain parse it once at the end.
        streaming = is_metered_openrouter
        chat = ChatOpenAI(
            model=model,
            api_key=key,
            base_url=base_url,
            temperature=temperature,
            max_retries=max(0, settings.llm_max_retries),
            http_client=_new_cancellable_http_client(read_timeout=None if is_local else 180.0),
            streaming=streaming,
            extra_body=extra_body,
            max_tokens=max_tokens,
        )
        _register_openai_client_for_cancel(chat)
        return chat

    if provider == "vertexai":
        try:
            from langchain_google_vertexai import ChatVertexAI
        except ModuleNotFoundError as exc:
            raise LLMProviderUnavailable(
                provider=provider,
                model=model,
                detail='Install backend extra: pip install -e ".[vertexai]"',
            ) from exc
        return ChatVertexAI(
            model=model,
            project=settings.google_cloud_project,
            temperature=temperature,
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


def _record_usage(raw_message: Any) -> None:
    tracker = USAGE_TRACKER.get()
    if tracker is None:
        return
    usage = getattr(raw_message, "usage_metadata", None)
    if not usage:
        response_meta = getattr(raw_message, "response_metadata", {}) or {}
        usage = response_meta.get("token_usage") or response_meta.get("usage")
    tracker.add(usage)


def _usage_callbacks() -> list:
    """Return a callback that records usage from the underlying chat call.

    Lives at call-time (not on the chat model) because the tracker is request-
    scoped via contextvar; the callback closes over the *current* tracker.
    """
    try:
        from langchain_core.callbacks import BaseCallbackHandler
        from langchain_core.outputs import LLMResult
    except Exception:
        return []

    tracker = USAGE_TRACKER.get()
    if tracker is None:
        return []

    class _UsageCB(BaseCallbackHandler):  # type: ignore[misc]
        def on_llm_end(self, response: "LLMResult", **_: Any) -> None:
            for generations in response.generations:
                for generation in generations:
                    message = getattr(generation, "message", None)
                    if message is None:
                        continue
                    usage = getattr(message, "usage_metadata", None)
                    if not usage:
                        meta = getattr(message, "response_metadata", {}) or {}
                        usage = meta.get("token_usage") or meta.get("usage")
                    tracker.add(usage)
            llm_output = response.llm_output or {}
            if (usage := llm_output.get("token_usage")):
                tracker.add(usage)

    return [_UsageCB()]


def _new_cancellable_http_client(read_timeout: Optional[float] = None):
    """Fresh httpx.Client. Local llama-server calls pass `read_timeout=None`
    so a long Qwen decode never trips the client. Cloud gateways (opencode-go,
    openrouter.ai) pass a bounded value so a dropped mid-response doesn't
    stall the whole compose graph on `as_completed` — the failed fill returns
    a silent instrument instead of hanging forever."""
    import httpx

    return httpx.Client(timeout=httpx.Timeout(
        connect=10.0, read=read_timeout, write=read_timeout, pool=read_timeout
    ))


def _register_openai_client_for_cancel(chat) -> None:
    """Best-effort: locate the httpx.Client the ChatOpenAI's OpenAI SDK client
    is using and register it so a client cancel can force-close its sockets.
    Silent if the internal layout differs from what we expect — the
    between-call event check still catches cancellation."""
    token = current_cancel_token()
    if token is None:
        return
    # ChatOpenAI.root_client is openai.OpenAI; openai.OpenAI._client is
    # httpx.Client — that's the object whose sockets we need to reach.
    for attr in ("root_client", "root_async_client"):
        openai_client = getattr(chat, attr, None)
        httpx_client = getattr(openai_client, "_client", None)
        if httpx_client is not None:
            token.register_closable(httpx_client)


class _FallbackStructuredInvoker:
    def __init__(self, role: str, schema: type, settings: Settings):
        self.role = role
        self.schema = schema
        self.settings = settings

    def invoke(self, messages):
        def operation(provider: str, model: str):
            token = current_cancel_token()
            if token is not None:
                token.raise_if_cancelled()
            _RATE_LIMITER.wait(self.settings.llm_rpm_limit)
            chat = _build_chat_model(provider, model, self.settings, role=self.role)
            # OpenAI-compat gateways that expose reasoning models (MiniMax M3,
            # DeepSeek R1, etc.) emit `<think>...</think>` before the JSON
            # payload — the default `json_schema` parser can't skip that and
            # errors with "expected value at line 1 column 1". Tool-calling
            # (`method="function_calling"`) works because the reasoning goes
            # into the message body while the structured output travels as a
            # tool call. Only openrouter (our name for any OpenAI-compat
            # gateway) needs this — Gemini uses its own native path.
            if provider == "openrouter":
                # `tool_choice="required"` forces the model to actually
                # call the tool. Without this MiniMax M3 sometimes returns
                # a plain assistant reply (with reasoning) and no tool
                # call, which `with_structured_output` surfaces as `None`
                # → our fills node crashed with `NoneType has no attribute
                # notes` and silently produced empty tracks.
                structured = chat.with_structured_output(
                    self.schema,
                    method="function_calling",
                    tool_choice="required",
                )
            else:
                structured = chat.with_structured_output(self.schema)
            callbacks = _usage_callbacks()
            try:
                if callbacks:
                    return structured.invoke(messages, config={"callbacks": callbacks})
                return structured.invoke(messages)
            except CancelledCompose:
                raise
            except Exception as exc:
                # If the token fired mid-request, the httpx close raises a
                # generic transport error; surface it as CancelledCompose so the
                # generator unwinds without triggering fallback providers.
                if token is not None and token.cancelled:
                    raise CancelledCompose("compose was cancelled by the client") from exc
                raise

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
