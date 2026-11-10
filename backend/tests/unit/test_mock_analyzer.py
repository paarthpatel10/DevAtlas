from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.ai.repository_analyzer import MockRepositoryAnalyzer
from app.schemas.analysis import RepositoryAnalysisOut
from app.schemas.snapshot import RepoSnapshot
from app.services.chunking import metadata_chunk

FIXED = datetime(2026, 11, 10, tzinfo=UTC)


def snap(**overrides) -> RepoSnapshot:
    values = dict(
        github_id=1,
        full_name="acme/jobs",
        owner="acme",
        name="jobs",
        description="Simple job queue for Python",
        html_url="https://github.com/acme/jobs",
        homepage_url=None,
        topics=["task-queue", "background-jobs"],
        primary_language="Python",
        languages={"Python": 900, "Shell": 50, "Dockerfile": 30, "Makefile": 5},
        license_spdx="MIT",
        license_name="MIT License",
        stars=10,
        forks=1,
        open_issues=0,
        archived=False,
        default_branch="main",
        created_at_github=None,
        updated_at_github=None,
        pushed_at_github=None,
        readme_text=(
            "# jobs\n\nA small library for running background jobs in Python apps.\n\n"
            "## Features\n\n- **Retries** with exponential backoff\n"
            "- Cron-style `scheduling` of periodic tasks\n\n## License\n\nMIT\n"
        ),
        readme_url="https://github.com/acme/jobs/blob/main/README.md",
        readme_truncated=False,
        fetched_at=FIXED,
        category="backend",
        featured=False,
    )
    values.update(overrides)
    return RepoSnapshot(**values)


def test_analyzer_extracts_feature_bullets_with_evidence():
    a = MockRepositoryAnalyzer().analyze(snap())
    assert [c.name for c in a.capabilities] == [
        "Retries with exponential backoff",
        "Cron-style scheduling of periodic tasks",
    ]
    assert a.capabilities[0].evidence == ["**Retries** with exponential backoff"]
    assert a.capabilities[0].confidence == "medium"
    assert a.summary == "Simple job queue for Python"
    assert a.category == "backend"
    assert a.supported_languages == ["Python", "Shell", "Dockerfile"]
    assert a.keywords == ["task queue", "background jobs"]
    assert a.maturity == "unknown"
    assert (a.analysis_version, a.model_name, a.prompt_version) == (
        "mock-extractive-v1",
        "mock",
        "none",
    )


def test_summary_falls_back_to_first_readme_paragraph():
    a = MockRepositoryAnalyzer().analyze(snap(description=None))
    assert a.summary == "A small library for running background jobs in Python apps."


def test_analyzer_never_invents_fields_when_readme_missing():
    a = MockRepositoryAnalyzer().analyze(snap(readme_text=None, description=None))
    assert a.summary is None
    assert a.capabilities == []
    assert a.problem_solved is None
    assert a.use_cases == [] and a.limitations == [] and a.integrations == []


def test_archived_repo_marked_inactive():
    assert MockRepositoryAnalyzer().analyze(snap(archived=True)).maturity == "inactive"


def test_capability_names_truncated_at_word_boundary():
    long = "- " + "capability " * 20 + "\n"
    a = MockRepositoryAnalyzer().analyze(snap(readme_text="## Features\n\n" + long))
    assert len(a.capabilities[0].name) <= 80
    assert not a.capabilities[0].name.endswith(" ")


def test_analysis_schema_rejects_unknown_fields():
    data = MockRepositoryAnalyzer().analyze(snap()).model_dump()
    data["invented"] = "x"
    with pytest.raises(ValidationError):
        RepositoryAnalysisOut(**data)


def test_metadata_chunk():
    c = metadata_chunk(snap())
    assert c.position == -1 and c.source_type == "metadata"
    assert "acme/jobs" in c.content and "task queue" in c.content
    assert c.source_url == "https://github.com/acme/jobs"
