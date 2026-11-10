from datetime import UTC, datetime

from app.models import RepositoryChunk
from app.services.evidence import find_evidence
from app.services.recommendation_service import limitations_for
from tests.factories import make_repo


def chunk(content: str, position: int = 0, source_type: str = "readme") -> RepositoryChunk:
    return RepositoryChunk(
        position=position,
        source_type=source_type,
        source_url="https://github.com/acme/x/blob/main/README.md",
        section_title="Features",
        content=content,
        content_hash="x",
    )


def test_snippet_window_and_source():
    text = ("lorem " * 80) + "automatic retries with backoff " + ("ipsum " * 80)
    (ev,) = find_evidence([chunk(text)], ["retries"])
    assert "automatic retries with backoff" in ev.snippet
    assert ev.snippet.startswith("…") and ev.snippet.endswith("…")
    assert len(ev.snippet) <= 340
    assert ev.source_url.endswith("README.md")
    assert ev.section_title == "Features" and ev.source_type == "readme"


def test_word_boundary_no_false_positive():
    assert find_evidence([chunk("Retrying is unsupported; see retryable-x")], ["retry"]) == []
    assert find_evidence([chunk("Automatic retries with backoff")], ["retries"])[0].snippet


def test_readme_evidence_preferred_over_metadata_and_capped():
    chunks = [
        chunk("acme/x: a queue with retries", position=-1, source_type="metadata"),
        chunk("Supports retries per job.", position=0),
        chunk("Retries can be configured.", position=1),
        chunk("More about retries here.", position=2),
    ]
    found = find_evidence(chunks, ["retries"], max_items=2)
    assert [e.source_type for e in found] == ["readme", "readme"]


def test_limitations_are_factual():
    repo = make_repo(
        license_spdx=None,
        license_name=None,
        archived=True,
        pushed_at_github=datetime(2024, 1, 1, tzinfo=UTC),
        source_fetched_at=datetime(2026, 11, 10, tzinfo=UTC),
    )
    lims = limitations_for(repo, uncovered=["scheduling"])
    assert "Archived on GitHub (read-only)" in lims
    assert "No license detected in GitHub metadata" in lims
    assert "Not established from source: scheduling" in lims
    assert any("No push in over 12 months" in item for item in lims)


def test_unrecognised_license_is_flagged_not_guessed():
    repo = make_repo(license_spdx=None, license_name="Other")
    assert any("Other" in item for item in limitations_for(repo, uncovered=[]))
