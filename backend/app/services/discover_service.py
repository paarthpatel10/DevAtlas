"""Build ranking signals from stored history, precompute feeds, and serve them.

Feeds are recomputed by `scripts/compute_feeds.py`; requests only read the stored result.
"""

import uuid
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models import (
    DiscoveryFeedEntry,
    DiscoveryFeedRun,
    Repository,
    RepositoryDailyStat,
    RepositoryInsight,
    RepositoryRelease,
)
from app.schemas.discover import CategorySummary, DiscoverItem, FeedPage
from app.services.activity_client import ReleaseInfo
from app.services.chunking import detect_format
from app.services.discover_ranking import (
    FeedEntry,
    RankingConfig,
    RepoSignals,
    rank_hidden_gems,
    rank_new,
    rank_rising,
    rank_trending,
    rank_weekly,
    readme_completeness,
)
from app.services.history_service import growth
from app.services.repository_service import category_label, saved_ids, to_card
from app.services.search_service import SearchFilters, apply_filters

WINDOWS = (1, 7, 30)
RELEASE_LIMIT = 20  # releases fetched per repository; fewer means the list is complete
FEED_STORE = {"hidden-gems": "hidden_gem"}  # API name -> stored feed name


# ---- Signals ----------------------------------------------------------------------------


def _active_weeks(session: Session, repo: Repository, today: date) -> int | None:
    coverage = repo.commit_history_since
    if coverage is None or coverage > today - timedelta(days=27):
        return None
    rows = session.execute(
        select(RepositoryDailyStat.day, RepositoryDailyStat.commits).where(
            RepositoryDailyStat.repository_id == repo.id,
            RepositoryDailyStat.day > today - timedelta(days=28),
            RepositoryDailyStat.day <= today,
        )
    ).all()
    weeks = {(today - day).days // 7 for day, commits in rows if commits}
    return len(weeks)


def build_signals(session: Session, now: datetime) -> list[RepoSignals]:
    today = now.date()
    repos = session.scalars(select(Repository).where(Repository.archived.is_(False))).all()
    signals: list[RepoSignals] = []
    for repo in repos:
        releases = session.scalars(
            select(RepositoryRelease)
            .where(RepositoryRelease.repository_id == repo.id)
            .order_by(RepositoryRelease.published_at.desc().nulls_last())
        ).all()
        latest = releases[0] if releases else None
        published = [r.published_at for r in releases if r.published_at]
        signals.append(
            RepoSignals(
                repository_id=repo.id,
                category=repo.category,
                discovery_source=repo.discovery_source,
                stars=repo.stars,
                forks=repo.forks,
                created_at=repo.created_at_github,
                first_indexed_at=repo.first_indexed_at,
                pushed_at=repo.pushed_at_github,
                has_license=bool(repo.license_spdx or repo.license_name),
                readme_completeness=readme_completeness(
                    repo.readme_content, detect_format(repo.readme_url)
                ),
                stars_gained={d: growth(session, repo, "stars", d, today) for d in WINDOWS},
                forks_gained={d: growth(session, repo, "forks", d, today) for d in WINDOWS},
                commits={d: growth(session, repo, "commits", d, today) for d in WINDOWS},
                active_weeks_of_last_4=_active_weeks(session, repo, today),
                latest_release=(
                    ReleaseInfo(latest.tag, latest.name, latest.published_at, latest.url)
                    if latest
                    else None
                ),
                first_release_at=(
                    min(published) if published and len(releases) < RELEASE_LIMIT else None
                ),
            )
        )
    return signals


# ---- Computation ------------------------------------------------------------------------


def compute_feeds(session: Session, cfg: RankingConfig, now: datetime) -> dict[str, int]:
    signals = build_signals(session, now)
    results: dict[tuple[str, str], tuple[list[FeedEntry], str]] = {}
    for period in ("day", "week", "month", "all"):
        entries, basis = rank_trending(signals, period, cfg, now)
        results[("trending", period)] = (entries, basis)
    rising, rising_basis = rank_rising(signals, cfg, now)
    results[("rising", "")] = (rising, rising_basis)
    results[("new", "")] = (rank_new(signals, cfg, now), "growth")
    results[("hidden_gem", "")] = (rank_hidden_gems(signals, cfg, now), "growth")
    weekly_inputs = {
        "trending": results[("trending", "week")][0]
        if results[("trending", "week")][1] == "growth"
        else [],
        "rising": rising,
        "new": results[("new", "")][0],
        "hidden_gem": results[("hidden_gem", "")][0],
    }
    by_id = {s.repository_id: s for s in signals}
    results[("weekly", "")] = (rank_weekly(weekly_inputs, by_id, cfg), "growth")

    session.execute(delete(DiscoveryFeedEntry))
    counts: dict[str, int] = {}
    for (feed, period), (entries, basis) in results.items():
        session.add_all(
            DiscoveryFeedEntry(
                feed=feed,
                period=period or None,
                repository_id=e.repository_id,
                rank=e.rank,
                score=e.score,
                signals=e.signals,
                basis=e.basis,
                computed_at=now,
            )
            for e in entries
        )
        stmt = insert(DiscoveryFeedRun).values(
            id=uuid.uuid4(),
            feed=feed,
            period=period,
            basis=basis,
            entry_count=len(entries),
            computed_at=now,
        )
        session.execute(
            stmt.on_conflict_do_update(
                index_elements=["feed", "period"],
                set_={"basis": basis, "entry_count": len(entries), "computed_at": now},
            )
        )
        counts[f"{feed}:{period}" if period else feed] = len(entries)
    session.flush()
    return counts


# ---- Presentation -----------------------------------------------------------------------


def _ago(moment: datetime, now: datetime) -> str:
    days = max(0, (now - moment).days)
    if days == 0:
        return "today"
    if days == 1:
        return "yesterday"
    if days < 14:
        return f"{days} days ago"
    if days < 60:
        return f"{days // 7} weeks ago"
    return f"{days // 30} months ago"


def _period_phrase(days: int) -> str:
    return "in the last day" if days == 1 else f"in {days} days"


def describe_signals(
    signals: dict[str, Any], latest_release: RepositoryRelease | None, now: datetime
) -> list[str]:
    """Human-readable, factual descriptions of the numbers that placed an item."""
    text: list[str] = []
    gained, days = signals.get("stars_gained"), signals.get("period_days")
    if gained is not None and days:
        prefix = "≥" if signals.get("stars_gained_lower_bound") else "+"
        text.append(f"{prefix}{gained:,} stars {_period_phrase(days)}")
    g30 = signals.get("stars_gained_30d")
    if g30 is not None:
        prefix = "≥" if signals.get("stars_gained_30d_lower_bound") else "+"
        text.append(f"{prefix}{g30:,} stars in 30 days")
        if signals.get("accelerating"):
            text.append("Gaining stars faster this week than its 30-day average")
    reason = signals.get("reason")
    if reason == "created" and signals.get("age_days") is not None:
        text.append(f"Created {_ago(now - timedelta(days=signals['age_days']), now)}")
    elif reason == "discovered":
        text.append("Newly discovered")
    elif reason == "first_release":
        text.append("First release within the last month")
    if signals.get("category_star_threshold") is not None and signals.get("stars") is not None:
        text.append(f"{signals['stars']:,} stars: fewer than most projects in its category")
    weeks = signals.get("active_weeks_of_last_4")
    if weeks:
        text.append(f"Commits in {weeks} of the last 4 weeks")
    if latest_release and latest_release.published_at:
        if now - latest_release.published_at <= timedelta(days=30):
            text.append(f"{latest_release.tag} released {_ago(latest_release.published_at, now)}")
    return list(dict.fromkeys(text))


def _labels(session: Session, repo_ids: list[uuid.UUID]) -> dict[uuid.UUID, list[str]]:
    rows = session.execute(
        select(
            DiscoveryFeedEntry.repository_id,
            DiscoveryFeedEntry.feed,
            DiscoveryFeedEntry.period,
            DiscoveryFeedEntry.basis,
        ).where(DiscoveryFeedEntry.repository_id.in_(repo_ids))
    ).all()
    labels: dict[uuid.UUID, list[str]] = {}
    for repo_id, feed, period, basis in rows:
        if feed == "trending" and not (period == "week" and basis == "growth"):
            continue  # "Trending" only when it is measured growth, never popularity
        if feed in ("trending", "rising", "new", "hidden_gem"):
            current = labels.setdefault(repo_id, [])
            if feed not in current:
                current.append(feed)
    return labels


def _insight_lines(session: Session, repo_ids: list[uuid.UUID]) -> dict[uuid.UUID, tuple]:
    rows = session.execute(
        select(RepositoryInsight.repository_id, RepositoryInsight.report).where(
            RepositoryInsight.repository_id.in_(repo_ids)
        )
    ).all()
    lines: dict[uuid.UUID, tuple] = {}
    for repo_id, report in rows:
        one_line = ((report or {}).get("what_is_it") or {}).get("one_line")
        points = (report or {}).get("why_interesting") or []
        lines[repo_id] = (one_line, points[0].get("point") if points else None)
    return lines


def _latest_releases(session: Session, repo_ids: list[uuid.UUID]) -> dict[uuid.UUID, Any]:
    latest: dict[uuid.UUID, Any] = {}
    rows = session.scalars(
        select(RepositoryRelease)
        .where(RepositoryRelease.repository_id.in_(repo_ids))
        .order_by(RepositoryRelease.published_at.desc().nulls_last())
    )
    for release in rows:
        latest.setdefault(release.repository_id, release)
    return latest


def to_items(
    session: Session,
    rows: list[tuple[Repository, dict[str, Any]]],
    user_id: uuid.UUID,
    now: datetime,
) -> list[DiscoverItem]:
    ids = [repo.id for repo, _ in rows]
    saved = saved_ids(session, user_id, ids)
    labels = _labels(session, ids)
    lines = _insight_lines(session, ids)
    releases = _latest_releases(session, ids)
    items = []
    for repo, signals in rows:
        one_liner, why = lines.get(repo.id, (None, None))
        items.append(
            DiscoverItem(
                **to_card(repo, repo.id in saved).model_dump(),
                labels=labels.get(repo.id, []),
                signals=signals,
                signal_text=describe_signals(signals, releases.get(repo.id), now),
                one_liner=one_liner,
                why_explore=why,
            )
        )
    return items


def get_feed(
    session: Session,
    *,
    feed: str,
    period: str | None,
    filters: SearchFilters,
    page: int,
    page_size: int,
    user_id: uuid.UUID,
) -> FeedPage:
    stored = FEED_STORE.get(feed, feed)
    period_key = period if stored == "trending" else ""
    run = session.scalar(
        select(DiscoveryFeedRun).where(
            DiscoveryFeedRun.feed == stored, DiscoveryFeedRun.period == period_key
        )
    )
    base = (
        select(DiscoveryFeedEntry, Repository)
        .join(Repository, Repository.id == DiscoveryFeedEntry.repository_id)
        .where(DiscoveryFeedEntry.feed == stored)
    )
    base = base.where(
        DiscoveryFeedEntry.period == period_key
        if period_key
        else DiscoveryFeedEntry.period.is_(None)
    )
    base = apply_filters(base, filters)
    total = session.scalar(select(func.count()).select_from(base.subquery())) or 0
    rows = session.execute(
        base.order_by(DiscoveryFeedEntry.rank).offset((page - 1) * page_size).limit(page_size)
    ).all()
    now = datetime.now(UTC)
    items = to_items(session, [(repo, entry.signals) for entry, repo in rows], user_id, now)
    return FeedPage(
        items=items,
        page=page,
        page_size=page_size,
        total=total,
        feed=feed,
        period=period_key or None,
        basis=run.basis if run else "not_computed",
        computed_at=run.computed_at if run else None,
    )


def get_categories(
    session: Session, language: str | None, user_id: uuid.UUID
) -> list[CategorySummary]:
    filters = SearchFilters(language=language)
    counts = session.execute(
        apply_filters(select(Repository.category, func.count()), filters).group_by(
            Repository.category
        )
    ).all()
    summaries = []
    now = datetime.now(UTC)
    for category, count in sorted(counts, key=lambda c: category_label(c[0])):
        week = get_feed(
            session,
            feed="trending",
            period="week",
            filters=SearchFilters(category=category, language=language),
            page=1,
            page_size=3,
            user_id=user_id,
        )
        top = week.items
        if not top:
            repos = session.scalars(
                apply_filters(
                    select(Repository), SearchFilters(category=category, language=language)
                )
                .order_by(Repository.stars.desc().nulls_last())
                .limit(3)
            ).all()
            top = to_items(session, [(r, {}) for r in repos], user_id, now)
        summaries.append(
            CategorySummary(value=category, label=category_label(category), count=count, top=top)
        )
    return summaries
