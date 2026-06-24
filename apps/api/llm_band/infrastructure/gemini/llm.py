"""Provider-backed LangChain chat-model factory."""

from __future__ import annotations

from typing import Optional

from llm_band.config import DEFAULT_MODELS, Settings, get_settings


def _model_name(role: str, settings: Settings) -> str:
    explicit = settings.model_director if role == "director" else settings.model_instrument
    return explicit or DEFAULT_MODELS[settings.llm_provider]  # type: ignore[index]


def make_llm(role: str = "director", settings: Optional[Settings] = None):
    s = settings or get_settings()
    if not s.llm_configured:
        raise RuntimeError(
            "No LLM configured. Set LLM_PROVIDER and the matching <PROVIDER>_API_KEY."
        )

    provider = s.llm_provider
    key = s.api_key_for(provider)  # type: ignore[arg-type]
    model = _model_name(role, s)

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

    raise RuntimeError(f"unknown provider: {provider}")
