"""Generate grounded intelligence reports with the configured LLM (Gemini).

Usage (from backend/):
    uv run python -m scripts.generate_insights [--limit N] [--only owner/name ...] [--force]

Resumable: repositories whose stored report matches the current README chunks are skipped.
Throttled to AI_REQUESTS_PER_MINUTE. Stops after 3 consecutive provider failures.
"""

import argparse
import logging
import sys
import time
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.gemini_provider import LLMUnavailableError
from app.ai.provider import get_providers
from app.ai.rate_limit import SlidingWindowLimiter
from app.config import get_settings
from app.db.session import get_engine
from app.models import Repository
from app.services.insight_service import generate_insight

MAX_CONSECUTIVE_FAILURES = 3


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--only", nargs="*", default=None)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")

    settings = get_settings()
    providers = get_providers(settings)
    if not providers.llm_available:
        print("No LLM configured (set GEMINI_API_KEY); nothing to generate.")
        return 1
    limiter = SlidingWindowLimiter(settings.ai_requests_per_minute)
    wanted = {n.lower() for n in args.only} if args.only else None
    generated = skipped = failed = consecutive = 0
    with Session(get_engine(settings.database_url)) as session:
        repos = session.scalars(
            select(Repository)
            .where(Repository.archived.is_(False))
            .order_by(Repository.featured.desc(), Repository.stars.desc().nulls_last())
        ).all()
        for repo in repos:
            if wanted and repo.full_name.lower() not in wanted:
                continue
            if args.limit is not None and generated >= args.limit:
                break
            time.sleep(limiter.wait_time("generate"))
            try:
                limiter.check("generate")
                result = generate_insight(
                    session, repo, providers.llm, datetime.now(UTC), force=args.force
                )
            except LLMUnavailableError as exc:
                session.rollback()
                failed += 1
                consecutive += 1
                print(f"  failed: {repo.full_name}: {exc.message}")
                if consecutive >= MAX_CONSECUTIVE_FAILURES:
                    print("Stopping after repeated provider failures; rerun later to resume.")
                    break
                continue
            consecutive = 0
            session.commit()
            if result is None:
                skipped += 1
            else:
                generated += 1
                print(f"  generated: {repo.full_name}")
    print(
        f"generated={generated} skipped={skipped} failed={failed} model={providers.llm.model_name}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
