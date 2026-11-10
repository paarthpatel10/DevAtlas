"""Strict schema for structured repository analysis (spec 6.2)."""

from typing import Literal

from pydantic import BaseModel, ConfigDict

Maturity = Literal["unknown", "experimental", "active", "mature", "inactive"]


class Capability(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    description: str
    evidence: list[str]
    confidence: Literal["high", "medium", "low"]


class RepositoryAnalysisOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    summary: str | None
    problem_solved: str | None
    category: str | None
    subcategory: str | None
    capabilities: list[Capability]
    use_cases: list[str]
    supported_languages: list[str]
    integrations: list[str]
    requirements: list[str]
    limitations: list[str]
    maturity: Maturity
    target_users: list[str]
    keywords: list[str]
    analysis_version: str
    model_name: str
    prompt_version: str
