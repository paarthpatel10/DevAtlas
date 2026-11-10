"""Side-by-side comparison on consistent dimensions (spec 6.7). No winner is chosen."""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError
from app.models import RepositoryRelease
from app.schemas.insights import CompareOut, CompareRow
from app.services.chunking import detect_format
from app.services.discover_ranking import readme_completeness
from app.services.insight_service import get_report
from app.services.repository_service import get_by_full_name, saved_ids, to_card

DIMENSIONS = [
    "Primary purpose",
    "Core capabilities",
    "Languages and platforms",
    "Integrations",
    "Prerequisites",
    "Maintenance signals",
    "License",
    "Documentation",
    "Strengths",
    "Limitations",
]


def _join(items: list[str], limit: int = 4) -> str | None:
    items = [i for i in items if i]
    return "; ".join(items[:limit]) if items else None


def _documentation(score: float) -> str:
    if score >= 0.75:
        return "README covers installation, usage and features"
    if score >= 0.5:
        return "README covers the basics"
    if score > 0:
        return "README is brief"
    return "No README indexed"


def compare(session: Session, names: list[str], user_id: uuid.UUID) -> CompareOut:
    repos = []
    for name in names:
        owner, _, repo_name = name.partition("/")
        if not owner or not repo_name:
            raise NotFoundError(f"Repository {name} not found")
        repos.append(get_by_full_name(session, owner, repo_name))
    saved = saved_ids(session, user_id, (r.id for r in repos))
    rows = []
    for repo in repos:
        report, _, _ = get_report(session, repo)
        release = session.scalar(
            select(RepositoryRelease)
            .where(RepositoryRelease.repository_id == repo.id)
            .order_by(RepositoryRelease.published_at.desc().nulls_last())
        )
        maintenance = []
        if repo.pushed_at_github:
            maintenance.append(f"last push {repo.pushed_at_github:%Y-%m-%d}")
        if release and release.published_at:
            maintenance.append(f"latest release {release.tag} on {release.published_at:%Y-%m-%d}")
        if repo.archived:
            maintenance.append("archived")
        capabilities = [c.name for c in report.technical.capabilities] or [
            c["name"] for c in (repo.analysis.capabilities if repo.analysis else [])
        ]
        languages = [repo.primary_language or ""] + [n.name for n in report.technical.frameworks]
        values = {
            "Primary purpose": report.what_is_it.one_line if report.what_is_it else None,
            "Core capabilities": _join(capabilities),
            "Languages and platforms": _join(list(dict.fromkeys(languages))),
            "Integrations": _join([n.name for n in report.technical.integrations]),
            "Prerequisites": _join([p.text for p in report.technical.prerequisites]),
            "Maintenance signals": _join(maintenance) if maintenance else None,
            "License": repo.license_spdx
            or (f"{repo.license_name} (not identified by GitHub)" if repo.license_name else None),
            "Documentation": _documentation(
                readme_completeness(repo.readme_content, detect_format(repo.readme_url))
            ),
            "Strengths": _join([p.point for p in report.why_interesting], 2),
            "Limitations": _join([item.text for item in report.limitations], 3),
        }
        fits_when = [f"{a.audience}: {a.reason}" for a in report.who_should_care][:3]
        fits_when += [u.text for u in report.use_cases][: max(0, 4 - len(fits_when))]
        rows.append(
            CompareRow(
                repository=to_card(repo, repo.id in saved), values=values, fits_when=fits_when
            )
        )
    return CompareOut(dimensions=DIMENSIONS, rows=rows)
