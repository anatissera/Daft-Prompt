"""Runtime configuration (pydantic-settings). All optional so the app still runs
with no LLM configured (Phase 1/2 canned path)."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal, Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

Provider = Literal["gemini", "groq", "openrouter", "vertexai"]

# sensible free-tier defaults per provider when MODEL_* isn't set explicitly
DEFAULT_MODELS: dict[str, str] = {
    "gemini": "gemini-3.5-flash",
    "groq": "llama-3.3-70b-versatile",
    "openrouter": "deepseek/deepseek-chat",
    "vertexai": "gemini-3.5-flash",
}


class Settings(BaseSettings):
    llm_provider: Optional[Provider] = None

    gemini_api_key: Optional[str] = None
    groq_api_key: Optional[str] = None
    openrouter_api_key: Optional[str] = None
    google_cloud_project: Optional[str] = None
    google_cloud_location: str = "global"

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
    llm_director_temperature: float = Field(default=0.3, ge=0.0, le=2.0)
    llm_instrument_temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    llm_arbiter_temperature: float = Field(default=0.2, ge=0.0, le=2.0)

    max_rounds: int = 3
    reference_upload_dir: Optional[str] = None
    reference_upload_max_bytes: int = 50 * 1024 * 1024
    reference_stem_cache_enabled: bool = False
    reference_stem_cache_dir: Optional[str] = None
    enable_melody_transcription: bool = False
    enable_web_research: bool = False

    # Model role settings intentionally retain their explicit MODEL_* environment
    # names; only reserve the settings-specific namespace to avoid Pydantic's
    # warning for these stable public configuration fields.
    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
        protected_namespaces=("settings_",),
    )

    @field_validator("llm_provider", mode="before")
    @classmethod
    def _blank_provider_means_unconfigured(cls, value: object) -> object:
        """Accept Compose's empty interpolation as the documented no-provider mode."""
        return None if isinstance(value, str) and not value.strip() else value

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
