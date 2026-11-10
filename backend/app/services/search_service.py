"""Retrieval: Postgres full-text (keyword) search and pgvector (semantic) search.

All user text reaches SQL only as bound parameters. Natural-language text goes through
`websearch_to_tsquery` (never raises on odd input); term lists are reduced to plain
alphanumeric lexemes before building an OR tsquery.
"""

import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from sqlalchemy import Select, func, select, text
from sqlalchemy.orm import Session

from app.ai.mock_providers import tokenize
from app.models import Repository, RepositoryEmbedding
from app.services.ranking import RankedHit

_LEXEME = re.compile(r"[a-z0-9]+")
_HNSW_EF_SEARCH = 400  # candidates scanned before filters; the default (40) hurts recall


@dataclass(frozen=True)
class SearchFilters:
    category: str | None = None
    language: str | None = None
    license_spdx: str | None = None
    include_archived: bool = False


def apply_filters(stmt: Select[Any], filters: SearchFilters) -> Select[Any]:
    if filters.category:
        stmt = stmt.where(Repository.category == filters.category)
    if filters.language:
        stmt = stmt.where(func.lower(Repository.primary_language) == filters.language.lower())
    if filters.license_spdx:
        stmt = stmt.where(func.lower(Repository.license_spdx) == filters.license_spdx.lower())
    if not filters.include_archived:
        stmt = stmt.where(Repository.archived.is_(False))
    return stmt


def build_or_tsquery(terms: Sequence[str]) -> str | None:
    """OR-combine terms; multi-word terms become phrases. Output uses only [a-z0-9 |()<->]."""
    clauses: list[str] = []
    for term in terms:
        parts = [p for token in tokenize(term) for p in _LEXEME.findall(token)]
        if not parts:
            continue
        clause = parts[0] if len(parts) == 1 else "(" + " <-> ".join(parts) + ")"
        if clause not in clauses:
            clauses.append(clause)
    return " | ".join(clauses) or None


def keyword_search(
    session: Session,
    *,
    text: str | None = None,
    terms: Sequence[str] | None = None,
    filters: SearchFilters,
    limit: int = 50,
) -> list[RankedHit]:
    if text is not None:
        if not text.strip():
            return []
        query = func.websearch_to_tsquery("english", text)
    else:
        tsquery = build_or_tsquery(terms or [])
        if tsquery is None:
            return []
        query = func.to_tsquery("english", tsquery)

    score = func.ts_rank_cd(Repository.search_vector, query, 32)
    stmt = select(Repository.id, score.label("score")).where(
        Repository.search_vector.op("@@")(query)
    )
    stmt = (
        apply_filters(stmt, filters)
        .order_by(score.desc(), Repository.stars.desc().nulls_last(), Repository.id)
        .limit(limit)
    )
    rows = session.execute(stmt).all()
    return [
        RankedHit(repository_id=row.id, rank=i, score=float(row.score))
        for i, row in enumerate(rows, start=1)
    ]


def semantic_search(
    session: Session,
    query_vector: list[float],
    *,
    filters: SearchFilters,
    limit: int = 50,
    chunk_pool: int = 300,
) -> list[RankedHit]:
    if not any(query_vector):
        return []  # cosine distance is undefined for a zero vector
    session.execute(text(f"SET LOCAL hnsw.ef_search = {_HNSW_EF_SEARCH}"))
    distance = RepositoryEmbedding.embedding.cosine_distance(query_vector)
    stmt = select(
        RepositoryEmbedding.repository_id,
        RepositoryEmbedding.chunk_id,
        distance.label("distance"),
    ).join(Repository, Repository.id == RepositoryEmbedding.repository_id)
    stmt = apply_filters(stmt, filters).order_by(distance).limit(chunk_pool)

    hits: list[RankedHit] = []
    seen: set[Any] = set()
    for row in session.execute(stmt):
        if row.repository_id in seen:
            continue
        seen.add(row.repository_id)
        hits.append(
            RankedHit(
                repository_id=row.repository_id,
                rank=len(hits) + 1,
                score=1.0 - float(row.distance),
                chunk_id=row.chunk_id,
            )
        )
        if len(hits) >= limit:
            break
    return hits
