import pytest
from sqlalchemy import inspect
from sqlalchemy.exc import IntegrityError

from tests.factories import make_repo


def test_migrations_create_schema_from_clean_database(db_engine):
    tables = set(inspect(db_engine).get_table_names())
    assert {
        "users",
        "repositories",
        "repository_analyses",
        "repository_chunks",
        "repository_embeddings",
        "repository_snapshots",
        "saved_repositories",
    } <= tables


def test_github_id_is_unique(db_session):
    db_session.add_all(
        [make_repo(github_id=1, full_name="a/x"), make_repo(github_id=1, full_name="a/y")]
    )
    with pytest.raises(IntegrityError):
        db_session.flush()


def test_full_name_unique_case_insensitive(db_session):
    db_session.add_all(
        [make_repo(github_id=1, full_name="Org/Repo"), make_repo(github_id=2, full_name="org/repo")]
    )
    with pytest.raises(IntegrityError):
        db_session.flush()


def test_vector_extension_installed(db_session):
    from sqlalchemy import text

    assert db_session.scalar(text("SELECT count(*) FROM pg_extension WHERE extname='vector'")) == 1
