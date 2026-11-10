"""Fetch curated repositories from the GitHub API into data/seed_snapshot/*.json.

Usage (from backend/):
    uv run python -m scripts.build_seed_snapshot [--refresh] [--only owner/name ...]

Resumable: existing snapshot files are skipped unless --refresh. Without GITHUB_TOKEN the
GitHub API allows 60 requests/hour (3 per repository); rerun after the reset time.
"""

import argparse
import logging
import sys

from app.config import BACKEND_DIR, get_settings
from app.schemas.snapshot import load_curated
from app.services.github_client import GitHubClient
from app.services.snapshot_builder import build_snapshot

CURATED_PATH = BACKEND_DIR / "data" / "curated_repositories.yaml"
SNAPSHOT_DIR = BACKEND_DIR / "data" / "seed_snapshot"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--refresh", action="store_true", help="re-fetch existing files")
    parser.add_argument("--only", nargs="*", default=None, help="limit to these owner/name")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    settings = get_settings()
    entries = load_curated(CURATED_PATH)
    if args.only:
        wanted = {name.lower() for name in args.only}
        entries = [e for e in entries if e.full_name.lower() in wanted]

    token = settings.github_token.get_secret_value() if settings.github_token else None
    if not token:
        print("No GITHUB_TOKEN set: limited to 60 requests/hour (about 20 repositories).")

    with GitHubClient(settings.github_api_base_url, token) as client:
        report = build_snapshot(client, entries, SNAPSHOT_DIR, refresh=args.refresh)

    print(
        f"written={len(report.written)} skipped={len(report.skipped)} failed={len(report.failed)}"
    )
    for name, reason in report.failed.items():
        print(f"  FAILED {name}: {reason}")
    if report.rate_limited_until:
        print(
            f"Rate limited until {report.rate_limited_until.isoformat()}. "
            "Set GITHUB_TOKEN in backend/.env or rerun after that time."
        )
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
