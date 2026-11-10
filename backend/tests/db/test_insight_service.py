from datetime import UTC, datetime

import pytest
from sqlalchemy import func, select

from app.ai.gemini_provider import LLMUnavailableError
from app.models import Repository, RepositoryChunk, RepositoryInsight
from app.services.insight_service import generate_insight, get_report
from tests.fakes import FakeLLM, report_citing_first_source

NOW = datetime(2026, 11, 10, tzinfo=UTC)


def jobs(session) -> Repository:
    return session.scalar(select(Repository).where(Repository.full_name == "acme/jobs"))


def count(session) -> int:
    return session.scalar(select(func.count()).select_from(RepositoryInsight))


def test_generate_store_skip_and_regenerate(db_session, providers):
    from app.services.ingestion_service import seed_from_directory
    from tests.factories import FIXTURES_DIR

    seed_from_directory(db_session, FIXTURES_DIR, providers)
    llm = FakeLLM(report_citing_first_source)
    repo = jobs(db_session)

    stored = generate_insight(db_session, repo, llm, NOW)
    assert stored is not None and stored.model_name == "fake:llm"
    assert stored.report["what_is_it"]["one_line"].startswith("A background job queue")
    assert stored.report["build_ideas"][0]["citations"][0]["id"] == "C2"
    assert len(llm.calls) == 1

    assert generate_insight(db_session, repo, llm, NOW) is None  # unchanged sources
    assert len(llm.calls) == 1

    chunk = db_session.scalar(
        select(RepositoryChunk).where(
            RepositoryChunk.repository_id == repo.id, RepositoryChunk.position == 0
        )
    )
    chunk.content_hash = "changed"
    db_session.flush()
    report, insight, stale = get_report(db_session, repo)
    assert stale is True and report.generated is True
    assert generate_insight(db_session, repo, llm, NOW) is not None
    assert len(llm.calls) == 2 and count(db_session) == 1


def test_llm_failure_stores_nothing(db_session, providers):
    from app.services.ingestion_service import seed_from_directory
    from tests.factories import FIXTURES_DIR

    seed_from_directory(db_session, FIXTURES_DIR, providers)
    with pytest.raises(LLMUnavailableError):
        generate_insight(db_session, jobs(db_session), FakeLLM(fail=True), NOW)
    assert count(db_session) == 0


def test_report_without_stored_insight_is_extractive(db_session, providers):
    from app.services.ingestion_service import seed_from_directory
    from tests.factories import FIXTURES_DIR

    seed_from_directory(db_session, FIXTURES_DIR, providers)
    report, insight, stale = get_report(db_session, jobs(db_session))
    assert insight is None and stale is False
    assert report.generated is False
    assert report.what_is_it.one_line == "Lightweight background job queue for Python web apps"
