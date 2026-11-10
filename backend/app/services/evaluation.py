"""Reproducible relevance evaluation for the recommendation pipeline (spec section 12)."""

import uuid
from dataclasses import dataclass
from pathlib import Path

import yaml
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.ai.provider import Providers
from app.ai.vocabulary import Vocabulary
from app.config import Settings
from app.schemas.recommendation import RecommendRequest
from app.services.recommendation_service import recommend
from app.services.users import DEMO_USER_ID


class BenchmarkCase(BaseModel):
    id: str
    query: str
    expected: list[str]
    must_have: list[str] = []


@dataclass(frozen=True)
class QueryResult:
    id: str
    ranked: list[str]
    hit_at_5: bool
    rr: float
    p_at_5: float


@dataclass(frozen=True)
class BenchmarkReport:
    per_query: list[QueryResult]
    hit_rate_at_5: float
    mrr: float
    mean_p_at_5: float


def _lower(items: set[str] | list[str]) -> set[str]:
    return {i.lower() for i in items}


def hit_at_k(ranked: list[str], expected: set[str], k: int) -> bool:
    return bool(_lower(ranked[:k]) & _lower(expected))


def reciprocal_rank(ranked: list[str], expected: set[str]) -> float:
    wanted = _lower(expected)
    for position, name in enumerate(ranked, start=1):
        if name.lower() in wanted:
            return 1.0 / position
    return 0.0


def precision_at_k(ranked: list[str], expected: set[str], k: int) -> float:
    return len(_lower(ranked[:k]) & _lower(expected)) / k


def load_benchmark(path: Path) -> list[BenchmarkCase]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or []
    return [BenchmarkCase(**item) for item in raw]


def run_benchmark(
    session: Session,
    providers: Providers,
    vocab: Vocabulary,
    settings: Settings,
    path: Path,
    user_id: uuid.UUID = DEMO_USER_ID,
) -> BenchmarkReport:
    results: list[QueryResult] = []
    for case in load_benchmark(path):
        response = recommend(
            session,
            RecommendRequest(query=case.query, max_results=5),
            providers,
            vocab,
            settings,
            user_id,
        )
        ranked = [r.repository.full_name for r in response.results]
        expected = set(case.expected)
        results.append(
            QueryResult(
                id=case.id,
                ranked=ranked,
                hit_at_5=hit_at_k(ranked, expected, 5),
                rr=reciprocal_rank(ranked, expected),
                p_at_5=precision_at_k(ranked, expected, 5),
            )
        )
    n = len(results) or 1
    return BenchmarkReport(
        per_query=results,
        hit_rate_at_5=sum(r.hit_at_5 for r in results) / n,
        mrr=sum(r.rr for r in results) / n,
        mean_p_at_5=sum(r.p_at_5 for r in results) / n,
    )
