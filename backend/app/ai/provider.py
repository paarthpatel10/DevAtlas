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
    llm_available: bool = False


def get_providers(settings: Settings) -> Providers:
    from app.ai.mock_providers import HashingEmbeddingProvider, MockLLMProvider

    # Search embeddings stay deterministic/lexical in every mode (see Discover design §2).
    embeddings = HashingEmbeddingProvider(dimension=settings.embedding_dim)
    key = settings.gemini_api_key.get_secret_value() if settings.gemini_api_key else None
    provider = settings.ai_provider
    if provider == "auto":
        provider = "gemini" if key else "mock"
    if provider == "mock":
        return Providers(llm=MockLLMProvider(), embeddings=embeddings, llm_available=False)
    if provider == "gemini" and key:
        from app.ai.gemini_provider import GeminiLLMProvider

        llm = GeminiLLMProvider(key, settings.gemini_model, settings.gemini_base_url)
        return Providers(llm=llm, embeddings=embeddings, llm_available=True)
    message = (
        "AI_PROVIDER=gemini needs a Gemini API key (GEMINI_API_KEY)."
        if provider == "gemini"
        else "Bedrock provider is not implemented yet; use AI_PROVIDER=auto or gemini."
    )
    raise AppError(message, code="provider_not_available", status_code=500)
