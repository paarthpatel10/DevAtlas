"""Run the relevance benchmark against DATABASE_URL and print per-query results.

Usage (from backend/):
    uv run python -m scripts.run_benchmark
"""

import sys

from sqlalchemy.orm import Session

from app.ai.provider import get_providers
from app.ai.vocabulary import get_vocabulary
from app.config import BACKEND_DIR, get_settings
from app.db.session import get_engine
from app.services.evaluation import run_benchmark

BENCHMARK_PATH = BACKEND_DIR / "eval" / "benchmark.yaml"


def main() -> int:
    settings = get_settings()
    if not settings.database_url:
        print("DATABASE_URL is not set (.env).")
        return 1
    with Session(get_engine(settings.database_url)) as session:
        report = run_benchmark(
            session, get_providers(settings), get_vocabulary(), settings, BENCHMARK_PATH
        )
    for r in report.per_query:
        mark = "HIT " if r.hit_at_5 else "MISS"
        print(f"{mark} {r.id:<13} RR={r.rr:.2f} P@5={r.p_at_5:.2f}  {', '.join(r.ranked)}")
    print(
        f"\nhit@5={report.hit_rate_at_5:.2f}  MRR={report.mrr:.2f}  "
        f"mean P@5={report.mean_p_at_5:.2f}  (n={len(report.per_query)})"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
