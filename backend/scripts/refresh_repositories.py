"""Daily refresh: GitHub metadata (+ a daily snapshot) and recent activity per repository.

Usage (from backend/):
    uv run python -m scripts.refresh_repositories [--only owner/name ...]

Run once a day (Task Scheduler / cron), then `compute_feeds`. Metadata updates go through
the normal ingestion (README changes are re-chunked/re-embedded only when they change).
"""

import argparse
import logging
import sys
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ai.provider import get_providers
from app.config import get_settings
from app.db.session import get_engine
from app.models import Repository, RepositoryDailyStat
from app.schemas.snapshot import CuratedEntry, RepoSnapshot
from app.services.activity_client import fetch_activity
from app.services.github_client import (
    GitHubClient,
    GitHubError,
    GitHubNotFound,
    GitHubRateLimited,
)
from app.services.history_service import record_activity
from app.services.ingestion_service import ingest_snapshot

DEFAULT_HISTORY_DAYS = 35
OVERLAP_DAYS = 2  # recount the most recent days: today's counts were partial last run


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--only", nargs="*", default=None)
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")

    settings = get_settings()
    token = settings.github_token.get_secret_value() if settings.github_token else None
    providers = get_providers(settings)
    now = datetime.now(UTC)
    today = now.date()
    wanted = {n.lower() for n in args.only} if args.only else None
    refreshed = failed = 0
    with (
        Session(get_engine(settings.database_url)) as session,
        GitHubClient(settings.github_api_base_url, token) as client,
    ):
        repos = session.scalars(select(Repository).order_by(Repository.full_name)).all()
        for repo in repos:
            if wanted and repo.full_name.lower() not in wanted:
                continue
            entry = CuratedEntry(
                full_name=repo.full_name, category=repo.category, featured=repo.featured
            )
            source = repo.discovery_source
            try:
                data = client.get_repository(repo.full_name)
                readme = client.get_readme(repo.full_name)
                languages = client.get_languages(repo.full_name)
                snap = RepoSnapshot.from_github(data, readme, languages, entry, now)
                ingest_snapshot(session, snap, providers, data_source="github_live")
                repo.discovery_source = source
                if token:
                    last_day = session.scalar(
                        select(func.max(RepositoryDailyStat.day)).where(
                            RepositoryDailyStat.repository_id == repo.id
                        )
                    )
                    since = (
                        min(last_day, today - timedelta(days=OVERLAP_DAYS))
                        if last_day
                        else today - timedelta(days=DEFAULT_HISTORY_DAYS)
                    )
                    activity = fetch_activity(client, repo.owner, repo.name, since)
                    record_activity(session, repo, activity, since, today)
                session.commit()
                refreshed += 1
            except GitHubRateLimited as exc:
                session.rollback()
                print(f"Rate limited (reset {exc.reset_at}); rerun later. refreshed={refreshed}")
                return 2
            except (GitHubNotFound, GitHubError) as exc:
                session.rollback()
                print(f"  failed: {repo.full_name}: {exc}")
                failed += 1
    print(f"refreshed={refreshed} failed={failed}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
