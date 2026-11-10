"""Application settings loaded from environment variables / backend/.env."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env", env_file_encoding="utf-8", extra="ignore"
    )

    app_env: Literal["development", "test", "production"] = "development"
    app_name: str = "Open Source Intelligence Platform"
    api_v1_prefix: str = "/api/v1"

    database_url: str | None = None
    test_database_url: str | None = None

    github_token: SecretStr | None = None
    github_api_base_url: str = "https://api.github.com"

    ai_provider: Literal["mock", "bedrock"] = "mock"
    embedding_dim: int = 1024
    rrf_k: int = 60

    cors_origins: list[str] = ["http://localhost:3000"]
    log_level: str = "INFO"
    max_request_bytes: int = 65536


@lru_cache
def get_settings() -> Settings:
    return Settings()
