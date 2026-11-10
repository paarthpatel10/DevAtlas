"""Discover: repository history, releases, AI reports/cache, and precomputed feeds."""

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


def _repo_fk() -> Mapped[uuid.UUID]:
    return mapped_column(ForeignKey("repositories.id", ondelete="CASCADE"), index=True)


class RepositoryDailyStat(Base):
    __tablename__ = "repository_daily_stats"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    repository_id: Mapped[uuid.UUID] = _repo_fk()
    day: Mapped[date] = mapped_column(Date)
    stars_gained: Mapped[int | None] = mapped_column(Integer)
    forks_gained: Mapped[int | None] = mapped_column(Integer)
    commits: Mapped[int | None] = mapped_column(Integer)
    stars_capped: Mapped[bool] = mapped_column(Boolean, default=False)
    forks_capped: Mapped[bool] = mapped_column(Boolean, default=False)

    __table_args__ = (UniqueConstraint("repository_id", "day"),)


class RepositoryRelease(Base):
    __tablename__ = "repository_releases"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    repository_id: Mapped[uuid.UUID] = _repo_fk()
    tag: Mapped[str] = mapped_column(String(300))
    name: Mapped[str | None] = mapped_column(String(500))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    url: Mapped[str | None] = mapped_column(String(500))

    __table_args__ = (UniqueConstraint("repository_id", "tag"),)


class RepositoryInsight(Base):
    __tablename__ = "repository_insights"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    repository_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("repositories.id", ondelete="CASCADE"), unique=True
    )
    report: Mapped[dict[str, Any]] = mapped_column(JSONB)
    model_name: Mapped[str] = mapped_column(String(200))
    prompt_version: Mapped[str] = mapped_column(String(50))
    source_hash: Mapped[str] = mapped_column(String(64))
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class AIGeneration(Base):
    __tablename__ = "ai_generations"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    kind: Mapped[str] = mapped_column(String(30))
    repository_id: Mapped[uuid.UUID] = _repo_fk()
    input_hash: Mapped[str] = mapped_column(String(64))
    output: Mapped[dict[str, Any]] = mapped_column(JSONB)
    model_name: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (UniqueConstraint("kind", "repository_id", "input_hash"),)


class DiscoveryFeedEntry(Base):
    __tablename__ = "discovery_feed_entries"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    feed: Mapped[str] = mapped_column(String(20))
    period: Mapped[str | None] = mapped_column(String(10))
    repository_id: Mapped[uuid.UUID] = _repo_fk()
    rank: Mapped[int] = mapped_column(Integer)
    score: Mapped[float] = mapped_column(Float)
    signals: Mapped[dict[str, Any]] = mapped_column(JSONB)
    basis: Mapped[str] = mapped_column(String(30))
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        Index("ix_discovery_feed_entries_feed_period_rank", "feed", "period", "rank"),
    )


class DiscoveryFeedRun(Base):
    __tablename__ = "discovery_feed_runs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    feed: Mapped[str] = mapped_column(String(20))
    # "" (not NULL) for feeds without periods, so the unique constraint applies.
    period: Mapped[str] = mapped_column(String(10), default="")
    basis: Mapped[str] = mapped_column(String(30))
    entry_count: Mapped[int] = mapped_column(Integer)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    note: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (UniqueConstraint("feed", "period"),)
