"""GitHub Trending daily observations.

Revision ID: 0003_github_trending
Revises: 0002_discover
Create Date: 2026-11-10
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "0003_github_trending"
down_revision: str | None = "0002_discover"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "github_trending_observations",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("day", sa.Date, nullable=False),
        sa.Column("scope", sa.String(60), nullable=False),
        sa.Column("rank", sa.Integer, nullable=False),
        sa.Column("full_name", sa.String(401), nullable=False),
        sa.Column(
            "repository_id",
            UUID(as_uuid=True),
            sa.ForeignKey("repositories.id", ondelete="CASCADE"),
        ),
        sa.Column("stars_today", sa.Integer, nullable=False),
        sa.Column("stars_total", sa.Integer),
        sa.Column("forks_total", sa.Integer),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("day", "scope", "full_name"),
    )
    op.create_index("ix_github_trending_observations_day", "github_trending_observations", ["day"])
    op.create_index(
        "ix_github_trending_observations_repository_id",
        "github_trending_observations",
        ["repository_id"],
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS github_trending_observations CASCADE")
