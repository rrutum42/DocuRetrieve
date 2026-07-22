"""Runtime configuration, loaded from environment / .env.

Everything secret or deployment-specific lives here so the rest of the app
never reads os.environ directly.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Gemini
    gemini_api_key: str = ""
    gemini_model: str = "gemini-flash-latest"  # receipt vision/extraction
    # The ask box uses a separate, lighter model — its own free-tier quota
    # bucket, so heavy Q&A doesn't starve receipt extraction (and vice-versa).
    gemini_ask_model: str = "gemini-flash-lite-latest"

    # Supabase
    supabase_url: str = ""
    supabase_key: str = ""

    # When true, extraction uses a deterministic local stub instead of Gemini.
    # Lets the app and tests run with no API key.
    docuretrieve_use_stub: bool = False

    # Home currency for the personal ("Everyday") ledger and the default for new
    # trips. Trips can override their own base currency at creation.
    default_base_currency: str = "INR"

    @property
    def gemini_configured(self) -> bool:
        return bool(self.gemini_api_key)

    @property
    def supabase_configured(self) -> bool:
        return bool(self.supabase_url and self.supabase_key)


@lru_cache
def get_settings() -> Settings:
    """Cached accessor so we build Settings once per process."""
    return Settings()
