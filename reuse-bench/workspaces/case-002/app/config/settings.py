"""
Application configuration using Pydantic Settings.
Extended from Milestone 2 to include PostgreSQL, LangSmith, and safety settings.
"""

import os
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Centralized configuration loaded from environment variables and .env file."""

    # ── AWS ────────────────────────────────────────────────────────────────
    AWS_REGION: str = "us-east-1"

    # ── S3 ─────────────────────────────────────────────────────────────────
    S3_BUCKET_NAME: str = "rag-assistant-bucket"

    # ── Bedrock ────────────────────────────────────────────────────────────
    BEDROCK_EMBEDDING_MODEL: str = "amazon.titan-embed-text-v2:0"
    BEDROCK_LLM_MODEL: str = "anthropic.claude-3-sonnet-20240229-v1:0"

    # ── OpenSearch ─────────────────────────────────────────────────────────
    OPENSEARCH_HOST: str = "localhost"
    OPENSEARCH_PORT: int = 9200
    OPENSEARCH_INDEX_NAME: str = "rag-index"
    OPENSEARCH_USERNAME: str = "admin"
    OPENSEARCH_PASSWORD: str = "admin"
    OPENSEARCH_USE_SSL: bool = False
    OPENSEARCH_VERIFY_CERTS: bool = False

    # ── DynamoDB ───────────────────────────────────────────────────────────
    DYNAMODB_TABLE_NAME: str = "rag-chat-history"

    # ── PostgreSQL (NEW for Milestone 3) ───────────────────────────────────
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_DB: str = "assistant_db"
    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: str = "pgadmin"

    # ── LangSmith (NEW for Milestone 3) ────────────────────────────────────
    LANGSMITH_API_KEY: Optional[str] = None
    LANGSMITH_PROJECT: str = "data-assistant"
    LANGSMITH_TRACING: bool = False

    # ── Safety Controls (NEW for Milestone 3) ──────────────────────────────
    MAX_GRAPH_STEPS: int = 5
    RETRY_LIMIT: int = 2
    QUERY_TIMEOUT_SECONDS: int = 30

    # ── API ────────────────────────────────────────────────────────────────
    API_PORT: int = 8000
    API_HOST: str = "0.0.0.0"

    # ── Upload Limits ──────────────────────────────────────────────────────
    MAX_UPLOAD_SIZE_MB: int = 50

    # ── Embedding ──────────────────────────────────────────────────────────
    EMBEDDING_DIMENSION: int = 1024

    # ── Logging ────────────────────────────────────────────────────────────
    LOG_LEVEL: str = "INFO"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def postgres_url(self) -> str:
        """SQLAlchemy-compatible PostgreSQL connection URL."""
        return (
            f"postgresql+psycopg2://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )


settings = Settings()
