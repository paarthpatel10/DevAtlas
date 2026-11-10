"""Collect recent repository activity (stars, forks, commits, releases) from GitHub.

GraphQL is used where REST cannot help: stargazers and forks ordered newest-first reach
recent events even for very large repositories. Every series degrades independently: a
series that cannot be read is `None` (unknown), never an empty count.
"""

import logging
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any

from app.services.github_client import GitHubClient, GitHubForbidden

logger = logging.getLogger(__name__)

_STARS = """
query($owner: String!, $name: String!, $after: String) {
  repository(owner: $owner, name: $name) {
    stargazers(first: 100, after: $after, orderBy: {field: STARRED_AT, direction: DESC}) {
      pageInfo { hasNextPage endCursor }
      edges { starredAt }
    }
  }
}"""

_FORKS = """
query($owner: String!, $name: String!, $after: String) {
  repository(owner: $owner, name: $name) {
    forks(first: 100, after: $after, orderBy: {field: CREATED_AT, direction: DESC}) {
      pageInfo { hasNextPage endCursor }
      nodes { createdAt }
    }
  }
}"""

_RELEASES = """
query($owner: String!, $name: String!) {
  repository(owner: $owner, name: $name) {
    releases(first: 20, orderBy: {field: CREATED_AT, direction: DESC}) {
      nodes { tagName name publishedAt url }
    }
  }
}"""


@dataclass(frozen=True)
class ReleaseInfo:
    tag: str
    name: str | None
    published_at: datetime | None
    url: str | None


@dataclass(frozen=True)
class RepoActivity:
    stars_by_day: dict[date, int] | None
    stars_capped: bool
    forks_by_day: dict[date, int] | None
    forks_capped: bool
    commits_by_day: dict[date, int] | None
    releases: list[ReleaseInfo]


def _parse_ts(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


def _count_by_day(
    client: GitHubClient,
    query: str,
    connection: str,
    items_key: str,
    ts_key: str,
    owner: str,
    name: str,
    since: date,
    max_pages: int,
) -> tuple[dict[date, int], bool]:
    counts: dict[date, int] = {}
    after: str | None = None
    for _ in range(max_pages):
        data = client.graphql(query, {"owner": owner, "name": name, "after": after})
        conn = (data.get("repository") or {}).get(connection) or {}
        reached_since = False
        for item in conn.get(items_key) or []:
            day = _parse_ts(item[ts_key]).date()
            if day < since:
                reached_since = True
                break
            counts[day] = counts.get(day, 0) + 1
        page_info = conn.get("pageInfo") or {}
        if reached_since or not page_info.get("hasNextPage"):
            return counts, False
        after = page_info.get("endCursor")
    return counts, True  # stopped by the page cap: counts are a lower bound


def _commits_by_day(weeks: list[dict[str, Any]], since: date) -> dict[date, int]:
    counts: dict[date, int] = {}
    for week in weeks:
        start = datetime.fromtimestamp(int(week["week"]), UTC).date()
        for offset, commits in enumerate(week.get("days") or []):
            day = start + timedelta(days=offset)
            if day >= since and commits:
                counts[day] = int(commits)
    return counts


def fetch_activity(
    client: GitHubClient, owner: str, name: str, since: date, *, max_pages: int = 30
) -> RepoActivity:
    full_name = f"{owner}/{name}"
    stars: dict[date, int] | None
    try:
        stars, stars_capped = _count_by_day(
            client, _STARS, "stargazers", "edges", "starredAt", owner, name, since, max_pages
        )
    except GitHubForbidden:
        logger.info("Stargazer history not accessible with this token for %s", full_name)
        stars, stars_capped = None, False

    forks: dict[date, int] | None
    try:
        forks, forks_capped = _count_by_day(
            client, _FORKS, "forks", "nodes", "createdAt", owner, name, since, max_pages
        )
    except GitHubForbidden:
        forks, forks_capped = None, False

    data = client.graphql(_RELEASES, {"owner": owner, "name": name})
    nodes = (((data.get("repository") or {}).get("releases") or {}).get("nodes")) or []
    releases = [
        ReleaseInfo(
            tag=n["tagName"],
            name=n.get("name"),
            published_at=_parse_ts(n["publishedAt"]) if n.get("publishedAt") else None,
            url=n.get("url"),
        )
        for n in nodes
    ]

    weeks = client.get_commit_activity(full_name)
    commits = None if weeks is None else _commits_by_day(weeks, since)
    return RepoActivity(
        stars_by_day=stars,
        stars_capped=stars_capped,
        forks_by_day=forks,
        forks_capped=forks_capped,
        commits_by_day=commits,
        releases=releases,
    )
