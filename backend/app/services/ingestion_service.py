"""Idempotent ingestion: snapshot -> repository row, history, chunks, analysis, embeddings.

Repositories are keyed by GitHub's stable repository ID, so renames update in place.
Chunks and embeddings are rebuilt only when the chunk content fingerprint changes.
"""

import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import delete, select, text
from sqlalchemy.orm import Session

from app.ai.provider import Providers
from app.ai.repository_analyzer import MockRepositoryAnalyzer
from app.models import (
    Repository,
    RepositoryAnalysis,
    RepositoryChunk,
    RepositoryEmbedding,
    RepositorySnapshot,
)
from app.schemas.snapshot import CuratedEntry, RepoSnapshot, load_snapshot
from app.services.chunking import Chunk, chunk_readme, metadata_chunk
from app.services.users import ensure_demo_user

logger = logging.getLogger(__name__)

README_INDEX_CHARS = 100_000


@dataclass(frozen=True)
class IngestResult:
    repository_id: uuid.UUID
    created: bool
    content_changed: bool


@dataclass(frozen=True)
class SeedReport:
    created: int
    updated: int
    unchanged: int


def _apply_metadata(repo: Repository, snap: RepoSnapshot, data_source: str) -> None:
    repo.owner = snap.owner
    repo.name = snap.name
    repo.full_name = snap.full_name
    repo.description = snap.description
    repo.html_url = snap.html_url
    repo.homepage_url = snap.homepage_url
    repo.readme_url = snap.readme_url
    repo.readme_content = snap.readme_text
    repo.readme_truncated = snap.readme_truncated
    repo.primary_language = snap.primary_language
    repo.languages = snap.languages
    repo.topics = snap.topics
    repo.license_spdx = snap.license_spdx
    repo.license_name = snap.license_name
    repo.stars = snap.stars
    repo.forks = snap.forks
    repo.open_issues = snap.open_issues
    repo.created_at_github = snap.created_at_github
    repo.updated_at_github = snap.updated_at_github
    repo.pushed_at_github = snap.pushed_at_github
    repo.archived = snap.archived
    repo.default_branch = snap.default_branch
    repo.category = snap.category
    repo.featured = snap.featured
    repo.data_source = data_source
    repo.source_fetched_at = snap.fetched_at


def _record_snapshot(session: Session, repo: Repository, snap: RepoSnapshot) -> None:
    exists = session.scalar(
        select(RepositorySnapshot.id).where(
            RepositorySnapshot.repository_id == repo.id,
            RepositorySnapshot.snapshot_at == snap.fetched_at,
        )
    )
    if exists is None:
        session.add(
            RepositorySnapshot(
                repository_id=repo.id,
                stars=snap.stars,
                forks=snap.forks,
                open_issues=snap.open_issues,
                snapshot_at=snap.fetched_at,
            )
        )


def _upsert_analysis(session: Session, repo: Repository, snap: RepoSnapshot) -> RepositoryAnalysis:
    result = MockRepositoryAnalyzer().analyze(snap)
    analysis = repo.analysis or RepositoryAnalysis(repository_id=repo.id)
    for field, value in result.model_dump(mode="json").items():
        setattr(analysis, field, value)
    if repo.analysis is None:
        session.add(analysis)
        repo.analysis = analysis
    return analysis


def _summary_text(repo: Repository, analysis: RepositoryAnalysis) -> str:
    parts = [repo.full_name, repo.description or "", " ".join(analysis.keywords)]
    parts.append(analysis.summary or "")
    parts.extend(c["name"] for c in analysis.capabilities)
    return "\n".join(p for p in parts if p)


