"""Backfill recent activity history (stars, forks, commits, releases) from GitHub.

Usage (from backend/):
    uv run python -m scripts.backfill_history [--days 35] [--only owner/name ...]

Idempotent and resumable: rerunning recounts the same days. Stops cleanly when the GitHub
rate limit is exhausted (exit code 2). Requires GITHUB_TOKEN (GraphQL).
"""

import argparse
import logging
import sys
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.session import get_engine
from app.models import Repository
from app.services.activity_client import fetch_activity
from app.services.github_client import (
    GitHubClient,
    GitHubError,
    GitHubNotFound,
    GitHubRateLimited,
)
from app.services.history_service import record_activity


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=int, default=35)
    parser.add_argument("--only", nargs="*", default=None)
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")

    settings = get_settings()
    if not settings.github_token:
        print(
            "GITHUB_TOKEN is required for GraphQL history; skipping (feeds stay popularity-based)."
        )
        return 1
    today = datetime.now(UTC).date()
    since = today - timedelta(days=args.days)
    wanted = {n.lower() for n in args.only} if args.only else None
    done = failed = 0
    star_series = 0
    with (
        Session(get_engine(settings.database_url)) as session,
        GitHubClient(
            settings.github_api_base_url, settings.github_token.get_secret_value()
        ) as client,
    ):
        repos = session.scalars(select(Repository).order_by(Repository.full_name)).all()
        for repo in repos:
            if wanted and repo.full_name.lower() not in wanted:
                continue
            try:
                activity = fetch_activity(client, repo.owner, repo.name, since)
            except GitHubRateLimited as exc:
                print(f"Rate limited (reset {exc.reset_at}); rerun later. done={done}")
                return 2
            except GitHubNotFound:
                print(f"  not found on GitHub: {repo.full_name}")
                failed += 1
                continue
            except GitHubError as exc:
                print(f"  failed: {repo.full_name}: {exc}")
                failed += 1
                continue
            record_activity(session, repo, activity, since, today)
            session.commit()
            done += 1
            star_series += activity.stars_by_day is not None
    print(f"backfilled={done} failed={failed} since={since} star_history={star_series}/{done}")
    if done and not star_series:
        print(
            "Star history unavailable with this token; star growth will come from daily "
            "snapshots (run refresh_repositories daily)."
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
