from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.ai.provider import Providers
from app.ai.rate_limit import SlidingWindowLimiter
from app.api.deps import get_ai_limiter, get_current_user, get_providers_dep
from app.db.session import get_db
from app.models import User
from app.schemas.common import Page
from app.schemas.insights import (
    AskIn,
    AskOut,
    BuildIdeasIn,
    BuildIdeasOut,
    CompareIn,
    CompareOut,
    InsightsOut,
)
from app.schemas.repository import Facets, RepositoryCard, RepositoryDetail, SaveState
from app.services import compare_service, discover_service, repo_qa_service, repository_service
from app.services.insight_service import get_report
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


Llm = Annotated[Providers, Depends(get_providers_dep)]
Limiter = Annotated[SlidingWindowLimiter, Depends(get_ai_limiter)]


@router.post("/compare", response_model=CompareOut)
def compare_repositories(body: CompareIn, session: DbSession, user: CurrentUser) -> CompareOut:
    return compare_service.compare(session, body.repositories, user.id)


@router.get("/{owner}/{name}/insights", response_model=InsightsOut)
def repository_insights(owner: str, name: str, session: DbSession, user: CurrentUser):
    repo = repository_service.get_by_full_name(session, owner, name)
    report, insight, stale = get_report(session, repo)
    labels, lines = discover_service.why_trending(session, repo, datetime.now(UTC))
    related = discover_service.related_repositories(session, repo)
    saved = repository_service.saved_ids(session, user.id, (r.id for r in related))
    return InsightsOut(
        report=report,
        generated=report.generated,
        model_name=insight.model_name if insight else None,
        generated_at=insight.generated_at if insight else None,
        stale=stale,
        labels=labels,
        why_trending=lines,
        related=[repository_service.to_card(r, r.id in saved) for r in related],
    )


@router.post("/{owner}/{name}/build-ideas", response_model=BuildIdeasOut)
def repository_build_ideas(
    owner: str,
    name: str,
    body: BuildIdeasIn,
    session: DbSession,
    providers: Llm,
    limiter: Limiter,
) -> BuildIdeasOut:
    repo = repository_service.get_by_full_name(session, owner, name)
    return repo_qa_service.build_ideas(session, repo, body.more, providers, limiter)


@router.post("/{owner}/{name}/ask", response_model=AskOut)
def repository_ask(
    owner: str, name: str, body: AskIn, session: DbSession, providers: Llm, limiter: Limiter
) -> AskOut:
    repo = repository_service.get_by_full_name(session, owner, name)
    return repo_qa_service.ask(session, repo, body.question, providers, limiter)
