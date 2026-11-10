from typing import Literal

from fastapi import APIRouter, Request
from pydantic import BaseModel

from app.ai.provider import get_providers
from app.core.errors import AppError
from app.db.session import check_database, get_engine

router = APIRouter(tags=["health"])

DatabaseStatus = Literal["ok", "unavailable", "not_configured"]


class HealthOut(BaseModel):
    status: Literal["ok", "degraded"]
    app_env: str
    ai_provider: Literal["mock", "gemini", "misconfigured"]
    llm_model: str | None
    demo_mode: bool
    database: DatabaseStatus


@router.get("/health", response_model=HealthOut)
def health(request: Request) -> HealthOut:
    settings = request.app.state.settings
    database: DatabaseStatus = "not_configured"
    if settings.database_url:
        database = check_database(get_engine(settings.database_url))

    ai_provider: Literal["mock", "gemini", "misconfigured"] = "misconfigured"
    llm_model: str | None = None
    try:
        providers = get_providers(settings)
        if providers.llm_available:
            ai_provider, llm_model = "gemini", providers.llm.model_name
        else:
            ai_provider = "mock"
    except AppError:
        pass

    healthy = database in ("ok", "not_configured") and ai_provider != "misconfigured"
    return HealthOut(
        status="ok" if healthy else "degraded",
        app_env=settings.app_env,
        ai_provider=ai_provider,
        llm_model=llm_model,
        demo_mode=llm_model is None,
        database=database,
    )
