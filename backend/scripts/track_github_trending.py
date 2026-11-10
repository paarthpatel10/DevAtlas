"""Record today's GitHub Trending (github.com/trending) and add new repositories to the index.

Usage (from backend/):
    uv run python -m scripts.track_github_trending

Run once a day, then `compute_feeds` (and `generate_insights` for new repositories).
Only the daily pages are fetched; robots.txt disallows `?since=` URLs for automated clients.
"""

import logging
import sys
from datetime import UTC, datetime

import httpx
import yaml
from sqlalchemy.orm import Session

from app.ai.provider import get_providers
from app.config import BACKEND_DIR, get_settings
from app.db.session import get_engine
from app.schemas.snapshot import CuratedEntry, RepoSnapshot
from app.services.discover_ranking import RANKING_PATH
from app.services.github_client import GitHubClient, GitHubError, GitHubRateLimited
from app.services.github_trending import TrendingClient, TrendingParseError, infer_category
from app.services.ingestion_service import ingest_snapshot
from app.services.snapshot_builder import snapshot_filename, write_snapshot
from app.services.trending_tracker import link_observations, record_trending

TRENDING_DIR = BACKEND_DIR / "data" / "trending_snapshot"


def main() -> int:
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")
    settings = get_settings()
    cfg = yaml.safe_load(RANKING_PATH.read_text(encoding="utf-8"))["github_trending"]
    now = datetime.now(UTC)
    day = now.date()
    token = settings.github_token.get_secret_value() if settings.github_token else None
    providers = get_providers(settings)
    TRENDING_DIR.mkdir(parents=True, exist_ok=True)

    unknown: dict[str, None] = {}
    with Session(get_engine(settings.database_url)) as session:
        with TrendingClient(delay_s=cfg.get("delay_s", 2.0)) as trending:
            for language in [None, *cfg.get("languages", [])]:
                scope = "" if language is None else language
                try:
                    repos = trending.fetch(language)
                except TrendingParseError as exc:
                    print(f"GitHub Trending layout changed ({exc}); keeping previous data.")
                    return 3
                except httpx.HTTPError as exc:
                    print(f"  skipped {scope or 'overall'}: {exc}")
                    continue
                for name in record_trending(session, scope, repos, day, now):
                    unknown.setdefault(name, None)
                session.commit()
                print(f"  {scope or 'overall':<12} {len(repos)} repositories")

        added = 0
        with GitHubClient(settings.github_api_base_url, token) as github:
            for name in unknown:
                try:
                    data = github.get_repository(name)
                    readme = github.get_readme(name)
                    languages = github.get_languages(name)
                except GitHubRateLimited as exc:
                    print(f"GitHub API rate limited (reset {exc.reset_at}); rerun later.")
                    break
                except GitHubError as exc:
                    print(f"  failed: {name}: {exc}")
                    continue
                category = infer_category(
                    data.get("topics") or [], data.get("language"), data.get("description")
                )
                entry = CuratedEntry(full_name=data["full_name"], category=category)
                snap = RepoSnapshot.from_github(data, readme, languages, entry, now)
                write_snapshot(TRENDING_DIR / snapshot_filename(data["full_name"]), snap)
                ingest_snapshot(
                    session, snap, providers, data_source="github_live", discovery_source="trending"
                )
                session.commit()
                added += 1
        linked = link_observations(session)
        session.commit()
    print(f"new repositories added={added} observations linked={linked}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
