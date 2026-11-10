import math

import pytest

from app.ai.mock_providers import HashingEmbeddingProvider, tokenize
from app.ai.provider import get_providers
from app.config import Settings
from app.core.errors import AppError


def dot(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b, strict=True))


def test_embeddings_are_deterministic_normalized_and_sized():
    p = HashingEmbeddingProvider(dimension=1024)
    a1, a2 = p.embed_texts(["Distributed task queue with retries"] * 2)
    assert a1 == a2
    assert len(a1) == 1024
    assert math.isclose(sum(x * x for x in a1), 1.0, rel_tol=1e-9)


def test_embeddings_stable_across_instances():
    text = "background jobs for FastAPI"
    assert HashingEmbeddingProvider().embed_texts([text]) == HashingEmbeddingProvider().embed_texts(
        [text]
    )


def test_related_text_is_closer_than_unrelated():
    p = HashingEmbeddingProvider()
    q, near, far = p.embed_texts(
        [
            "background task queue with retries",
            "a task queue for background jobs, supports retries",
            "css utility classes for styling buttons",
        ]
    )
    assert dot(q, near) > dot(q, far)


def test_empty_text_gives_zero_vector():
    assert set(HashingEmbeddingProvider().embed_texts(["  !!  "])[0]) == {0.0}


def test_tokenizer_keeps_cpp_and_nextjs():
    assert {"c++", "next.js"} <= set(tokenize("C++ and Next.js"))


def test_tokenizer_drops_stopwords():
    assert tokenize("I need a queue for the app") == ["need", "queue", "app"]


def test_mock_provider_selected_by_default():
    providers = get_providers(Settings(_env_file=None))
    assert providers.embeddings.model_name == "mock-hashing-v1"
    assert providers.embeddings.dimension == 1024


def test_bedrock_not_available_in_m1():
    with pytest.raises(AppError) as e:
        get_providers(Settings(ai_provider="bedrock", _env_file=None))
    assert e.value.code == "provider_not_available"
