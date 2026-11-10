"""Discover new repositories with GitHub search and add them to the index.

Usage (from backend/):
    uv run python -m scripts.discover_new [--dry-run]

Each accepted repository is snapshotted to data/discovered_snapshot/ (so a fresh database
can be seeded offline) and ingested with discovery_source="search".
"""

import argparse
import logging
import sys
import time
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.provider import get_providers
from app.config import BACKEND_DIR, get_settings
from app.db.session import get_engine
from app.models import Repository
from app.schemas.snapshot import CuratedEntry, RepoSnapshot
from app.services.discovery_search import (
    build_queries,
    documented_enough,
    load_search_config,
    select_candidates,
)
from app.services.github_client import GitHubClient, GitHubError, GitHubRateLimited
from app.services.ingestion_service import ingest_snapshot
from app.services.snapshot_builder import snapshot_filename, write_snapshot

DISCOVERED_DIR = BACKEND_DIR / "data" / "discovered_snapshot"
SEARCH_PAUSE_S = 2.1  # the search API allows 30 requests/minute


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")

    settings = get_settings()
    cfg = load_search_config()
    now = datetime.now(UTC)
    token = settings.github_token.get_secret_value() if settings.github_token else None
    providers = get_providers(settings)
    DISCOVERED_DIR.mkdir(parents=True, exist_ok=True)
    with (
        Session(get_engine(settings.database_url)) as session,
        GitHubClient(settings.github_api_base_url, token) as client,
    ):
        known = set(session.scalars(select(Repository.github_id)))
        results = []
        try:
            for category, query in build_queries(cfg, now.date()):
                results.append((category, client.search_repositories(query, per_page=30)))
                time.sleep(SEARCH_PAUSE_S)
        except GitHubRateLimited as exc:
            print(f"Search rate limited (reset {exc.reset_at}); using results so far.")
        candidates = select_candidates(results, known, cfg)
        print(f"queries={len(results)} candidates={len(candidates)}")
        added = 0
        for category, item in candidates:
            name = item["full_name"]
            if args.dry_run:
                print(f"  would add [{category}] {name} ({item.get('stargazers_count')} stars)")
                continue
            try:
                readme = client.get_readme(name)
                if readme is None or not documented_enough(readme.text, readme.html_url, cfg):
                    print(f"  skipped (README missing or too thin): {name}")
                    continue
                languages = client.get_languages(name)
            except GitHubRateLimited as exc:
                print(f"Rate limited (reset {exc.reset_at}); rerun later. added={added}")
                return 2
            except GitHubError as exc:
                print(f"  failed: {name}: {exc}")
                continue
            entry = CuratedEntry(full_name=name, category=category)
            snap = RepoSnapshot.from_github(item, readme, languages, entry, now)
            write_snapshot(DISCOVERED_DIR / snapshot_filename(name), snap)
            ingest_snapshot(
                session, snap, providers, data_source="github_live", discovery_source="search"
            )
            session.commit()
            added += 1
            print(f"  added [{category}] {name}")
    print(f"added={added}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
