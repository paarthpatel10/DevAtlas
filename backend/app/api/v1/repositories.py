from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models import User
from app.schemas.common import Page
from app.schemas.repository import Facets, RepositoryCard, RepositoryDetail, SaveState
from app.services import repository_service
from app.services.repository_service import SortOption
from app.services.search_service import SearchFilters

router = APIRouter(prefix="/repositories", tags=["repositories"])

DbSession = Annotated[Session, Depends(get_db)]
CurrentUser = Annotated[User, Depends(get_current_user)]


# Static routes are registered before /{owner}/{name}.
@router.get("", response_model=Page[RepositoryCard])
def list_repositories(
    session: DbSession,
    user: CurrentUser,
    q: Annotated[str | None, Query(max_length=200)] = None,
    category: Annotated[str | None, Query(max_length=50)] = None,
    language: Annotated[str | None, Query(max_length=100)] = None,
    license_spdx: Annotated[str | None, Query(alias="license", max_length=100)] = None,
    sort: SortOption | None = None,
    page: Annotated[int, Query(ge=1, le=10_000)] = 1,
    page_size: Annotated[int, Query(ge=1, le=50)] = 20,
) -> Page[RepositoryCard]:
    filters = SearchFilters(category=category, language=language, license_spdx=license_spdx)
    return repository_service.list_repositories(
        session, user_id=user.id, q=q, filters=filters, sort=sort, page=page, page_size=page_size
    )


@router.get("/facets", response_model=Facets)
def facets(session: DbSession) -> Facets:
    return repository_service.get_facets(session)


@router.get("/{owner}/{name}", response_model=RepositoryDetail)
def repository_detail(owner: str, name: str, session: DbSession, user: CurrentUser):
    return repository_service.get_detail(session, owner, name, user.id)


@router.post("/{owner}/{name}/save", response_model=SaveState)
def save_repository(owner: str, name: str, session: DbSession, user: CurrentUser) -> SaveState:
    return SaveState(saved=repository_service.set_saved(session, user.id, owner, name, True))


@router.delete("/{owner}/{name}/save", response_model=SaveState)
def unsave_repository(owner: str, name: str, session: DbSession, user: CurrentUser) -> SaveState:
    return SaveState(saved=repository_service.set_saved(session, user.id, owner, name, False))
