"""Generate, store, and read grounded repository intelligence reports."""

import hashlib
import uuid
from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.ai.insights import (
    PROMPT_VERSION,
    GroundedReport,
    ModelReport,
    build_prompt,
    extractive_report,
    ground,
    select_chunks,
)
from app.ai.provider import LLMProvider
from app.models import Repository, RepositoryChunk, RepositoryInsight, RepositoryRelease


def source_hash(chunks: Sequence[RepositoryChunk]) -> str:
    payload = PROMPT_VERSION + "|" + "|".join(c.content_hash for c in chunks)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _chunks(session: Session, repo: Repository) -> list[RepositoryChunk]:
    return list(
        session.scalars(
            select(RepositoryChunk)
            .where(RepositoryChunk.repository_id == repo.id)
            .order_by(RepositoryChunk.position)
        )
    )


def current_source_hash(session: Session, repo: Repository) -> str:
    return source_hash(select_chunks(_chunks(session, repo)))


def _insight(session: Session, repo: Repository) -> RepositoryInsight | None:
    return session.scalar(
        select(RepositoryInsight).where(RepositoryInsight.repository_id == repo.id)
    )


def generate_insight(
    session: Session, repo: Repository, llm: LLMProvider, now: datetime, *, force: bool = False
) -> RepositoryInsight | None:
    """Generate and store a report; returns None when the stored one is still current.

    Raises LLMUnavailableError (nothing stored) when the provider fails.
    """
    chunks = select_chunks(_chunks(session, repo))
    digest = source_hash(chunks)
    existing = _insight(session, repo)
    if existing is not None and existing.source_hash == digest and not force:
        return None
    releases = session.scalars(
        select(RepositoryRelease)
        .where(RepositoryRelease.repository_id == repo.id)
        .order_by(RepositoryRelease.published_at.desc().nulls_last())
        .limit(3)
    ).all()
    system, user, id_map = build_prompt(repo, chunks, releases)
    model_report = llm.generate_structured(system, user, ModelReport)
    grounded = ground(model_report, id_map, "\n".join(c.content for c in chunks))
    if grounded.what_is_it is None:  # no citable summary: fall back to the extractive one
        grounded.what_is_it = extractive_report(repo).what_is_it

    values = {
        "report": grounded.model_dump(mode="json"),
        "model_name": llm.model_name,
        "prompt_version": PROMPT_VERSION,
        "source_hash": digest,
        "generated_at": now,
    }
    session.execute(
        insert(RepositoryInsight)
        .values(id=uuid.uuid4(), repository_id=repo.id, **values)
        .on_conflict_do_update(index_elements=["repository_id"], set_=values)
    )
    session.flush()
    return _insight(session, repo)


def get_report(
    session: Session, repo: Repository
) -> tuple[GroundedReport, RepositoryInsight | None, bool]:
    """(report, stored row or None, stale). Without a stored report: extractive summary."""
    insight = _insight(session, repo)
    if insight is None:
        return extractive_report(repo), None, False
    stale = insight.source_hash != current_source_hash(session, repo)
    return GroundedReport.model_validate(insight.report), insight, stale
