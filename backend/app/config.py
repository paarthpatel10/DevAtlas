"""Application settings loaded from environment variables / .env files.

Env files are read in order, later ones overriding earlier ones:
  1. <repo>/.env and <repo>/.env.local - written by `neon deploy` / `neon env pull`
  2. backend/.env - local overrides
"""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import AliasChoices, Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = BACKEND_DIR.parent

_PSYCOPG_SCHEME = "postgresql+psycopg://"


def to_psycopg_url(url: str | None) -> str | None:
    """Point a plain Postgres URL (as Neon issues them) at SQLAlchemy's psycopg 3 driver.

    `postgresql://` alone would make SQLAlchemy load psycopg2, which is not installed.
    URLs that already name a driver (`postgresql+...://`) are left untouched.
    """
    if not url:
        return url
    for scheme in ("postgresql://", "postgres://"):
        if url.startswith(scheme):
            return _PSYCOPG_SCHEME + url[len(scheme) :]
    return url


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(REPO_ROOT / ".env", REPO_ROOT / ".env.local", BACKEND_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: Literal["development", "test", "production"] = "development"
    app_name: str = "Open Source Intelligence Platform"
    api_v1_prefix: str = "/api/v1"

    # Pooled connection (Neon `-pooler` host) for application traffic.
    # Also accepts `neon_db`, the name used in this project's repo-root .env.
    database_url: str | None = Field(
        default=None, validation_alias=AliasChoices("database_url", "neon_db")
    )
    # Direct connection for schema migrations (Alembic); falls back to database_url.
    database_url_unpooled: str | None = None
    test_database_url: str | None = Field(
        default=None, validation_alias=AliasChoices("test_database_url", "neon_db_test")
    )

    github_token: SecretStr | None = None
    github_api_base_url: str = "https://api.github.com"

    # auto = Gemini when a key is configured, otherwise the deterministic mock (demo mode).
    ai_provider: Literal["auto", "mock", "gemini", "bedrock"] = "auto"
    gemini_api_key: SecretStr | None = Field(
        default=None, validation_alias=AliasChoices("gemini_api_key", "gemini")
    )
    # flash-lite: the free tier allows far more requests per day than flash (20/day).
    gemini_model: str = "gemini-3.5-flash-lite"
    gemini_base_url: str = "https://generativelanguage.googleapis.com/v1beta"
    ai_requests_per_minute: int = 10
    embedding_dim: int = 1024
    rrf_k: int = 60

    cors_origins: list[str] = ["http://localhost:3000"]
    log_level: str = "INFO"
    max_request_bytes: int = 65536

    @field_validator("database_url", "database_url_unpooled", "test_database_url")
    @classmethod
    def _use_psycopg_driver(cls, v: str | None) -> str | None:
        return to_psycopg_url(v)

    @property
    def migration_database_url(self) -> str | None:
        return self.database_url_unpooled or self.database_url


@lru_cache
def get_settings() -> Settings:
    return Settings()
