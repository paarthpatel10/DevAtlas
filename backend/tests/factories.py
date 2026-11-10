"""Test data builders (test-only helpers)."""

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.models import Repository
from app.schemas.snapshot import RepoSnapshot

FIXED_TIME = datetime(2026, 11, 10, tzinfo=UTC)
FIXTURES_DIR = Path(__file__).parent / "fixtures" / "snapshots"


def load_fixture(name: str) -> RepoSnapshot:
    return RepoSnapshot(**json.loads((FIXTURES_DIR / name).read_text(encoding="utf-8")))


def make_repo(**overrides: Any) -> Repository:
    full_name = overrides.pop("full_name", "acme/example")
    owner, name = full_name.split("/", 1)
    values: dict[str, Any] = {
        "github_id": 1,
        "owner": owner,
        "name": name,
        "full_name": full_name,
        "description": "Example repository",
        "html_url": f"https://github.com/{full_name}",
        "category": "backend",
        "featured": False,
        "data_source": "seed_snapshot",
        "source_fetched_at": FIXED_TIME,
        "archived": False,
        "topics": [],
        "languages": {},
    }
    values.update(overrides)
    return Repository(**values)