def _rebuild_chunks_and_embeddings(
    session: Session,
    repo: Repository,
    chunks: list[Chunk],
    analysis: RepositoryAnalysis,
    providers: Providers,
) -> None:
    session.execute(delete(RepositoryEmbedding).where(RepositoryEmbedding.repository_id == repo.id))
    session.execute(delete(RepositoryChunk).where(RepositoryChunk.repository_id == repo.id))
    rows = [
        RepositoryChunk(
            repository_id=repo.id,
            position=c.position,
            source_type=c.source_type,
            source_url=c.source_url,
            section_title=c.section_title,
            content=c.content,
            content_hash=c.content_hash,
        )
        for c in chunks
    ]
    session.add_all(rows)
    session.flush()

    texts = [_summary_text(repo, analysis)]
    texts += [f"{row.section_title or ''}\n{row.content}" for row in rows]
    vectors = providers.embeddings.embed_texts(texts)
    model = providers.embeddings.model_name
    targets: list[RepositoryChunk | None] = [None, *rows]
    for target, vector in zip(targets, vectors, strict=True):
        if not any(vector):
            continue  # nothing embeddable (e.g. empty text); a zero vector breaks cosine
        session.add(
            RepositoryEmbedding(
                repository_id=repo.id,
                chunk_id=target.id if target else None,
                kind="chunk" if target else "summary",
                embedding=vector,
                embedding_model=model,
            )
        )


def refresh_search_vector(session: Session, repo: Repository) -> None:
    """Weighted FTS document: A = name/owner, B = description/topics/analysis, C = README."""
    analysis = repo.analysis
    weight_a = f"{repo.name} {repo.owner} {repo.name.replace('-', ' ').replace('_', ' ')}"
    weight_b_parts = [repo.description or "", " ".join(t.replace("-", " ") for t in repo.topics)]
    if analysis is not None:
        weight_b_parts.append(" ".join(analysis.keywords))
        weight_b_parts.extend(c["name"] for c in analysis.capabilities)
    weight_c = (repo.readme_content or "")[:README_INDEX_CHARS]
    session.execute(
        text(
            "UPDATE repositories SET search_vector = "
            "setweight(to_tsvector('english', :a), 'A') || "
            "setweight(to_tsvector('english', :b), 'B') || "
            "setweight(to_tsvector('english', :c), 'C') "
            "WHERE id = :id"
        ),
        {"a": weight_a, "b": " ".join(weight_b_parts), "c": weight_c, "id": repo.id},
    )
    session.expire(repo, ["search_vector"])


def ingest_snapshot(
    session: Session,
    snap: RepoSnapshot,
    providers: Providers,
    *,
    data_source: str = "seed_snapshot",
    discovery_source: str | None = None,
) -> IngestResult:
    now = datetime.now(UTC)
    repo = session.scalar(select(Repository).where(Repository.github_id == snap.github_id))
    created = repo is None
    if repo is None:
        repo = Repository(id=uuid.uuid4(), github_id=snap.github_id)
        session.add(repo)
    _apply_metadata(repo, snap, data_source)
    if discovery_source is not None:
        repo.discovery_source = discovery_source
    repo.last_ingested_at = now
    if not created:
        repo.last_refreshed_at = now
    session.flush()

    _record_snapshot(session, repo, snap)

    chunks = [metadata_chunk(snap), *chunk_readme(snap.readme_text, snap.readme_url)]
    stored_hashes = session.scalars(
        select(RepositoryChunk.content_hash)
        .where(RepositoryChunk.repository_id == repo.id)
        .order_by(RepositoryChunk.position)
    ).all()
    content_changed = list(stored_hashes) != [c.content_hash for c in chunks] or (
        repo.analysis is None
    )

    # Analysis is deterministic and cheap: always refresh so curated labels stay current.
    analysis = _upsert_analysis(session, repo, snap)
    session.flush()
    if content_changed:
        _rebuild_chunks_and_embeddings(session, repo, chunks, analysis, providers)
    refresh_search_vector(session, repo)
    session.flush()
    return IngestResult(repository_id=repo.id, created=created, content_changed=content_changed)


def seed_from_directory(
    session: Session,
    directory: Path,
    providers: Providers,
    curated: dict[str, CuratedEntry] | None = None,
    *,
    data_source: str = "seed_snapshot",
    discovery_source: str | None = None,
) -> SeedReport:
    ensure_demo_user(session)
    session.commit()
    created = updated = unchanged = 0
    for path in sorted(directory.glob("*.json")):
        snap = load_snapshot(path, curated)
        result = ingest_snapshot(
            session, snap, providers, data_source=data_source, discovery_source=discovery_source
        )
        session.commit()
        if result.created:
            created += 1
        elif result.content_changed:
            updated += 1
        else:
            unchanged += 1
        logger.info(
            "ingested %s (created=%s changed=%s)",
            snap.full_name,
            result.created,
            result.content_changed,
        )
    return SeedReport(created=created, updated=updated, unchanged=unchanged)
