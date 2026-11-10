"""Deterministic demo-mode providers (no credentials, no network).

The hashing embedder is a *lexical* stand-in for a semantic embedding model: it maps
unigrams and bigrams into a fixed-size vector (feature hashing). It is honest about what it
is: the UI labels demo mode, and real embeddings arrive with the Bedrock provider (M3).
"""

import hashlib
import math
import re
from collections.abc import Sequence

from pydantic import BaseModel

TOKEN_RE = re.compile(r"[a-z0-9]+(?:\.[a-z0-9]+)*(?:\+\+|#)?")

STOPWORDS = frozenset(
    """
    a an the and or but if then else of to in on at by for from with without into onto as is
    are was were be been being am i me my we our you your it its this that these those there
    here can could would should will shall may might do does did done have has had having
    not no so than too very just also any some such using use used want wants wanted
    how what which who whom whose when where why about over under up down out
    """.split()
)


def tokenize(text: str) -> list[str]:
    """Lowercase technical tokenizer that keeps `c++`, `c#`, `next.js`, `3.12`."""
    return [t for t in TOKEN_RE.findall(text.lower()) if t not in STOPWORDS]


def _hash(feature: str, person: bytes = b"") -> int:
    return int.from_bytes(
        hashlib.blake2b(feature.encode("utf-8"), digest_size=8, person=person).digest(), "big"
    )


class HashingEmbeddingProvider:
    model_name = "mock-hashing-v1"

    def __init__(self, dimension: int = 1024) -> None:
        self.dimension = dimension

    def _embed(self, text: str) -> list[float]:
        tokens = tokenize(text)
        vector = [0.0] * self.dimension
        features: list[tuple[str, float]] = [(t, 1.0) for t in tokens]
        features += [(f"{a} {b}", 0.5) for a, b in zip(tokens, tokens[1:], strict=False)]
        for feature, weight in features:
            index = _hash(feature) % self.dimension
            sign = 1.0 if _hash(feature, person=b"sign") & 1 else -1.0
            vector[index] += sign * weight
        norm = math.sqrt(sum(x * x for x in vector))
        if norm == 0.0:
            return vector
        return [x / norm for x in vector]

    def embed_texts(self, texts: Sequence[str]) -> list[list[float]]:
        return [self._embed(t) for t in texts]


class MockLLMProvider:
    model_name = "mock"

    def generate_text(self, system: str, prompt: str) -> str:
        raise NotImplementedError("Mock LLM is not used for generation in demo mode")

    def generate_structured(self, system: str, prompt: str, schema: type[BaseModel]) -> BaseModel:
        raise NotImplementedError("Mock LLM is not used for generation in demo mode")
