"""
PostgreSQL connection management using SQLAlchemy.
Provides connection pooling and session management for the analytics database.
"""

from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.config.settings import settings
from app.utils.logger import setup_logger

logger = setup_logger(__name__)

# Module-level engine (lazy singleton)
_engine: Engine | None = None


def get_engine() -> Engine:
    """Returns the SQLAlchemy engine, creating it on first call."""
    global _engine
    if _engine is None:
        logger.info(
            f"Creating PostgreSQL engine: {settings.POSTGRES_HOST}:{settings.POSTGRES_PORT}/{settings.POSTGRES_DB}"
        )
        _engine = create_engine(
            settings.postgres_url,
            pool_size=5,
            max_overflow=10,
            pool_timeout=30,
            pool_recycle=1800,
            echo=False,
        )
    return _engine


def get_session_factory() -> sessionmaker:
    """Returns a sessionmaker bound to the engine."""
    return sessionmaker(bind=get_engine())


@contextmanager
def get_db_session() -> Generator[Session, None, None]:
    """Context manager that yields a database session and handles cleanup."""
    session_factory = get_session_factory()
    session = session_factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def test_connection() -> bool:
    """Tests the PostgreSQL connection and returns True if successful."""
    try:
        engine = get_engine()
        with engine.connect() as conn:
            result = conn.execute(text("SELECT 1"))
            result.fetchone()
        logger.info("PostgreSQL connection test: SUCCESS")
        return True
    except Exception as e:
        logger.error(f"PostgreSQL connection test: FAILED — {e}")
        return False
