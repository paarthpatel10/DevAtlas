"""Fixtures for tests that need a real Postgres + pgvector database.

These tests run only when TEST_DATABASE_URL is set (backend/.env or environment).
The database is wiped: point it at a dedicated test database/branch.
"""

from collections.abc import Iterator

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session

from app.ai.provider import get_providers
from app.config import BACKEND_DIR, Settings
from app.db.session import get_db, get_engine
from app.main import create_app
from app.services.ingestion_service import seed_from_directory
from tests.factories import FIXTURES_DIR

TEST_DATABASE_URL = Settings().test_database_url


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    for item in items:
        if "tests/db/" in item.nodeid.replace("\\", "/"):
            item.add_marker(pytest.mark.db)
            if not TEST_DATABASE_URL:
                item.add_marker(pytest.mark.skip(reason="TEST_DATABASE_URL not set"))


def alembic_config(url: str) -> Config:
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "app" / "db" / "migrations"))
    cfg.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    return cfg


@pytest.fixture(scope="session")
def db_engine() -> Iterator[Engine]:
    assert TEST_DATABASE_URL, "TEST_DATABASE_URL must be set for db tests"
    cfg = alembic_config(TEST_DATABASE_URL)
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")
    engine = get_engine(TEST_DATABASE_URL)
    yield engine
    engine.dispose()


def _truncate(engine: Engine) -> None:
    with engine.begin() as conn:
        conn.execute(
            text("TRUNCATE users, repositories, discovery_feed_runs RESTART IDENTITY CASCADE")
        )


@pytest.fixture
def db_session(db_engine: Engine) -> Iterator[Session]:
    _truncate(db_engine)
    session = Session(db_engine, expire_on_commit=False)
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture(scope="module")
def seeded_module_session(db_engine: Engine) -> Iterator[Session]:
    """The 4 fixture repositories, seeded once per test module (Neon round trips are slow)."""
    _truncate(db_engine)
    session = Session(db_engine, expire_on_commit=False)
    seed_from_directory(session, FIXTURES_DIR, get_providers(Settings(_env_file=None)))
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture
def seeded(seeded_module_session: Session) -> Iterator[Session]:
    """Seeded session; per-user state (saves) is cleared before each test."""
    seeded_module_session.execute(text("DELETE FROM saved_repositories"))
    seeded_module_session.commit()
    yield seeded_module_session
    seeded_module_session.rollback()


@pytest.fixture
def api(seeded: Session) -> TestClient:
    """API client whose DB dependency is the seeded test session."""
    app = create_app(
        Settings(app_env="test", _env_file=None, database_url="postgresql+psycopg://unused/x")
    )
    app.dependency_overrides[get_db] = lambda: seeded
    return TestClient(app)
