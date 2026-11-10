"""Load the committed GitHub snapshot into the database (idempotent).

Usage (from backend/):
    uv run python -m scripts.seed_demo_data [--dir data/seed_snapshot]
"""

import argparse
import logging
import sys
from pathlib import Path

from sqlalchemy.orm import Session

from app.ai.provider import get_providers
from app.config import BACKEND_DIR, get_settings
from app.db.session import get_engine
from app.services.ingestion_service import seed_from_directory


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dir", type=Path, default=BACKEND_DIR / "data" / "seed_snapshot")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    settings = get_settings()
    if not settings.database_url:
        print("DATABASE_URL is not set (.env).")
        return 1
    with Session(get_engine(settings.database_url)) as session:
        report = seed_from_directory(session, args.dir, get_providers(settings))
    print(f"created={report.created} updated={report.updated} unchanged={report.unchanged}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
