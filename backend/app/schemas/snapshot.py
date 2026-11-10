"""Curated list and raw repository snapshot schemas (the ingestion input format)."""

from datetime import datetime
from pathlib import Path
from typing import Any, Literal, get_args

import yaml
from pydantic import BaseModel, ConfigDict

from app.services.github_client import ReadmeResult

CategorySlug = Literal[
    "ai_ml",
    "llm_agents_mcp",
    "backend",
    "frontend",
    "databases_search",
    "devops_platform",
    "data_engineering",
    "developer_tools",
    "learning",
]

CATEGORY_LABELS: dict[str, str] = {
    "ai_ml": "AI / ML",
    "llm_agents_mcp": "LLMs, agents & MCP",
    "backend": "Backend",
    "frontend": "Frontend",
    "databases_search": "Databases & search",
    "devops_platform": "DevOps & platform",
    "data_engineering": "Data engineering",
    "developer_tools": "Developer tools",
    "learning": "Learning",
}
assert set(CATEGORY_LABELS) == set(get_args(CategorySlug))

README_MAX_CHARS = 40_000


class CuratedEntry(BaseModel):
    model_config = ConfigDict(frozen=True)

    full_name: str
    category: CategorySlug
    featured: bool = False


def load_curated(path: Path) -> list[CuratedEntry]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    entries: list[CuratedEntry] = []
    seen: set[str] = set()
    for category, items in raw.items():
        for item in items or []:
            if isinstance(item, str):
                full_name, featured = item, False
            else:
                full_name, featured = item["repo"], bool(item.get("featured", False))
            key = full_name.lower()
            if key in seen:
                raise ValueError(f"Duplicate curated repository: {full_name}")
            seen.add(key)
            entries.append(CuratedEntry(full_name=full_name, category=category, featured=featured))
    return entries


class RepoSnapshot(BaseModel):
    """GitHub facts for one repository at `fetched_at`, plus curator labels."""

    model_config = ConfigDict(extra="ignore")

    github_id: int
    full_name: str
    owner: str
    name: str
    description: str | None
    html_url: str
    homepage_url: str | None
    topics: list[str]
    primary_language: str | None
    languages: dict[str, int]
    license_spdx: str | None
    license_name: str | None
    stars: int | None
    forks: int | None
    open_issues: int | None
    archived: bool
    default_branch: str | None
    created_at_github: datetime | None
    updated_at_github: datetime | None
    pushed_at_github: datetime | None
    readme_text: str | None
    readme_url: str | None
    readme_truncated: bool
    fetched_at: datetime
    category: CategorySlug
    featured: bool

    @classmethod
    def from_github(
        cls,
        repo: dict[str, Any],
        readme: ReadmeResult | None,
        languages: dict[str, int],
        entry: CuratedEntry,
        fetched_at: datetime,
    ) -> "RepoSnapshot":
        license_info = repo.get("license") or {}
        spdx = license_info.get("spdx_id")
        readme_text = readme.text if readme else None
        truncated = bool(readme_text and len(readme_text) > README_MAX_CHARS)
        if readme_text and truncated:
            readme_text = readme_text[:README_MAX_CHARS]
        return cls(
            github_id=repo["id"],
            full_name=repo["full_name"],
            owner=repo["owner"]["login"],
            name=repo["name"],
            description=repo.get("description") or None,
            html_url=repo["html_url"],
            homepage_url=repo.get("homepage") or None,
            topics=list(repo.get("topics") or []),
            primary_language=repo.get("language"),
            languages=languages,
            license_spdx=spdx if spdx and spdx != "NOASSERTION" else None,
            license_name=license_info.get("name"),
            stars=repo.get("stargazers_count"),
            forks=repo.get("forks_count"),
            open_issues=repo.get("open_issues_count"),
            archived=bool(repo.get("archived", False)),
            default_branch=repo.get("default_branch"),
            created_at_github=repo.get("created_at"),
            updated_at_github=repo.get("updated_at"),
            pushed_at_github=repo.get("pushed_at"),
            readme_text=readme_text,
            readme_url=readme.html_url if readme else None,
            readme_truncated=truncated,
            fetched_at=fetched_at,
            category=entry.category,
            featured=entry.featured,
        )
