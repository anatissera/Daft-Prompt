"""Runtime configuration (pydantic-settings). All optional so the app still runs
with no LLM configured (Phase 1/2 canned path)."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal, Optional

from pydantic_settings import BaseSettings, SettingsConfigDict

Provider = Literal["gemini", "groq", "openrouter", "vertexai"]

# sensible free-tier defaults per provider when MODEL_* isn't set explicitly
DEFAULT_MODELS: dict[str, str] = {
    "gemini": "gemini-2.5-flash",
    "groq": "llama-3.3-70b-versatile",
    "openrouter": "deepseek/deepseek-chat",
    "vertexai": "gemini-2.5-flash",
}


class Settings(BaseSettings):
    llm_provider: Optional[Provider] = None

    gemini_api_key: Optional[str] = None
    groq_api_key: Optional[str] = None
    openrouter_api_key: Optional[str] = None
    google_cloud_project: Optional[str] = None

    model_director: Optional[str] = None
    model_instrument: Optional[str] = None
    model_arbiter: Optional[str] = None

    gemini_model_fallbacks: Optional[str] = None
    openrouter_model_director: Optional[str] = None
    openrouter_model_instrument: Optional[str] = None
    openrouter_model_arbiter: Optional[str] = None
    openrouter_model_fallbacks: Optional[str] = None
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    llm_fallback_providers: str = "gemini,openrouter"

    llm_max_retries: int = 1
    llm_rpm_limit: int = 5
    llm_fail_fast_on_quota: bool = True

    max_rounds: int = 3
    reference_upload_dir: Optional[str] = None
    reference_upload_max_bytes: int = 50 * 1024 * 1024

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    def api_key_for(self, provider: str) -> Optional[str]:
        if provider == "vertexai":
            return "adc"  # ADC — no API key required
        return {
            "gemini": self.gemini_api_key,
            "groq": self.groq_api_key,
            "openrouter": self.openrouter_api_key,
        }.get(provider)

    @property
    def llm_configured(self) -> bool:
        return bool(self.llm_provider and self.api_key_for(self.llm_provider))


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
