from datetime import UTC, date, datetime

from sqlalchemy import func, select

from app.models import GitHubTrendingObservation
from app.services.github_trending import TrendingRepo
from app.services.trending_tracker import link_observations, record_trending

DAY = date(2026, 11, 10)
NOW = datetime(2026, 11, 10, 9, tzinfo=UTC)


def trending(name: str, rank: int, stars: int) -> TrendingRepo:
    return TrendingRepo(
        rank=rank,
        full_name=name,
        description=None,
        language="Python",
        stars_total=1000,
        forks_total=10,
        stars_today=stars,
    )


def count(session) -> int:
    return session.scalar(select(func.count()).select_from(GitHubTrendingObservation))


def test_record_is_idempotent_links_known_and_reports_unknown(seeded):
    seeded.execute(GitHubTrendingObservation.__table__.delete())
    page = [trending("ACME/Jobs", 1, 500), trending("someone/new-thing", 2, 300)]
    unknown = record_trending(seeded, "", page, DAY, NOW)
    record_trending(seeded, "", page, DAY, NOW)  # rerun the same day: no duplicates
    record_trending(seeded, "python", page[:1], DAY, NOW)
    seeded.commit()
    assert unknown == ["someone/new-thing"]
    assert count(seeded) == 3
    linked = seeded.scalars(
        select(GitHubTrendingObservation).where(GitHubTrendingObservation.full_name == "ACME/Jobs")
    ).all()
    assert all(o.repository_id is not None for o in linked)
    unlinked = seeded.scalar(
        select(GitHubTrendingObservation).where(
            GitHubTrendingObservation.full_name == "someone/new-thing"
        )
    )
    assert unlinked.repository_id is None and unlinked.stars_today == 300


def test_link_observations_after_ingesting_new_repository(seeded):
    seeded.execute(GitHubTrendingObservation.__table__.delete())
    record_trending(seeded, "", [trending("acme/ui", 1, 50)], DAY, NOW)
    seeded.execute(GitHubTrendingObservation.__table__.update().values(repository_id=None))
    assert link_observations(seeded) == 1
    seeded.commit()
    assert seeded.scalar(select(GitHubTrendingObservation.repository_id)) is not None
