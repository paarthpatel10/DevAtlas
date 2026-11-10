"""Seed the database from committed snapshots (idempotent).

Order: curated GitHub snapshot -> search-discovered snapshot -> activity history ->
AI reports -> Discover feeds.

Usage (from backend/):
    uv run python -m scripts.seed_demo_data [--dir data/seed_snapshot] [--skip-feeds]
"""

import argparse
import logging
import sys
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy.orm import Session

from app.ai.provider import get_providers
from app.config import BACKEND_DIR, get_settings
from app.db.session import get_engine
from app.schemas.snapshot import curated_by_stem, load_curated
from app.services.discover_ranking import load_ranking_config
from app.services.discover_service import compute_feeds
from app.services.ingestion_service import seed_from_directory
from app.services.snapshot_io import import_history, import_insights

DATA = BACKEND_DIR / "data"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dir", type=Path, default=DATA / "seed_snapshot")
    parser.add_argument("--skip-feeds", action="store_true")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")

    settings = get_settings()
    if not settings.database_url:
        print("DATABASE_URL is not set (.env).")
        return 1
    providers = get_providers(settings)
    with Session(get_engine(settings.database_url)) as session:
        curated = curated_by_stem(load_curated(DATA / "curated_repositories.yaml"))
        report = seed_from_directory(session, args.dir, providers, curated)
        print(
            f"curated: created={report.created} updated={report.updated} "
            f"unchanged={report.unchanged}"
        )
        discovered_dir = DATA / "discovered_snapshot"
        if discovered_dir.exists():
            found = seed_from_directory(
                session,
                discovered_dir,
                providers,
                data_source="github_live",
                discovery_source="search",
            )
            print(
                f"discovered: created={found.created} updated={found.updated} "
                f"unchanged={found.unchanged}"
            )
        histories = import_history(session, DATA / "history_snapshot.json")
        insights = import_insights(session, DATA / "insights_snapshot")
        session.commit()
        print(f"history={histories} insights={insights}")
        if not args.skip_feeds:
            counts = compute_feeds(session, load_ranking_config(), datetime.now(UTC))
            session.commit()
            print("feeds: " + ", ".join(f"{k}={v}" for k, v in counts.items()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
