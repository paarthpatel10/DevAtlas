"""Engine/session management and the FastAPI DB dependency."""

from collections.abc import Iterator
from functools import lru_cache
from typing import Literal

from fastapi import Request
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session

from app.core.errors import DatabaseUnavailableError


@lru_cache(maxsize=8)
def get_engine(url: str) -> Engine:
    return create_engine(
        url,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=5,
        connect_args={"connect_timeout": 5},
    )


def check_database(engine: Engine) -> Literal["ok", "unavailable"]:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return "ok"
    except Exception:
        return "unavailable"


def get_db(request: Request) -> Iterator[Session]:
    """Yield a session bound to the app's configured database.

    Connection failures surface as `OperationalError`, which the error handlers map to
    a 503 `database_unavailable` response.
    """
    url = request.app.state.settings.database_url
    if not url:
        raise DatabaseUnavailableError("The database is not configured. Set DATABASE_URL.")
    session = Session(get_engine(url), expire_on_commit=False)
    try:
        yield session
    finally:
        session.close()
