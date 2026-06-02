from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class SparkSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    openrouter_api_key: str | None = None
    openrouter_model: str = "anthropic/claude-3-haiku"


@lru_cache(maxsize=1)
def get_settings() -> SparkSettings:
    return SparkSettings()
