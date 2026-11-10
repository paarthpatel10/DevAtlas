"""Repository knowledge-base models: metadata, analysis, chunks, embeddings, snapshots.

Source text (README, metadata) is stored separately from generated analysis.
"""

import uuid
from datetime import datetime
from typing import Any

from pgvector.sqlalchemy import VECTOR
from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin

EMBEDDING_DIM = 1024


class Repository(TimestampMixin, Base):
    __tablename__ = "repositories"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    github_id: Mapped[int] = mapped_column(BigInteger, unique=True)
    owner: Mapped[str] = mapped_column(String(200))
    name: Mapped[str] = mapped_column(String(200))
    full_name: Mapped[str] = mapped_column(String(401))
    description: Mapped[str | None] = mapped_column(Text)
    html_url: Mapped[str] = mapped_column(String(500))
    homepage_url: Mapped[str | None] = mapped_column(String(500))
    readme_url: Mapped[str | None] = mapped_column(String(500))
    readme_content: Mapped[str | None] = mapped_column(Text)
    readme_truncated: Mapped[bool] = mapped_column(Boolean, default=False)
    primary_language: Mapped[str | None] = mapped_column(String(100), index=True)
    languages: Mapped[dict[str, int]] = mapped_column(JSONB, default=dict)
    topics: Mapped[list[str]] = mapped_column(JSONB, default=list)
    license_spdx: Mapped[str | None] = mapped_column(String(100), index=True)
    license_name: Mapped[str | None] = mapped_column(String(200))
    stars: Mapped[int | None] = mapped_column(Integer)
    forks: Mapped[int | None] = mapped_column(Integer)
    open_issues: Mapped[int | None] = mapped_column(Integer)
    created_at_github: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at_github: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    pushed_at_github: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    archived: Mapped[bool] = mapped_column(Boolean, default=False)
    default_branch: Mapped[str | None] = mapped_column(String(200))
    # Curator's label (see roadmap deviation 6), separate from generated analysis.category.
    category: Mapped[str] = mapped_column(String(50), index=True)
    featured: Mapped[bool] = mapped_column(Boolean, default=False)
    data_source: Mapped[str] = mapped_column(String(30))
    source_fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_ingested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_refreshed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    search_vector: Mapped[Any | None] = mapped_column(TSVECTOR)

    analysis: Mapped["RepositoryAnalysis | None"] = relationship(
        back_populates="repository", uselist=False, passive_deletes=True
    )
    chunks: Mapped[list["RepositoryChunk"]] = relationship(
        back_populates="repository", order_by="RepositoryChunk.position", passive_deletes=True
    )

    __table_args__ = (
        Index("uq_repositories_full_name_lower", func.lower(full_name), unique=True),
        Index("ix_repositories_search_vector", search_vector, postgresql_using="gin"),
    )


class RepositoryAnalysis(TimestampMixin, Base):
    __tablename__ = "repository_analyses"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    repository_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("repositories.id", ondelete="CASCADE"), unique=True
    )
    summary: Mapped[str | None] = mapped_column(Text)
    problem_solved: Mapped[str | None] = mapped_column(Text)
    category: Mapped[str | None] = mapped_column(String(50))
    subcategory: Mapped[str | None] = mapped_column(String(100))
    capabilities: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    use_cases: Mapped[list[str]] = mapped_column(JSONB, default=list)
    supported_languages: Mapped[list[str]] = mapped_column(JSONB, default=list)
    integrations: Mapped[list[str]] = mapped_column(JSONB, default=list)
    requirements: Mapped[list[str]] = mapped_column(JSONB, default=list)
    limitations: Mapped[list[str]] = mapped_column(JSONB, default=list)
    maturity: Mapped[str] = mapped_column(String(30), default="unknown")
    target_users: Mapped[list[str]] = mapped_column(JSONB, default=list)
    keywords: Mapped[list[str]] = mapped_column(JSONB, default=list)
    analysis_version: Mapped[str] = mapped_column(String(50))
    model_name: Mapped[str] = mapped_column(String(200))
    prompt_version: Mapped[str] = mapped_column(String(50))

    repository: Mapped[Repository] = relationship(back_populates="analysis")


class RepositoryChunk(Base):
    __tablename__ = "repository_chunks"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    repository_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("repositories.id", ondelete="CASCADE"), index=True
    )
    position: Mapped[int] = mapped_column(Integer)
    source_type: Mapped[str] = mapped_column(String(30))
    source_url: Mapped[str | None] = mapped_column(String(500))
    section_title: Mapped[str | None] = mapped_column(String(500))
    content: Mapped[str] = mapped_column(Text)
    content_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    repository: Mapped[Repository] = relationship(back_populates="chunks")

    __table_args__ = (UniqueConstraint("repository_id", "position"),)


class RepositoryEmbedding(Base):
    __tablename__ = "repository_embeddings"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    repository_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("repositories.id", ondelete="CASCADE"), index=True
    )
    chunk_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("repository_chunks.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[str] = mapped_column(String(20))
    embedding: Mapped[list[float]] = mapped_column(VECTOR(EMBEDDING_DIM))
    embedding_model: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index(
            "ix_repository_embeddings_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )


class RepositorySnapshot(Base):
    __tablename__ = "repository_snapshots"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    repository_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("repositories.id", ondelete="CASCADE"), index=True
    )
    stars: Mapped[int | None] = mapped_column(Integer)
    forks: Mapped[int | None] = mapped_column(Integer)
    open_issues: Mapped[int | None] = mapped_column(Integer)
    snapshot_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    __table_args__ = (UniqueConstraint("repository_id", "snapshot_at"),)
