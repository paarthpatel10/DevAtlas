from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, Field, StringConstraints

from app.ai.insights import Citation, GroundedReport, Idea
from app.schemas.repository import RepositoryCard


class InsightsOut(BaseModel):
    report: GroundedReport
    generated: bool
    model_name: str | None
    generated_at: datetime | None
    stale: bool
    labels: list[str]
    why_trending: list[str]
    related: list[RepositoryCard]


class BuildIdeasIn(BaseModel):
    more: bool = False


class BuildIdeasOut(BaseModel):
    ideas: list[Idea]
    generated: bool
    model_name: str | None
    cached: bool


class AskIn(BaseModel):
    question: Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=500)]


class AskOut(BaseModel):
    covered: bool
    answer: str
    citations: list[Citation]
    model_name: str | None
    cached: bool


class CompareIn(BaseModel):
    repositories: Annotated[list[str], Field(min_length=2, max_length=4)]


class CompareRow(BaseModel):
    repository: RepositoryCard
    values: dict[str, str | None]
    fits_when: list[str]


class CompareOut(BaseModel):
    dimensions: list[str]
    rows: list[CompareRow]
