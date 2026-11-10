"""Repository history: daily event counts, releases, and honest growth windows.

Growth is computed from event history (per-day counts) when the window is fully covered,
otherwise from two metadata snapshots spanning the window; with neither, it is unknown
(`value=None`), never zero.
"""

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from typing import Literal

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models import Repository, RepositoryDailyStat, RepositoryRelease, RepositorySnapshot
from app.services.activity_client import RepoActivity

Metric = Literal["stars", "forks", "commits"]

_COLUMN = {"stars": "stars_gained", "forks": "forks_gained", "commits": "commits"}
_CAPPED = {"stars": "stars_capped", "forks": "forks_capped"}
_COVERAGE = {
    "stars": "star_history_since",
    "forks": "fork_history_since",
    "commits": "commit_history_since",
}


@dataclass(frozen=True)
class Growth:
    value: int | None
    lower_bound: bool
    basis: Literal["events", "snapshots"] | None


def _days(since: date, today: date) -> list[date]:
    return [since + timedelta(days=i) for i in range((today - since).days + 1)]


def record_activity(
    session: Session, repo: Repository, activity: RepoActivity, since: date, today: date
) -> None:
    """Store per-day counts for every collected series (missing days in a collected series
    are real zeros), upsert releases, and extend coverage start dates."""
    series = {
        "stars": (activity.stars_by_day, activity.stars_capped),
        "forks": (activity.forks_by_day, activity.forks_capped),
        "commits": (activity.commits_by_day, False),
    }
    collected = {m: v for m, v in series.items() if v[0] is not None}
    if collected:
        for day in _days(since, today):
            values: dict[str, object] = {}
            for metric, (by_day, capped) in collected.items():
                values[_COLUMN[metric]] = (by_day or {}).get(day, 0)
                if metric in _CAPPED:
                    values[_CAPPED[metric]] = bool(capped and (by_day or {}).get(day))
            stmt = insert(RepositoryDailyStat).values(repository_id=repo.id, day=day, **values)
            session.execute(
                stmt.on_conflict_do_update(index_elements=["repository_id", "day"], set_=values)
            )
        for metric in collected:
            current = getattr(repo, _COVERAGE[metric])
            if current is None or since < current:
                setattr(repo, _COVERAGE[metric], since)

    for release in activity.releases:
        stmt = insert(RepositoryRelease).values(
            repository_id=repo.id,
            tag=release.tag,
            name=release.name,
            published_at=release.published_at,
            url=release.url,
        )
        session.execute(
            stmt.on_conflict_do_update(
                index_elements=["repository_id", "tag"],
                set_={
                    "name": release.name,
                    "published_at": release.published_at,
                    "url": release.url,
                },
            )
        )
    session.flush()


def _snapshot_value(snapshot: RepositorySnapshot, metric: Metric) -> int | None:
    return snapshot.stars if metric == "stars" else snapshot.forks


def growth(session: Session, repo: Repository, metric: Metric, days: int, today: date) -> Growth:
    window_start = today - timedelta(days=days)
    coverage: date | None = getattr(repo, _COVERAGE[metric])
    if coverage is not None and coverage <= window_start:
        column = getattr(RepositoryDailyStat, _COLUMN[metric])
        filters = (
            RepositoryDailyStat.repository_id == repo.id,
            RepositoryDailyStat.day > window_start,
            RepositoryDailyStat.day <= today,
        )
        total = session.scalar(select(func.coalesce(func.sum(column), 0)).where(*filters))
        capped = False
        if metric in _CAPPED:
            capped_column = getattr(RepositoryDailyStat, _CAPPED[metric])
            capped = bool(session.scalar(select(func.bool_or(capped_column)).where(*filters)))
        return Growth(int(total or 0), capped, "events")

    if metric in ("stars", "forks"):
        start_dt = datetime.combine(window_start, time.max, tzinfo=UTC)
        earliest_ok = datetime.combine(window_start - timedelta(days=1), time.min, tzinfo=UTC)
        old = session.scalar(
            select(RepositorySnapshot)
            .where(
                RepositorySnapshot.repository_id == repo.id,
                RepositorySnapshot.snapshot_at <= start_dt,
                RepositorySnapshot.snapshot_at >= earliest_ok,
            )
            .order_by(RepositorySnapshot.snapshot_at.desc())
        )
        latest = session.scalar(
            select(RepositorySnapshot)
            .where(RepositorySnapshot.repository_id == repo.id)
            .order_by(RepositorySnapshot.snapshot_at.desc())
        )
        if old is not None and latest is not None and old.id != latest.id:
            before, after = _snapshot_value(old, metric), _snapshot_value(latest, metric)
            if before is not None and after is not None:
                return Growth(after - before, False, "snapshots")
    return Growth(None, False, None)
