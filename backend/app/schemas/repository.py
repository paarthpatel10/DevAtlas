"""API response schemas for repositories. Unknown values are explicit nulls, never guesses."""

import uuid
from datetime import datetime

from pydantic import BaseModel

from app.schemas.analysis import RepositoryAnalysisOut


class RepositoryCard(BaseModel):
    id: uuid.UUID
    owner: str
    name: str
    full_name: str
    description: str | None
    html_url: str
    primary_language: str | None
    topics: list[str]
    license_spdx: str | None
    license_name: str | None
    stars: int | None
    forks: int | None
    pushed_at_github: datetime | None
    archived: bool
    category: str
    category_label: str
    featured: bool
    data_source: str
    source_fetched_at: datetime
    is_saved: bool


class AnalysisView(RepositoryAnalysisOut):
    generated_by_label: str


class Signal(BaseModel):
    label: str
    value: str
    explanation: str


class SourceRef(BaseModel):
    label: str
    url: str


class RepositoryDetail(RepositoryCard):
    homepage_url: str | None
    readme_url: str | None
    languages: dict[str, int]
    open_issues: int | None
    created_at_github: datetime | None
    updated_at_github: datetime | None
    default_branch: str | None
    readme_truncated: bool
    analysis: AnalysisView | None
    maintenance_signals: list[Signal]
    sources: list[SourceRef]


class CategoryFacet(BaseModel):
    value: str
    label: str
    count: int


class FacetValue(BaseModel):
    value: str
    count: int


class Facets(BaseModel):
    categories: list[CategoryFacet]
    languages: list[FacetValue]
    licenses: list[FacetValue]


class SaveState(BaseModel):
    saved: bool
