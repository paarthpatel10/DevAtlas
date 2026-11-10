from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.ai.provider import Providers, get_providers
from app.ai.rate_limit import SlidingWindowLimiter
from app.db.session import get_db
from app.models import User
from app.services.users import DEMO_USER_ID, ensure_demo_user


def get_current_user(session: Annotated[Session, Depends(get_db)]) -> User:
    """V0 has no authentication: every request acts as the seeded demo user."""
    user = session.get(User, DEMO_USER_ID)
    if user is None:
        user = ensure_demo_user(session)
        session.commit()
    return user


def get_providers_dep(request: Request) -> Providers:
    """AI providers for this app (cached on app state; overridable in tests)."""
    providers = getattr(request.app.state, "providers", None)
    if providers is None:
        providers = get_providers(request.app.state.settings)
        request.app.state.providers = providers
    return providers


def get_ai_limiter(request: Request) -> SlidingWindowLimiter:
    limiter = getattr(request.app.state, "ai_limiter", None)
    if limiter is None:
        limiter = SlidingWindowLimiter(request.app.state.settings.ai_requests_per_minute)
        request.app.state.ai_limiter = limiter
    return limiter
