"""Discover: history, releases, AI reports/cache, precomputed feeds.

Revision ID: 0002_discover
Revises: 0001_initial
Create Date: 2026-11-10
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "0002_discover"
down_revision: str | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

NEW_TABLES = (
    "discovery_feed_runs",
    "discovery_feed_entries",
    "ai_generations",
    "repository_insights",
    "repository_releases",
    "repository_daily_stats",
)


def _repo_fk(unique: bool = False) -> sa.Column:
    return sa.Column(
        "repository_id",
        UUID(as_uuid=True),
        sa.ForeignKey("repositories.id", ondelete="CASCADE"),
        nullable=False,
        unique=unique,
    )


def _pk() -> sa.Column:
    return sa.Column("id", UUID(as_uuid=True), primary_key=True)


def upgrade() -> None:
    op.add_column(
        "repositories",
        sa.Column("discovery_source", sa.String(20), nullable=False, server_default="curated"),
    )
    op.add_column(
        "repositories",
        sa.Column("first_indexed_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.execute("UPDATE repositories SET first_indexed_at = created_at")
    for column in ("star_history_since", "fork_history_since", "commit_history_since"):
        op.add_column("repositories", sa.Column(column, sa.Date))

    op.create_table(
        "repository_daily_stats",
        _pk(),
        _repo_fk(),
        sa.Column("day", sa.Date, nullable=False),
        sa.Column("stars_gained", sa.Integer),
        sa.Column("forks_gained", sa.Integer),
        sa.Column("commits", sa.Integer),
        sa.Column("stars_capped", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("forks_capped", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.UniqueConstraint("repository_id", "day"),
    )
    op.create_table(
        "repository_releases",
        _pk(),
        _repo_fk(),
        sa.Column("tag", sa.String(300), nullable=False),
        sa.Column("name", sa.String(500)),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        sa.Column("url", sa.String(500)),
        sa.UniqueConstraint("repository_id", "tag"),
    )
    op.create_table(
        "repository_insights",
        _pk(),
        _repo_fk(unique=True),
        sa.Column("report", JSONB, nullable=False),
        sa.Column("model_name", sa.String(200), nullable=False),
        sa.Column("prompt_version", sa.String(50), nullable=False),
        sa.Column("source_hash", sa.String(64), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "ai_generations",
        _pk(),
        sa.Column("kind", sa.String(30), nullable=False),
        _repo_fk(),
        sa.Column("input_hash", sa.String(64), nullable=False),
        sa.Column("output", JSONB, nullable=False),
        sa.Column("model_name", sa.String(200), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("kind", "repository_id", "input_hash"),
    )
    op.create_table(
        "discovery_feed_entries",
        _pk(),
        sa.Column("feed", sa.String(20), nullable=False),
        sa.Column("period", sa.String(10)),
        _repo_fk(),
        sa.Column("rank", sa.Integer, nullable=False),
        sa.Column("score", sa.Float, nullable=False),
        sa.Column("signals", JSONB, nullable=False),
        sa.Column("basis", sa.String(30), nullable=False),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_discovery_feed_entries_feed_period_rank",
        "discovery_feed_entries",
        ["feed", "period", "rank"],
    )
    op.create_table(
        "discovery_feed_runs",
        _pk(),
        sa.Column("feed", sa.String(20), nullable=False),
        sa.Column("period", sa.String(10), nullable=False, server_default=""),
        sa.Column("basis", sa.String(30), nullable=False),
        sa.Column("entry_count", sa.Integer, nullable=False),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("note", sa.Text),
        sa.UniqueConstraint("feed", "period"),
    )
    for table in ("repository_daily_stats", "repository_releases", "ai_generations",
                  "discovery_feed_entries"):
        op.create_index(f"ix_{table}_repository_id", table, ["repository_id"])


def downgrade() -> None:
    for table in NEW_TABLES:
        op.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
    for column in (
        "commit_history_since",
        "fork_history_since",
        "star_history_since",
        "first_indexed_at",
        "discovery_source",
    ):
        op.drop_column("repositories", column)
