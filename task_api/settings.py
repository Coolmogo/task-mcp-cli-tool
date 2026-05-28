from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class SparkSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    spark_llm_provider: Literal["openai", "google"] = "openai"
    openai_api_key: str | None = None
    openai_model: str = "gpt-4.1-mini"
    google_api_key: str | None = None
    google_model: str = "gemini-2.5-flash"


@lru_cache(maxsize=1)
def get_settings() -> SparkSettings:
    return SparkSettings()
