"""Repository read models, listing/search, facets, and saves."""

import uuid
from collections.abc import Iterable
from typing import Literal

from sqlalchemy import Select, delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session, selectinload

from app.core.errors import NotFoundError
from app.models import Repository, SavedRepository
from app.schemas.analysis import RepositoryAnalysisOut
from app.schemas.common import Page
from app.schemas.repository import (
    AnalysisView,
    CategoryFacet,
    Facets,
    FacetValue,
    RepositoryCard,
    RepositoryDetail,
    Signal,
    SourceRef,
)
from app.schemas.snapshot import CATEGORY_LABELS
from app.services.search_service import SearchFilters, apply_filters, keyword_search

SortOption = Literal["relevance", "stars", "recent", "name", "featured"]
MAX_KEYWORD_RESULTS = 500


def category_label(slug: str) -> str:
    return CATEGORY_LABELS.get(slug, slug.replace("_", " ").title())


def to_card(repo: Repository, is_saved: bool) -> RepositoryCard:
    return RepositoryCard(
        id=repo.id,
        owner=repo.owner,
        name=repo.name,
        full_name=repo.full_name,
        description=repo.description,
        html_url=repo.html_url,
        primary_language=repo.primary_language,
        topics=list(repo.topics or []),
        license_spdx=repo.license_spdx,
        license_name=repo.license_name,
        stars=repo.stars,
        forks=repo.forks,
        pushed_at_github=repo.pushed_at_github,
        archived=repo.archived,
        category=repo.category,
        category_label=category_label(repo.category),
        featured=repo.featured,
        data_source=repo.data_source,
        source_fetched_at=repo.source_fetched_at,
        is_saved=is_saved,
    )


def saved_ids(session: Session, user_id: uuid.UUID, repo_ids: Iterable[uuid.UUID]) -> set:
    ids = list(repo_ids)
    if not ids:
        return set()
    return set(
        session.scalars(
            select(SavedRepository.repository_id).where(
                SavedRepository.user_id == user_id, SavedRepository.repository_id.in_(ids)
            )
        )
    )


def cards_for(
    session: Session, repos: list[Repository], user_id: uuid.UUID
) -> list[RepositoryCard]:
    saved = saved_ids(session, user_id, (r.id for r in repos))
    return [to_card(r, r.id in saved) for r in repos]


def get_by_full_name(session: Session, owner: str, name: str) -> Repository:
    full_name = f"{owner}/{name}"
    repo = session.scalar(
        select(Repository)
        .options(selectinload(Repository.analysis))
        .where(func.lower(Repository.full_name) == full_name.lower())
    )
    if repo is None:
        raise NotFoundError(f"Repository {full_name} not found")
    return repo


def _order(stmt: Select, sort: SortOption) -> Select:
    if sort == "stars":
        return stmt.order_by(Repository.stars.desc().nulls_last(), Repository.full_name)
    if sort == "recent":
        return stmt.order_by(Repository.pushed_at_github.desc().nulls_last(), Repository.full_name)
    if sort == "name":
        return stmt.order_by(func.lower(Repository.full_name))
    return stmt.order_by(
        Repository.featured.desc(), Repository.stars.desc().nulls_last(), Repository.full_name
    )


def list_repositories(
    session: Session,
    *,
    user_id: uuid.UUID,
    q: str | None,
    filters: SearchFilters,
    sort: SortOption | None,
    page: int,
    page_size: int,
) -> Page[RepositoryCard]:
    offset = (page - 1) * page_size
    query = (q or "").strip()
    if query:
        hits = keyword_search(session, text=query, filters=filters, limit=MAX_KEYWORD_RESULTS)
        if not hits:  # natural phrases: fall back to OR semantics (roadmap deviation 9)
            hits = keyword_search(
                session, terms=query.split(), filters=filters, limit=MAX_KEYWORD_RESULTS
            )
        ids = [h.repository_id for h in hits]
        total = len(ids)
        effective_sort = sort or "relevance"
        if effective_sort == "relevance":
            page_ids = ids[offset : offset + page_size]
            by_id = {
                r.id: r
                for r in session.scalars(select(Repository).where(Repository.id.in_(page_ids)))
            }
            repos = [by_id[i] for i in page_ids if i in by_id]
        else:
            stmt = _order(select(Repository).where(Repository.id.in_(ids)), effective_sort)
            repos = list(session.scalars(stmt.offset(offset).limit(page_size)))
    else:
        base = apply_filters(select(Repository), filters)
        total = session.scalar(select(func.count()).select_from(base.subquery())) or 0
        effective_sort = "featured" if sort in (None, "relevance") else sort
        repos = list(session.scalars(_order(base, effective_sort).offset(offset).limit(page_size)))
    return Page(
        items=cards_for(session, repos, user_id), page=page, page_size=page_size, total=total
    )


