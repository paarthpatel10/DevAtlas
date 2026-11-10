"""Export history and AI reports from DATABASE_URL into committed snapshot files.

Usage (from backend/):
    uv run python -m scripts.export_snapshots
"""

import sys

from sqlalchemy.orm import Session

from app.config import BACKEND_DIR, get_settings
from app.db.session import get_engine
from app.services.snapshot_io import export_history, export_insights

HISTORY_PATH = BACKEND_DIR / "data" / "history_snapshot.json"
INSIGHTS_DIR = BACKEND_DIR / "data" / "insights_snapshot"


def main() -> int:
    with Session(get_engine(get_settings().database_url)) as session:
        export_history(session, HISTORY_PATH)
        count = export_insights(session, INSIGHTS_DIR)
    print(f"history -> {HISTORY_PATH.name}; insights={count} -> {INSIGHTS_DIR.name}/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
