"""Schemas for the evidence-backed recommendation pipeline (spec 6.4, 6.5)."""

from typing import Annotated, Literal

from pydantic import BaseModel, Field, StringConstraints

from app.schemas.repository import RepositoryCard


class QueryIntent(BaseModel):
    goal: str
    requirements: list[str]
    constraints: list[str]
    known_stack: dict[str, list[str]]
    category: str | None
    preferred_license: str | None
    keywords: list[str]
    inferred: list[str]
    clarifying_question: str | None


class Evidence(BaseModel):
    snippet: str
    source_url: str | None
    section_title: str | None
    source_type: str


class RequirementCheck(BaseModel):
    requirement: str
    status: Literal["evidenced", "not_established"]
    evidence: list[Evidence]


class CompatibilityNote(BaseModel):
    stack_item: str
    status: Literal["evidenced", "inferred", "not_established"]
    note: str
    evidence: Evidence | None


class RetrievalSignals(BaseModel):
    keyword_rank: int | None
    semantic_rank: int | None
    rrf_score: float
    requirements_evidenced: int
    requirements_total: int


class Recommendation(BaseModel):
    rank: int
    repository: RepositoryCard
    reasons: list[str]
    requirements: list[RequirementCheck]
    compatibility: list[CompatibilityNote]
    limitations: list[str]
    signals: RetrievalSignals


class FilterIn(BaseModel):
    category: Annotated[str | None, Field(max_length=50)] = None
    language: Annotated[str | None, Field(max_length=100)] = None
    license: Annotated[str | None, Field(max_length=100)] = None


class RecommendRequest(BaseModel):
    query: Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=1000)]
    max_results: Annotated[int, Field(ge=1, le=10)] = 5
    filters: FilterIn | None = None


class PipelineInfo(BaseModel):
    provider: str
    embedding_model: str
    rrf_k: int
    keyword_candidates: int
    semantic_candidates: int
    notes: list[str]


class RecommendResponse(BaseModel):
    query: str
    intent: QueryIntent
    results: list[Recommendation]
    pipeline: PipelineInfo
    clarifying_question: str | None
