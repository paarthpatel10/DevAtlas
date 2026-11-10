"""Provider abstraction: business logic depends on these interfaces, never on an SDK."""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from pydantic import BaseModel

from app.config import Settings
from app.core.errors import AppError


class EmbeddingProvider(Protocol):
    model_name: str
    dimension: int

    def embed_texts(self, texts: Sequence[str]) -> list[list[float]]: ...


class LLMProvider(Protocol):
    model_name: str

    def generate_text(self, system: str, prompt: str) -> str: ...

    def generate_structured(
        self, system: str, prompt: str, schema: type[BaseModel]
    ) -> BaseModel: ...


@dataclass(frozen=True)
class Providers:
    llm: LLMProvider
    embeddings: EmbeddingProvider


def get_providers(settings: Settings) -> Providers:
    if settings.ai_provider == "mock":
        from app.ai.mock_providers import HashingEmbeddingProvider, MockLLMProvider

        return Providers(
            llm=MockLLMProvider(),
            embeddings=HashingEmbeddingProvider(dimension=settings.embedding_dim),
        )
    raise AppError(
        "Bedrock provider arrives in milestone M3; set AI_PROVIDER=mock",
        code="provider_not_available",
        status_code=500,
    )
