import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.config import BACKEND_DIR
from app.schemas.snapshot import (
    CATEGORY_LABELS,
    README_MAX_CHARS,
    CuratedEntry,
    RepoSnapshot,
    load_curated,
)
from app.services.github_client import GitHubNotFound, GitHubRateLimited, ReadmeResult
from app.services.snapshot_builder import build_snapshot

FIXED = datetime(2026, 11, 10, 9, 0, tzinfo=UTC)


def repo_json(full_name: str = "celery/celery", **overrides):
    owner, name = full_name.split("/")
    data = {
        "id": 123,
        "full_name": full_name,
        "name": name,
        "owner": {"login": owner},
        "description": "Distributed Task Queue",
        "html_url": f"https://github.com/{full_name}",
        "homepage": "https://docs.celeryq.dev",
        "topics": ["task-queue", "python"],
        "language": "Python",
        "license": {"spdx_id": "BSD-3-Clause", "name": "BSD 3-Clause License"},
        "stargazers_count": 1000,
        "forks_count": 10,
        "open_issues_count": 5,
        "archived": False,
        "default_branch": "main",
        "created_at": "2009-04-24T12:00:00Z",
        "updated_at": "2026-11-01T12:00:00Z",
        "pushed_at": "2026-11-01T12:00:00Z",
    }
    data.update(overrides)
    return data


class FakeClient:
    def __init__(self, repos=None, missing=(), rate_limit_on=None):
        self.repos = repos or {}
        self.missing = {m.lower() for m in missing}
        self.rate_limit_on = rate_limit_on
        self.calls: list[str] = []

    def get_repository(self, full_name):
        self.calls.append(full_name)
        if self.rate_limit_on and full_name.lower() == self.rate_limit_on:
            raise GitHubRateLimited("limit", reset_at=FIXED)
        if full_name.lower() in self.missing:
            raise GitHubNotFound(full_name)
        return self.repos.get(full_name.lower()) or repo_json(full_name.lower())

    def get_readme(self, full_name):
        return ReadmeResult("# Celery\n\nTask queue.", "https://github.com/x/README.md", None)

    def get_languages(self, full_name):
        return {"Python": 900, "Shell": 100}


def entry(full_name: str, category="backend", featured=False) -> CuratedEntry:
    return CuratedEntry(full_name=full_name, category=category, featured=featured)


def test_writes_snapshot_and_skips_existing(tmp_path: Path):
    report = build_snapshot(FakeClient(), [entry("Celery/Celery")], tmp_path, now=lambda: FIXED)
    assert report.written == ["celery/celery"]
    data = json.loads((tmp_path / "celery__celery.json").read_text(encoding="utf-8"))
    assert data["github_id"] == 123
    assert data["category"] == "backend"
    assert data["readme_text"].startswith("# Celery")
    assert data["languages"] == {"Python": 900, "Shell": 100}

    client = FakeClient()
    again = build_snapshot(client, [entry("celery/celery")], tmp_path, now=lambda: FIXED)
    assert again.skipped == ["celery/celery"]
    assert client.calls == []


def test_refresh_rewrites_existing(tmp_path: Path):
    build_snapshot(FakeClient(), [entry("celery/celery")], tmp_path, now=lambda: FIXED)
    report = build_snapshot(
        FakeClient(), [entry("celery/celery")], tmp_path, refresh=True, now=lambda: FIXED
    )
    assert report.written == ["celery/celery"]


def test_not_found_recorded_and_build_continues(tmp_path: Path):
    report = build_snapshot(
        FakeClient(missing=["gone/repo"]),
        [entry("gone/repo"), entry("celery/celery")],
        tmp_path,
        now=lambda: FIXED,
    )
    assert "gone/repo" in report.failed
    assert report.written == ["celery/celery"]


def test_rate_limit_stops_build_and_reports_reset(tmp_path: Path):
    client = FakeClient(rate_limit_on="b/b")
    report = build_snapshot(
        client, [entry("a/a"), entry("b/b"), entry("c/c")], tmp_path, now=lambda: FIXED
    )
    assert report.written == ["a/a"]
    assert report.rate_limited_until == FIXED
    assert "c/c" not in client.calls


def test_noassertion_license_becomes_unknown_spdx():
    snap = RepoSnapshot.from_github(
        repo_json(license={"spdx_id": "NOASSERTION", "name": "Other"}),
        None,
        {},
        entry("celery/celery"),
        FIXED,
    )
    assert snap.license_spdx is None
    assert snap.license_name == "Other"


def test_missing_license_and_readme():
    snap = RepoSnapshot.from_github(
        repo_json(license=None, description=None), None, {}, entry("celery/celery"), FIXED
    )
    assert snap.license_spdx is None and snap.license_name is None
    assert snap.readme_text is None and snap.readme_url is None
    assert snap.description is None


def test_readme_truncated_at_limit():
    readme = ReadmeResult("x" * (README_MAX_CHARS + 1), "https://g/README.md", None)
    snap = RepoSnapshot.from_github(repo_json(), readme, {}, entry("celery/celery"), FIXED)
    assert len(snap.readme_text or "") == README_MAX_CHARS
    assert snap.readme_truncated is True


def test_renamed_repo_uses_canonical_name():
    snap = RepoSnapshot.from_github(
        repo_json("kludex/starlette"), None, {}, entry("encode/starlette"), FIXED
    )
    assert snap.full_name == "kludex/starlette"
    assert snap.owner == "kludex"


def test_curated_list_rejects_case_insensitive_duplicates(tmp_path: Path):
    path = tmp_path / "c.yaml"
    path.write_text("backend:\n  - celery/celery\n  - Celery/Celery\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Duplicate"):
        load_curated(path)


def test_repo_curated_file_is_valid():
    entries = load_curated(BACKEND_DIR / "data" / "curated_repositories.yaml")
    assert len(entries) == 71
    assert {e.category for e in entries} == set(CATEGORY_LABELS)
    assert len(CATEGORY_LABELS) == 12
    by_name = {e.full_name: e.category for e in entries}
    assert by_name["vercel/next.js"] == "full_stack"
    assert by_name["modelcontextprotocol/python-sdk"] == "mcp_automation"
    assert by_name["ory/kratos"] == "security"
    assert sum(e.featured for e in entries) == 9
