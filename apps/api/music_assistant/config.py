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
    # Sized for a free tier. The limiter is process-global and spaces every call
    # by 60/limit seconds, so this also caps how fast the parallel fill pool can
    # go: at 5 a compose spends minutes asleep. Flat-fee gateways should raise it
    # — see the note in .env.example.
    llm_rpm_limit: int = 5
    llm_fail_fast_on_quota: bool = True

    max_rounds: int = 3
    artifacts_dir: Optional[str] = None
    reference_store_dir: Optional[str] = None
    reference_upload_dir: Optional[str] = None
    reference_upload_max_bytes: int = 50 * 1024 * 1024

    # Root log level. INFO keeps the pipeline's per-stage TIMING lines, which
    # are the only way to see where a slow compose spent its time.
    log_level: str = "INFO"

    # HTTP access control. All unset by default: no auth, CORS wide open.
    api_key: Optional[str] = None
    cors_allow_origins: Optional[str] = None
    cors_allow_origin_regex: Optional[str] = None

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
