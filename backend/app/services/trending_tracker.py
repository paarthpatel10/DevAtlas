"""Store GitHub Trending observations and link them to indexed repositories."""

import uuid
from datetime import date, datetime

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models import GitHubTrendingObservation, Repository
from app.services.github_trending import TrendingRepo


def _repo_ids_by_name(session: Session, names: list[str]) -> dict[str, uuid.UUID]:
    lowered = [n.lower() for n in names]
    rows = session.execute(
        select(func.lower(Repository.full_name), Repository.id).where(
            func.lower(Repository.full_name).in_(lowered)
        )
    ).all()
    return dict(rows)


def record_trending(
    session: Session, scope: str, repos: list[TrendingRepo], day: date, now: datetime
) -> list[str]:
    """Upsert one page's observations; returns names not yet in the index."""
    known = _repo_ids_by_name(session, [r.full_name for r in repos])
    unknown: list[str] = []
    for repo in repos:
        repo_id = known.get(repo.full_name.lower())
        if repo_id is None:
            unknown.append(repo.full_name)
        values = {
            "rank": repo.rank,
            "repository_id": repo_id,
            "stars_today": repo.stars_today,
            "stars_total": repo.stars_total,
            "forks_total": repo.forks_total,
            "observed_at": now,
        }
        session.execute(
            insert(GitHubTrendingObservation)
            .values(id=uuid.uuid4(), day=day, scope=scope, full_name=repo.full_name, **values)
            .on_conflict_do_update(index_elements=["day", "scope", "full_name"], set_=values)
        )
    session.flush()
    return unknown


def link_observations(session: Session) -> int:
    """Attach repository ids to observations recorded before the repository was indexed."""
    pending = session.scalars(
        select(GitHubTrendingObservation.full_name)
        .where(GitHubTrendingObservation.repository_id.is_(None))
        .distinct()
    ).all()
    known = _repo_ids_by_name(session, list(pending))
    linked = 0
    for name in pending:
        repo_id = known.get(name.lower())
        if repo_id is None:
            continue
        result = session.execute(
            update(GitHubTrendingObservation)
            .where(
                GitHubTrendingObservation.full_name == name,
                GitHubTrendingObservation.repository_id.is_(None),
            )
            .values(repository_id=repo_id)
        )
        linked += result.rowcount or 0
    session.flush()
    return linked
