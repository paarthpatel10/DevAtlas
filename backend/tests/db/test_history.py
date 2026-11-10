from datetime import UTC, date, datetime, timedelta

from sqlalchemy import func, select

from app.models import Repository, RepositoryDailyStat, RepositoryRelease, RepositorySnapshot
from app.services.activity_client import ReleaseInfo, RepoActivity
from app.services.history_service import Growth, growth, record_activity
from app.services.ingestion_service import ingest_snapshot
from tests.factories import load_fixture

TODAY = date(2026, 11, 10)


def activity(stars=None, forks=None, commits=None, stars_capped=False, releases=()):
    return RepoActivity(
        stars_by_day=stars,
        stars_capped=stars_capped,
        forks_by_day=forks,
        forks_capped=False,
        commits_by_day=commits,
        releases=list(releases),
    )


def repo(db_session, providers) -> Repository:
    result = ingest_snapshot(db_session, load_fixture("acme__jobs.json"), providers)
    return db_session.get(Repository, result.repository_id)


def test_event_sum_over_window(db_session, providers):
    r = repo(db_session, providers)
    since = TODAY - timedelta(days=35)
    record_activity(
        db_session,
        r,
        activity(stars={TODAY: 5, TODAY - timedelta(days=3): 7, TODAY - timedelta(days=20): 100}),
        since,
        TODAY,
    )
    assert growth(db_session, r, "stars", 7, TODAY) == Growth(12, False, "events")
    assert growth(db_session, r, "stars", 30, TODAY) == Growth(112, False, "events")
    assert r.star_history_since == since


def test_window_older_than_coverage_falls_back_to_snapshot_diff(db_session, providers):
    r = repo(db_session, providers)  # fixture snapshot: 1200 stars on 2026-11-10
    db_session.add(
        RepositorySnapshot(
            repository_id=r.id,
            stars=1000,
            forks=5,
            open_issues=0,
            snapshot_at=datetime(2026, 11, 3, 9, tzinfo=UTC),
        )
    )
    db_session.flush()
    assert growth(db_session, r, "stars", 7, TODAY) == Growth(200, False, "snapshots")


def test_no_coverage_gives_unknown_not_zero(db_session, providers):
    r = repo(db_session, providers)
    assert growth(db_session, r, "stars", 7, TODAY) == Growth(None, False, None)
    assert growth(db_session, r, "commits", 7, TODAY) == Growth(None, False, None)


def test_capped_days_make_lower_bound(db_session, providers):
    r = repo(db_session, providers)
    record_activity(
        db_session,
        r,
        activity(stars={TODAY: 3000}, stars_capped=True),
        TODAY - timedelta(days=35),
        TODAY,
    )
    assert growth(db_session, r, "stars", 7, TODAY) == Growth(3000, True, "events")


def test_collected_series_without_events_counts_zero(db_session, providers):
    r = repo(db_session, providers)
    record_activity(db_session, r, activity(forks={}), TODAY - timedelta(days=35), TODAY)
    assert growth(db_session, r, "forks", 7, TODAY) == Growth(0, False, "events")


def test_record_activity_is_idempotent_and_keeps_earliest_coverage(db_session, providers):
    r = repo(db_session, providers)
    release = ReleaseInfo("v1.0", "1.0", datetime(2026, 11, 1, tzinfo=UTC), "https://x/v1.0")
    data = activity(commits={TODAY: 4}, releases=[release])
    record_activity(db_session, r, data, TODAY - timedelta(days=35), TODAY)
    record_activity(db_session, r, data, TODAY - timedelta(days=2), TODAY)
    days = db_session.scalar(
        select(func.count())
        .select_from(RepositoryDailyStat)
        .where(RepositoryDailyStat.repository_id == r.id)
    )
    assert days == 36  # one row per day from coverage start to today, no duplicates
    assert db_session.scalar(select(func.count()).select_from(RepositoryRelease)) == 1
    assert r.commit_history_since == TODAY - timedelta(days=35)
    assert growth(db_session, r, "commits", 7, TODAY) == Growth(4, False, "events")


def test_uncollected_star_series_leaves_coverage_empty(db_session, providers):
    r = repo(db_session, providers)
    record_activity(
        db_session, r, activity(stars=None, forks={TODAY: 1}), TODAY - timedelta(days=35), TODAY
    )
    assert r.star_history_since is None
    assert r.fork_history_since == TODAY - timedelta(days=35)
    row = db_session.scalar(select(RepositoryDailyStat).where(RepositoryDailyStat.day == TODAY))
    assert row.stars_gained is None and row.forks_gained == 1
