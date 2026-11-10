"""Initial schema: users, repositories, analyses, chunks, embeddings, snapshots, saves.

Revision ID: 0001_initial
Revises:
Create Date: 2026-11-10
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import VECTOR
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR, UUID

revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

EMBEDDING_DIM = 1024


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    ]


def _uuid_pk() -> sa.Column:
    return sa.Column("id", UUID(as_uuid=True), primary_key=True)


def _fk(column: str, target: str, nullable: bool = False) -> sa.Column:
    return sa.Column(
        column, UUID(as_uuid=True), sa.ForeignKey(target, ondelete="CASCADE"), nullable=nullable
    )


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "users",
        _uuid_pk(),
        sa.Column("email", sa.String(320), nullable=False, unique=True),
        sa.Column("display_name", sa.String(200), nullable=False),
        *_timestamps(),
    )

    op.create_table(
        "repositories",
        _uuid_pk(),
        sa.Column("github_id", sa.BigInteger, nullable=False, unique=True),
        sa.Column("owner", sa.String(200), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("full_name", sa.String(401), nullable=False),
        sa.Column("description", sa.Text),
        sa.Column("html_url", sa.String(500), nullable=False),
        sa.Column("homepage_url", sa.String(500)),
        sa.Column("readme_url", sa.String(500)),
        sa.Column("readme_content", sa.Text),
        sa.Column("readme_truncated", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("primary_language", sa.String(100)),
        sa.Column("languages", JSONB, nullable=False, server_default="{}"),
        sa.Column("topics", JSONB, nullable=False, server_default="[]"),
        sa.Column("license_spdx", sa.String(100)),
        sa.Column("license_name", sa.String(200)),
        sa.Column("stars", sa.Integer),
        sa.Column("forks", sa.Integer),
        sa.Column("open_issues", sa.Integer),
        sa.Column("created_at_github", sa.DateTime(timezone=True)),
        sa.Column("updated_at_github", sa.DateTime(timezone=True)),
        sa.Column("pushed_at_github", sa.DateTime(timezone=True)),
        sa.Column("archived", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("default_branch", sa.String(200)),
        sa.Column("category", sa.String(50), nullable=False),
        sa.Column("featured", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("data_source", sa.String(30), nullable=False),
        sa.Column("source_fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_ingested_at", sa.DateTime(timezone=True)),
        sa.Column("last_refreshed_at", sa.DateTime(timezone=True)),
        sa.Column("search_vector", TSVECTOR),
        *_timestamps(),
    )
    op.create_index(
        "uq_repositories_full_name_lower",
        "repositories",
        [sa.text("lower(full_name)")],
        unique=True,
    )
    op.create_index(
        "ix_repositories_search_vector", "repositories", ["search_vector"], postgresql_using="gin"
    )
    op.create_index("ix_repositories_category", "repositories", ["category"])
    op.create_index("ix_repositories_primary_language", "repositories", ["primary_language"])
    op.create_index("ix_repositories_license_spdx", "repositories", ["license_spdx"])

    op.create_table(
        "repository_analyses",
        _uuid_pk(),
        _fk("repository_id", "repositories.id"),
        sa.Column("summary", sa.Text),
        sa.Column("problem_solved", sa.Text),
        sa.Column("category", sa.String(50)),
        sa.Column("subcategory", sa.String(100)),
        sa.Column("capabilities", JSONB, nullable=False, server_default="[]"),
        sa.Column("use_cases", JSONB, nullable=False, server_default="[]"),
        sa.Column("supported_languages", JSONB, nullable=False, server_default="[]"),
        sa.Column("integrations", JSONB, nullable=False, server_default="[]"),
        sa.Column("requirements", JSONB, nullable=False, server_default="[]"),
        sa.Column("limitations", JSONB, nullable=False, server_default="[]"),
        sa.Column("maturity", sa.String(30), nullable=False, server_default="unknown"),
        sa.Column("target_users", JSONB, nullable=False, server_default="[]"),
        sa.Column("keywords", JSONB, nullable=False, server_default="[]"),
        sa.Column("analysis_version", sa.String(50), nullable=False),
        sa.Column("model_name", sa.String(200), nullable=False),
        sa.Column("prompt_version", sa.String(50), nullable=False),
        *_timestamps(),
        sa.UniqueConstraint("repository_id"),
    )

    op.create_table(
        "repository_chunks",
        _uuid_pk(),
        _fk("repository_id", "repositories.id"),
        sa.Column("position", sa.Integer, nullable=False),
        sa.Column("source_type", sa.String(30), nullable=False),
        sa.Column("source_url", sa.String(500)),
        sa.Column("section_title", sa.String(500)),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("repository_id", "position"),
    )
    op.create_index("ix_repository_chunks_repository_id", "repository_chunks", ["repository_id"])

    op.create_table(
        "repository_embeddings",
        _uuid_pk(),
        _fk("repository_id", "repositories.id"),
        _fk("chunk_id", "repository_chunks.id", nullable=True),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("embedding", VECTOR(EMBEDDING_DIM), nullable=False),
        sa.Column("embedding_model", sa.String(200), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index(
        "ix_repository_embeddings_repository_id", "repository_embeddings", ["repository_id"]
    )
    op.create_index("ix_repository_embeddings_chunk_id", "repository_embeddings", ["chunk_id"])
    op.create_index(
        "ix_repository_embeddings_embedding_hnsw",
        "repository_embeddings",
        ["embedding"],
        postgresql_using="hnsw",
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )

    op.create_table(
        "repository_snapshots",
        _uuid_pk(),
        _fk("repository_id", "repositories.id"),
        sa.Column("stars", sa.Integer),
        sa.Column("forks", sa.Integer),
        sa.Column("open_issues", sa.Integer),
        sa.Column("snapshot_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("repository_id", "snapshot_at"),
    )
    op.create_index(
        "ix_repository_snapshots_repository_id", "repository_snapshots", ["repository_id"]
    )

    op.create_table(
        "saved_repositories",
        _uuid_pk(),
        _fk("user_id", "users.id"),
        _fk("repository_id", "repositories.id"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("user_id", "repository_id"),
    )
    op.create_index("ix_saved_repositories_user_id", "saved_repositories", ["user_id"])
    op.create_index("ix_saved_repositories_repository_id", "saved_repositories", ["repository_id"])


def downgrade() -> None:
    for table in (
        "saved_repositories",
        "repository_snapshots",
        "repository_embeddings",
        "repository_chunks",
        "repository_analyses",
        "repositories",
        "users",
    ):
        op.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
