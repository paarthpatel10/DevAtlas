from datetime import UTC, date, datetime, timedelta

from sqlalchemy import delete, func, select

from app.models import (
    Repository,
    RepositoryChunk,
    RepositoryDailyStat,
    RepositoryInsight,
    RepositoryRelease,
)
from app.services.activity_client import ReleaseInfo, RepoActivity
from app.services.history_service import record_activity
from app.services.ingestion_service import seed_from_directory
from app.services.insight_service import generate_insight, get_report
from app.services.snapshot_io import (
    export_history,
    export_insights,
    import_history,
    import_insights,
)
from tests.factories import FIXTURES_DIR
from tests.fakes import FakeLLM, report_citing_first_source

TODAY = date(2026, 11, 10)


def count(session, model) -> int:
    return session.scalar(select(func.count()).select_from(model))


def jobs(session) -> Repository:
    return session.scalar(select(Repository).where(Repository.full_name == "acme/jobs"))


def prepare(session, providers):
    seed_from_directory(session, FIXTURES_DIR, providers)
    repo = jobs(session)
    record_activity(
        session,
        repo,
        RepoActivity(
            stars_by_day=None,
            stars_capped=False,
            forks_by_day={TODAY: 2},
            forks_capped=False,
            commits_by_day={TODAY: 5},
            releases=[ReleaseInfo("v1", "1", datetime(2026, 11, 1, tzinfo=UTC), None)],
        ),
        TODAY - timedelta(days=10),
        TODAY,
    )
    generate_insight(
        session, repo, FakeLLM(report_citing_first_source), datetime(2026, 11, 10, tzinfo=UTC)
    )
    session.commit()


def test_history_round_trip_and_idempotent(db_session, providers, tmp_path):
    prepare(db_session, providers)
    path = tmp_path / "history.json"
    export_history(db_session, path)
    before = count(db_session, RepositoryDailyStat)
    db_session.execute(delete(RepositoryDailyStat))
    db_session.execute(delete(RepositoryRelease))
    jobs(db_session).fork_history_since = None
    db_session.commit()

    import_history(db_session, path)
    import_history(db_session, path)
    db_session.commit()
    assert count(db_session, RepositoryDailyStat) == before == 11
    assert count(db_session, RepositoryRelease) == 1
    repo = jobs(db_session)
    assert repo.fork_history_since == TODAY - timedelta(days=10)
    assert repo.star_history_since is None


def test_insights_round_trip_and_staleness(db_session, providers, tmp_path):
    prepare(db_session, providers)
    export_insights(db_session, tmp_path)
    assert (tmp_path / "acme__jobs.json").exists()
    db_session.execute(delete(RepositoryInsight))
    db_session.commit()

    import_insights(db_session, tmp_path)
    import_insights(db_session, tmp_path)
    db_session.commit()
    assert count(db_session, RepositoryInsight) == 1
    report, insight, stale = get_report(db_session, jobs(db_session))
    assert report.generated and insight.model_name == "fake:llm" and stale is False

    chunk = db_session.scalar(
        select(RepositoryChunk).where(
            RepositoryChunk.repository_id == jobs(db_session).id, RepositoryChunk.position == 0
        )
    )
    chunk.content_hash = "readme changed since export"
    db_session.flush()
    assert get_report(db_session, jobs(db_session))[2] is True  # loaded but flagged stale


def test_trending_observations_round_trip(db_session, providers, tmp_path):
    from app.models import GitHubTrendingObservation
    from app.services.github_trending import TrendingRepo
    from app.services.snapshot_io import export_trending, import_trending
    from app.services.trending_tracker import record_trending

    seed_from_directory(db_session, FIXTURES_DIR, providers)
    record_trending(
        db_session,
        "",
        [TrendingRepo(1, "acme/jobs", None, "Python", 10, 1, 77)],
        TODAY,
        datetime(2026, 11, 10, tzinfo=UTC),
    )
    db_session.commit()
    path = tmp_path / "trending.json"
    export_trending(db_session, path)
    db_session.execute(delete(GitHubTrendingObservation))
    db_session.commit()
    import_trending(db_session, path)
    import_trending(db_session, path)
    db_session.commit()
    rows = db_session.scalars(select(GitHubTrendingObservation)).all()
    assert len(rows) == 1 and rows[0].stars_today == 77 and rows[0].repository_id is not None
