"""Build the committed seed snapshot from the GitHub API (resumable, idempotent)."""

import json
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

from app.schemas.snapshot import CuratedEntry, RepoSnapshot, snapshot_stem
from app.services.github_client import GitHubError, GitHubRateLimited, ReadmeResult

logger = logging.getLogger(__name__)


class RepoSource(Protocol):
    def get_repository(self, full_name: str) -> dict: ...
    def get_readme(self, full_name: str) -> ReadmeResult | None: ...
    def get_languages(self, full_name: str) -> dict[str, int]: ...


@dataclass
class BuildReport:
    written: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    failed: dict[str, str] = field(default_factory=dict)
    rate_limited_until: datetime | None = None


def snapshot_filename(full_name: str) -> str:
    return f"{snapshot_stem(full_name)}.json"


def write_snapshot(path: Path, snapshot: RepoSnapshot) -> None:
    payload = json.dumps(
        snapshot.model_dump(mode="json"), indent=2, ensure_ascii=False, sort_keys=True
    )
    path.write_text(payload + "\n", encoding="utf-8", newline="\n")


def build_snapshot(
    client: RepoSource,
    entries: list[CuratedEntry],
    out_dir: Path,
    *,
    refresh: bool = False,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> BuildReport:
    out_dir.mkdir(parents=True, exist_ok=True)
    report = BuildReport()
    for entry in entries:
        key = entry.full_name.lower()
        path = out_dir / snapshot_filename(entry.full_name)
        if path.exists() and not refresh:
            report.skipped.append(key)
            continue
        try:
            repo = client.get_repository(entry.full_name)
            readme = client.get_readme(entry.full_name)
            languages = client.get_languages(entry.full_name)
        except GitHubRateLimited as exc:
            report.rate_limited_until = exc.reset_at or now()
            logger.warning("Rate limited at %s; stopping.", key)
            break
        except GitHubError as exc:
            report.failed[key] = str(exc)
            continue
        write_snapshot(path, RepoSnapshot.from_github(repo, readme, languages, entry, now()))
        report.written.append(key)
    return report
