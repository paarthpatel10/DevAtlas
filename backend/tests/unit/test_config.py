import pytest

from app.config import Settings, to_psycopg_url


@pytest.mark.parametrize(
    ("given", "expected"),
    [
        (
            "postgresql://u:p@ep-x-pooler.neon.tech/db?sslmode=require",
            "postgresql+psycopg://u:p@ep-x-pooler.neon.tech/db?sslmode=require",
        ),
        ("postgres://u:p@h/db", "postgresql+psycopg://u:p@h/db"),
        ("postgresql+psycopg://u:p@h/db", "postgresql+psycopg://u:p@h/db"),
        (None, None),
    ],
)
def test_to_psycopg_url(given, expected):
    assert to_psycopg_url(given) == expected


def test_settings_normalize_neon_urls_and_prefer_unpooled_for_migrations():
    s = Settings(
        _env_file=None,
        database_url="postgresql://u:p@ep-x-pooler.neon.tech/db",
        database_url_unpooled="postgresql://u:p@ep-x.neon.tech/db",
    )
    assert s.database_url == "postgresql+psycopg://u:p@ep-x-pooler.neon.tech/db"
    assert s.migration_database_url == "postgresql+psycopg://u:p@ep-x.neon.tech/db"


def test_migration_url_falls_back_to_pooled_url():
    s = Settings(_env_file=None, database_url="postgresql://u:p@h/db")
    assert s.migration_database_url == "postgresql+psycopg://u:p@h/db"


def test_neon_style_env_names_are_accepted(tmp_path, monkeypatch):
    for key in ("DATABASE_URL", "TEST_DATABASE_URL", "NEON_DB", "NEON_DB_TEST"):
        monkeypatch.delenv(key, raising=False)
    env = tmp_path / ".env"
    env.write_text(
        "neon_db = postgresql://u:p@main-pooler.neon.tech/db\n"
        "neon_db_test = postgresql://u:p@test-pooler.neon.tech/db\n",
        encoding="utf-8",
    )
    s = Settings(_env_file=env)
    assert s.database_url == "postgresql+psycopg://u:p@main-pooler.neon.tech/db"
    assert s.test_database_url == "postgresql+psycopg://u:p@test-pooler.neon.tech/db"


def test_standard_names_still_work_as_keywords():
    s = Settings(_env_file=None, test_database_url="postgresql://u:p@h/t")
    assert s.test_database_url == "postgresql+psycopg://u:p@h/t"
