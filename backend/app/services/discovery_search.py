"""Find new repositories via GitHub search, within the curated categories.

Only candidates with basic quality signals are kept (not a fork, not archived, a license,
a description); the curated list remains the core of the index.
"""

from datetime import date, timedelta
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel

from app.services.chunking import detect_format
from app.services.discover_ranking import RANKING_PATH, readme_completeness


class SearchConfig(BaseModel):
    per_category_limit: int
    min_stars: int
    max_stars: int
    created_within_days: int
    min_readme_completeness: float
    queries: dict[str, list[str]]


def load_search_config(path: Path = RANKING_PATH) -> SearchConfig:
    return SearchConfig(**yaml.safe_load(path.read_text(encoding="utf-8"))["search"])


def build_queries(cfg: SearchConfig, today: date) -> list[tuple[str, str]]:
    since = today - timedelta(days=cfg.created_within_days)
    qualifiers = f"created:>={since.isoformat()} stars:>={cfg.min_stars} fork:false archived:false"
    return [
        (category, f"{query} {qualifiers}")
        for category, queries in cfg.queries.items()
        for query in queries
    ]


def _acceptable(repo: dict[str, Any], cfg: SearchConfig) -> bool:
    owner, _, name = (repo.get("full_name") or "/").partition("/")
    return (
        not repo.get("fork")
        and not repo.get("archived")
        and bool(repo.get("license"))
        and bool((repo.get("description") or "").strip())
        and owner.lower() != name.lower()  # profile README repositories
        and (repo.get("stargazers_count") or 0) <= cfg.max_stars
    )


def documented_enough(readme_text: str, readme_url: str | None, cfg: SearchConfig) -> bool:
    fmt = detect_format(readme_url)
    return readme_completeness(readme_text, fmt) >= cfg.min_readme_completeness


def select_candidates(
    results: list[tuple[str, list[dict[str, Any]]]],
    known_github_ids: set[int],
    cfg: SearchConfig,
) -> list[tuple[str, dict[str, Any]]]:
    chosen: list[tuple[str, dict[str, Any]]] = []
    taken: set[int] = set(known_github_ids)
    per_category: dict[str, int] = {}
    for category, items in results:
        for repo in items:
            if per_category.get(category, 0) >= cfg.per_category_limit:
                break
            if repo["id"] in taken or not _acceptable(repo, cfg):
                continue
            taken.add(repo["id"])
            per_category[category] = per_category.get(category, 0) + 1
            chosen.append((category, repo))
    return chosen
