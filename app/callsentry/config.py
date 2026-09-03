"""Application configuration.

Every setting is environment-driven so the same image runs in dev and prod.
The important one is `local_only`: when true, no paid inference API is ever
called regardless of which keys happen to be present in the environment.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    # --- Core ---------------------------------------------------------------
    database_url: str = "postgresql+asyncpg://callsentry:callsentry@postgres:5432/callsentry"
    redis_url: str = "redis://redis:6379/0"
    log_level: str = "INFO"

    encryption_key: str = Field(..., alias="ENCRYPTION_KEY")
    jwt_secret: str = Field(..., alias="JWT_SECRET")
    jwt_ttl_seconds: int = 60 * 60 * 12
    # A viewer-role user the public showcase signs visitors in as. Empty
    # disables the shortcut and the showcase links to the sign-in page.
    demo_viewer_email: str = ""
    internal_api_token: str = Field(..., alias="INTERNAL_API_TOKEN")

    public_base_url: str = "http://localhost:8000"
    public_ws_url: str = "ws://localhost:8080"

    # --- Local-first switch -------------------------------------------------
    callsentry_local_only: bool = True

    # --- Local providers ----------------------------------------------------
    ollama_base_url: str = "http://ollama:11434"
    ollama_model: str = "llama3.2"
    ollama_embed_model: str = "nomic-embed-text"
    worker_base_url: str = "http://worker:8100"

    # --- Telephony (no local substitute) -----------------------------------
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_phone_number: str = ""

    # --- Optional cloud fallbacks ------------------------------------------
    claude_api_key: str = ""
    claude_model: str = "claude-sonnet-5"
    elevenlabs_api_key: str = ""
    deepgram_api_key: str = ""
    retell_api_key: str = ""
    openai_api_key: str = ""

    # --- Calendar -----------------------------------------------------------
    calcom_api_key: str = ""
    calcom_base_url: str = "https://api.cal.com/v1"

    # --- Conversation tuning ------------------------------------------------
    kb_confidence_threshold: float = 0.62
    max_clarifying_questions: int = 3

    # --- Compliance ---------------------------------------------------------
    recording_retention_days: int = 90
    transcript_retention_days: int = 365

    @property
    def local_only(self) -> bool:
        return self.callsentry_local_only

    def cloud_enabled(self, key: str) -> bool:
        """True when a cloud fallback is both configured and permitted."""
        return bool(key) and not self.local_only


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
