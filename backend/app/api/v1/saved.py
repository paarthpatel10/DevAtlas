from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models import User
from app.schemas.common import Page
from app.schemas.repository import RepositoryCard
from app.services import repository_service

router = APIRouter(prefix="/me", tags=["saved"])


@router.get("/saved", response_model=Page[RepositoryCard])
def list_saved(
    session: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
    page: Annotated[int, Query(ge=1, le=10_000)] = 1,
    page_size: Annotated[int, Query(ge=1, le=50)] = 20,
) -> Page[RepositoryCard]:
    return repository_service.list_saved(session, user.id, page, page_size)