def _analysis_view(repo: Repository) -> AnalysisView | None:
    analysis = repo.analysis
    if analysis is None:
        return None
    data = RepositoryAnalysisOut.model_validate(analysis, from_attributes=True).model_dump()
    label = (
        "Extractive demo analyzer (no LLM)"
        if analysis.model_name == "mock"
        else f"Generated by {analysis.model_name}"
    )
    return AnalysisView(**data, generated_by_label=label)


def _maintenance_signals(repo: Repository) -> list[Signal]:
    note = f"From GitHub metadata, snapshot {repo.source_fetched_at:%Y-%m-%d}"
    signals: list[Signal] = []
    if repo.pushed_at_github is not None:
        signals.append(
            Signal(label="Last push", value=f"{repo.pushed_at_github:%Y-%m-%d}", explanation=note)
        )
    if repo.archived:
        signals.append(
            Signal(label="Archived", value="Yes — read-only on GitHub", explanation=note)
        )
    if repo.open_issues is not None:
        signals.append(
            Signal(
                label="Open issues",
                value=str(repo.open_issues),
                explanation=f"{note}; GitHub counts open pull requests too",
            )
        )
    return signals


def _sources(repo: Repository) -> list[SourceRef]:
    sources = [SourceRef(label="GitHub repository", url=repo.html_url)]
    if repo.readme_url:
        sources.append(SourceRef(label="README", url=repo.readme_url))
    if repo.homepage_url:
        sources.append(SourceRef(label="Homepage", url=repo.homepage_url))
    return sources


def get_detail(session: Session, owner: str, name: str, user_id: uuid.UUID) -> RepositoryDetail:
    repo = get_by_full_name(session, owner, name)
    card = to_card(repo, repo.id in saved_ids(session, user_id, [repo.id]))
    return RepositoryDetail(
        **card.model_dump(),
        homepage_url=repo.homepage_url,
        readme_url=repo.readme_url,
        languages=dict(repo.languages or {}),
        open_issues=repo.open_issues,
        created_at_github=repo.created_at_github,
        updated_at_github=repo.updated_at_github,
        default_branch=repo.default_branch,
        readme_truncated=repo.readme_truncated,
        analysis=_analysis_view(repo),
        maintenance_signals=_maintenance_signals(repo),
        sources=_sources(repo),
    )


def get_facets(session: Session) -> Facets:
    def counts(column) -> list[tuple[str, int]]:
        stmt = (
            select(column, func.count())
            .where(column.is_not(None), Repository.archived.is_(False))
            .group_by(column)
            .order_by(func.count().desc(), column)
        )
        return [(value, count) for value, count in session.execute(stmt)]

    return Facets(
        categories=[
            CategoryFacet(value=v, label=category_label(v), count=c)
            for v, c in counts(Repository.category)
        ],
        languages=[FacetValue(value=v, count=c) for v, c in counts(Repository.primary_language)],
        licenses=[FacetValue(value=v, count=c) for v, c in counts(Repository.license_spdx)],
    )


def set_saved(session: Session, user_id: uuid.UUID, owner: str, name: str, saved: bool) -> bool:
    repo = get_by_full_name(session, owner, name)
    if saved:
        session.execute(
            insert(SavedRepository)
            .values(id=uuid.uuid4(), user_id=user_id, repository_id=repo.id)
            .on_conflict_do_nothing(index_elements=["user_id", "repository_id"])
        )
    else:
        session.execute(
            delete(SavedRepository).where(
                SavedRepository.user_id == user_id, SavedRepository.repository_id == repo.id
            )
        )
    session.commit()
    return saved


def list_saved(
    session: Session, user_id: uuid.UUID, page: int, page_size: int
) -> Page[RepositoryCard]:
    base = (
        select(Repository)
        .join(SavedRepository, SavedRepository.repository_id == Repository.id)
        .where(SavedRepository.user_id == user_id)
    )
    total = session.scalar(select(func.count()).select_from(base.subquery())) or 0
    repos = list(
        session.scalars(
            base.order_by(SavedRepository.created_at.desc(), Repository.full_name)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    )
    return Page(
        items=[to_card(r, True) for r in repos], page=page, page_size=page_size, total=total
    )
