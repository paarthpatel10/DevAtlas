"""Relevance smoke benchmark against the real committed seed snapshot (slow: seeds 71 repos)."""

from collections.abc import Iterator

import pytest
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from app.ai.provider import get_providers
from app.config import BACKEND_DIR, Settings
from app.services.evaluation import run_benchmark
from app.services.ingestion_service import seed_from_directory
from tests.db.conftest import _truncate

pytestmark = pytest.mark.benchmark

BENCHMARK = BACKEND_DIR / "eval" / "benchmark.yaml"
SNAPSHOT_DIR = BACKEND_DIR / "data" / "seed_snapshot"


@pytest.fixture(scope="module")
def real_seeded_session(db_engine: Engine) -> Iterator[Session]:
    _truncate(db_engine)
    session = Session(db_engine, expire_on_commit=False)
    seed_from_directory(session, SNAPSHOT_DIR, get_providers(Settings(_env_file=None)))
    yield session
    session.close()
    _truncate(db_engine)  # leave the fixture-based modules a clean database


def test_benchmark_hit_rate_floor(real_seeded_session, vocab):
    settings = Settings(_env_file=None)
    report = run_benchmark(real_seeded_session, get_providers(settings), vocab, settings, BENCHMARK)
    misses = [(r.id, r.ranked) for r in report.per_query if not r.hit_at_5]
    assert report.hit_rate_at_5 >= 0.8, misses
    assert report.mrr >= 0.6
