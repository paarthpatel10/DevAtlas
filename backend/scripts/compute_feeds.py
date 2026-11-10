"""Recompute the Discover feeds from stored history (run after refresh_repositories).

Usage (from backend/):
    uv run python -m scripts.compute_feeds
"""

import sys
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.session import get_engine
from app.services.discover_ranking import load_ranking_config
from app.services.discover_service import compute_feeds


def main() -> int:
    settings = get_settings()
    with Session(get_engine(settings.database_url)) as session:
        counts = compute_feeds(session, load_ranking_config(), datetime.now(UTC))
        session.commit()
    for feed, count in counts.items():
        print(f"{feed:<16} {count}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
