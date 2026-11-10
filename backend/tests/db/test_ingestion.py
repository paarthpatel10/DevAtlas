from sqlalchemy import func, select

from app.models import (
    Repository,
    RepositoryAnalysis,
    RepositoryChunk,
    RepositoryEmbedding,
    RepositorySnapshot,
    User,
)
from app.services.ingestion_service import ingest_snapshot, seed_from_directory
from app.services.users import DEMO_USER_ID, ensure_demo_user
from tests.factories import FIXTURES_DIR, load_fixture


def count(session, model) -> int:
    return session.scalar(select(func.count()).select_from(model))


def test_seed_is_idempotent(db_session, providers):
    first = seed_from_directory(db_session, FIXTURES_DIR, providers)
    chunks_after_first = count(db_session, RepositoryChunk)
    embeddings_after_first = count(db_session, RepositoryEmbedding)
    second = seed_from_directory(db_session, FIXTURES_DIR, providers)
    assert (first.created, second.created, second.unchanged) == (4, 0, 4)
    assert count(db_session, Repository) == 4
    assert count(db_session, RepositorySnapshot) == 4
    assert count(db_session, RepositoryAnalysis) == 4
    assert count(db_session, RepositoryChunk) == chunks_after_first
    assert count(db_session, RepositoryEmbedding) == embeddings_after_first
    assert chunks_after_first > 4  # metadata chunk + README chunks


def test_rename_updates_in_place(db_session, providers):
    original = load_fixture("acme__jobs.json")
    ingest_snapshot(db_session, original, providers)
    renamed = original.model_copy(
        update={
            "full_name": "acme/jobs-ng",
            "name": "jobs-ng",
            "html_url": "https://github.com/acme/jobs-ng",
        }
    )
    ingest_snapshot(db_session, renamed, providers)
    names = db_session.scalars(select(Repository.full_name)).all()
    assert names == ["acme/jobs-ng"]


def test_changed_readme_rechunks_and_reembeds(db_session, providers):
    original = load_fixture("acme__jobs.json")
    ingest_snapshot(db_session, original, providers)
    changed = original.model_copy(
        update={
            "readme_text": original.readme_text
            + "\n## Webhooks\n\nSend webhooks to your monitoring service when jobs finish or fail."
        }
    )
    result = ingest_snapshot(db_session, changed, providers)
    assert result.content_changed is True and result.created is False
    contents = db_session.scalars(
        select(RepositoryChunk.content).where(RepositoryChunk.repository_id == result.repository_id)
    ).all()
    assert any("webhooks" in c.lower() for c in contents)
    chunk_ids = set(
        db_session.scalars(
            select(RepositoryChunk.id).where(RepositoryChunk.repository_id == result.repository_id)
        )
    )
    embedded_chunk_ids = set(
        db_session.scalars(
            select(RepositoryEmbedding.chunk_id).where(
                RepositoryEmbedding.repository_id == result.repository_id,
                RepositoryEmbedding.kind == "chunk",
            )
        )
    )
    assert embedded_chunk_ids == chunk_ids


def test_new_snapshot_time_adds_history_row(db_session, providers):
    original = load_fixture("acme__jobs.json")
    ingest_snapshot(db_session, original, providers)
    later = original.model_copy(update={"fetched_at": original.fetched_at.replace(day=11)})
    ingest_snapshot(db_session, later, providers)
    assert count(db_session, RepositorySnapshot) == 2


def test_repo_with_missing_fields_ingests(db_session, providers):
    result = ingest_snapshot(db_session, load_fixture("acme__bare.json"), providers)
    repo = db_session.get(Repository, result.repository_id)
    assert repo.license_spdx is None and repo.stars is None and repo.readme_content is None
    assert repo.description is None
    assert repo.search_vector is not None  # metadata chunk still indexed
    assert repo.analysis.summary is None and repo.analysis.capabilities == []


def test_search_vector_and_embeddings_written(db_session, providers):
    result = ingest_snapshot(db_session, load_fixture("acme__jobs.json"), providers)
    kinds = db_session.scalars(
        select(RepositoryEmbedding.kind).where(
            RepositoryEmbedding.repository_id == result.repository_id
        )
    ).all()
    assert kinds.count("summary") == 1 and kinds.count("chunk") >= 2
    repo = db_session.get(Repository, result.repository_id)
    assert "retri" in str(repo.search_vector)


def test_demo_user_created_once(db_session):
    ensure_demo_user(db_session)
    ensure_demo_user(db_session)
    assert count(db_session, User) == 1
    assert db_session.get(User, DEMO_USER_ID).email == "demo@example.com"
