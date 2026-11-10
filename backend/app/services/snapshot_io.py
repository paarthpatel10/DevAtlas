"""Export/import of history and AI reports, so a fresh database can be seeded offline.

Records are keyed by GitHub repository id (stable across renames). Imports are idempotent.
"""

import json
import uuid
from datetime import date, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models import Repository, RepositoryDailyStat, RepositoryInsight, RepositoryRelease
from app.schemas.snapshot import snapshot_stem


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _repos_by_github_id(session: Session) -> dict[int, Repository]:
    return {r.github_id: r for r in session.scalars(select(Repository))}


def _date(value: str | None) -> date | None:
    return date.fromisoformat(value) if value else None


def _dt(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


def export_history(session: Session, path: Path) -> None:
    payload: dict[str, Any] = {}
    for repo in session.scalars(select(Repository).order_by(Repository.full_name)):
        stats = session.scalars(
            select(RepositoryDailyStat)
            .where(RepositoryDailyStat.repository_id == repo.id)
            .order_by(RepositoryDailyStat.day)
        ).all()
        releases = session.scalars(
            select(RepositoryRelease)
            .where(RepositoryRelease.repository_id == repo.id)
            .order_by(RepositoryRelease.tag)
        ).all()
        if not stats and not releases:
            continue
        payload[str(repo.github_id)] = {
            "full_name": repo.full_name,
            "star_history_since": repo.star_history_since,
            "fork_history_since": repo.fork_history_since,
            "commit_history_since": repo.commit_history_since,
            "daily": [
                [s.day, s.stars_gained, s.forks_gained, s.commits, s.stars_capped, s.forks_capped]
                for s in stats
            ],
            "releases": [
                {"tag": r.tag, "name": r.name, "published_at": r.published_at, "url": r.url}
                for r in releases
            ],
        }
    _write_json(path, payload)


def import_history(session: Session, path: Path) -> int:
    if not path.exists():
        return 0
    data = json.loads(path.read_text(encoding="utf-8"))
    repos = _repos_by_github_id(session)
    imported = 0
    for github_id, record in data.items():
        repo = repos.get(int(github_id))
        if repo is None:
            continue
        for day, stars, forks, commits, stars_capped, forks_capped in record["daily"]:
            values = {
                "stars_gained": stars,
                "forks_gained": forks,
                "commits": commits,
                "stars_capped": stars_capped,
                "forks_capped": forks_capped,
            }
            session.execute(
                insert(RepositoryDailyStat)
                .values(
                    id=uuid.uuid4(), repository_id=repo.id, day=date.fromisoformat(day), **values
                )
                .on_conflict_do_update(index_elements=["repository_id", "day"], set_=values)
            )
        for release in record["releases"]:
            values = {
                "name": release["name"],
                "published_at": _dt(release["published_at"]),
                "url": release["url"],
            }
            session.execute(
                insert(RepositoryRelease)
                .values(id=uuid.uuid4(), repository_id=repo.id, tag=release["tag"], **values)
                .on_conflict_do_update(index_elements=["repository_id", "tag"], set_=values)
            )
        for field in ("star_history_since", "fork_history_since", "commit_history_since"):
            exported = _date(record.get(field))
            current = getattr(repo, field)
            if exported is not None and (current is None or exported < current):
                setattr(repo, field, exported)
        imported += 1
    session.flush()
    return imported


def export_insights(session: Session, directory: Path) -> int:
    directory.mkdir(parents=True, exist_ok=True)
    rows = session.execute(
        select(RepositoryInsight, Repository).join(
            Repository, Repository.id == RepositoryInsight.repository_id
        )
    ).all()
    for insight, repo in rows:
        _write_json(
            directory / f"{snapshot_stem(repo.full_name)}.json",
            {
                "github_id": repo.github_id,
                "full_name": repo.full_name,
                "model_name": insight.model_name,
                "prompt_version": insight.prompt_version,
                "source_hash": insight.source_hash,
                "generated_at": insight.generated_at,
                "report": insight.report,
            },
        )
    return len(rows)


def import_insights(session: Session, directory: Path) -> int:
    if not directory.exists():
        return 0
    repos = _repos_by_github_id(session)
    imported = 0
    for path in sorted(directory.glob("*.json")):
        record = json.loads(path.read_text(encoding="utf-8"))
        repo = repos.get(int(record["github_id"]))
        if repo is None:
            continue
        values = {
            "report": record["report"],
            "model_name": record["model_name"],
            "prompt_version": record["prompt_version"],
            "source_hash": record["source_hash"],
            "generated_at": _dt(record["generated_at"]),
        }
        session.execute(
            insert(RepositoryInsight)
            .values(id=uuid.uuid4(), repository_id=repo.id, **values)
            .on_conflict_do_update(index_elements=["repository_id"], set_=values)
        )
        imported += 1
    session.flush()
    return imported
