from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models import User
from app.schemas.discover import CategorySummary, FeedName, FeedPage, Period
from app.services import discover_service
from app.services.search_service import SearchFilters

router = APIRouter(prefix="/discover", tags=["discover"])

DbSession = Annotated[Session, Depends(get_db)]
CurrentUser = Annotated[User, Depends(get_current_user)]


# Static route registered before /{feed}.
@router.get("/categories", response_model=list[CategorySummary])
def categories(
    session: DbSession,
    user: CurrentUser,
    language: Annotated[str | None, Query(max_length=100)] = None,
) -> list[CategorySummary]:
    return discover_service.get_categories(session, language, user.id)


@router.get("/{feed}", response_model=FeedPage)
def feed(
    feed: FeedName,
    session: DbSession,
    user: CurrentUser,
    period: Period = "week",
    category: Annotated[str | None, Query(max_length=50)] = None,
    language: Annotated[str | None, Query(max_length=100)] = None,
    page: Annotated[int, Query(ge=1, le=10_000)] = 1,
    page_size: Annotated[int, Query(ge=1, le=50)] = 20,
) -> FeedPage:
    return discover_service.get_feed(
        session,
        feed=feed,
        period=period,
        filters=SearchFilters(category=category, language=language),
        page=page,
        page_size=page_size,
        user_id=user.id,
    )
