from typing import Literal

from fastapi import APIRouter, Request
from pydantic import BaseModel

from app.db.session import check_database, get_engine

router = APIRouter(tags=["health"])

DatabaseStatus = Literal["ok", "unavailable", "not_configured"]


class HealthOut(BaseModel):
    status: Literal["ok", "degraded"]
    app_env: str
    ai_provider: str
    demo_mode: bool
    database: DatabaseStatus


@router.get("/health", response_model=HealthOut)
def health(request: Request) -> HealthOut:
    settings = request.app.state.settings
    database: DatabaseStatus = "not_configured"
    if settings.database_url:
        database = check_database(get_engine(settings.database_url))
    return HealthOut(
        status="ok" if database == "ok" or database == "not_configured" else "degraded",
        app_env=settings.app_env,
        ai_provider=settings.ai_provider,
        demo_mode=settings.ai_provider == "mock",
        database=database,
    )
