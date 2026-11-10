"""Discover feed ranking: pure, configurable, and transparent (docs/discover-ranking.md).

Every entry carries the exact signals that placed it. Unknown growth (`Growth.value is
None`) is never treated as zero: such repositories are left out of growth-based feeds.
"""

import math
import re
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel

from app.config import BACKEND_DIR
from app.services.activity_client import ReleaseInfo
from app.services.chunking import ReadmeFormat, clean_readme, split_sections
from app.services.history_service import Growth

Basis = Literal["growth", "popularity_activity"]
RANKING_PATH = BACKEND_DIR / "data" / "discover_ranking.yaml"
_UNKNOWN = Growth(None, False, None)


class TrendingConfig(BaseModel):
    periods: dict[str, int]
    min_stars_gained: dict[str, int]
    active_within_days: int
    limit: int


class RisingConfig(BaseModel):
    window_days: int
    size_floor: int
    min_active_weeks: int
    min_stars_gained: int
    acceleration_boost: float
    exclude_top_popular: int
    limit: int


class NewConfig(BaseModel):
    created_within_days: int
    discovered_within_days: int
    first_release_within_days: int
    limit: int


class HiddenGemsConfig(BaseModel):
    star_percentile_max: float
    min_category_size: int = 8
    pushed_within_days: int
    min_readme_completeness: float
    require_license: bool
    limit: int


class WeeklyConfig(BaseModel):
    per_feed: int
    total: int
    max_per_category: int


class RankingConfig(BaseModel):
    trending: TrendingConfig
    rising: RisingConfig
    new: NewConfig
    hidden_gems: HiddenGemsConfig
    weekly: WeeklyConfig


def load_ranking_config(path: Path = RANKING_PATH) -> RankingConfig:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    return RankingConfig(**{k: raw[k] for k in RankingConfig.model_fields})


@dataclass(frozen=True)
class RepoSignals:
    repository_id: uuid.UUID
    category: str
    discovery_source: str
    stars: int | None
    forks: int | None
    created_at: datetime | None
    first_indexed_at: datetime | None
    pushed_at: datetime | None
    has_license: bool
    readme_completeness: float
    stars_gained: dict[int, Growth]
    forks_gained: dict[int, Growth]
    commits: dict[int, Growth]
    active_weeks_of_last_4: int | None
    latest_release: ReleaseInfo | None
    first_release_at: datetime | None


@dataclass(frozen=True)
class FeedEntry:
    repository_id: uuid.UUID
    rank: int
    score: float
    signals: dict[str, Any]
    basis: Basis


def _days_since(moment: datetime | None, now: datetime) -> float | None:
    return None if moment is None else (now - moment).total_seconds() / 86400


def _gained(series: dict[int, Growth], days: int) -> Growth:
    return series.get(days, _UNKNOWN)


def _ranked(
    rows: list[tuple[RepoSignals, float, dict[str, Any]]], basis: Basis, limit: int
) -> list[FeedEntry]:
    return [
        FeedEntry(
            repository_id=s.repository_id,
            rank=i,
            score=round(score, 6),
            signals=signals,
            basis=basis,
        )
        for i, (s, score, signals) in enumerate(rows[:limit], start=1)
    ]


# ---- README completeness ------------------------------------------------------------------

_INSTALL = re.compile(r"install|getting started|setup|set up|quick ?start", re.I)
_USAGE = re.compile(r"usage|example|quick ?start|tutorial|how to use|getting started", re.I)
_FEATURES = re.compile(r"feature|highlight|capabilit|why|what", re.I)
_BULLET = re.compile(r"^\s{0,3}[-*+]\s+\S", re.M)


def readme_completeness(text: str | None, fmt: ReadmeFormat = "markdown") -> float:
    """0..1 documentation completeness: install 0.25, usage 0.25, feature list 0.2,
    length >= 1,500 chars 0.15, a code block 0.15."""
    if not text or not text.strip():
        return 0.0
    cleaned = clean_readme(text, fmt)
    sections = split_sections(cleaned, fmt)
    titles = [s.title or "" for s in sections]
    score = 0.0
    if any(_INSTALL.search(t) for t in titles):
        score += 0.25
    if any(_USAGE.search(t) for t in titles):
        score += 0.25
    if any(_FEATURES.search(s.title or "") and len(_BULLET.findall(s.text)) >= 3 for s in sections):
        score += 0.2
    if len(cleaned) >= 1500:
        score += 0.15
    if "```" in cleaned or "~~~" in cleaned or ".. code" in text or "::\n\n    " in text:
        score += 0.15
    return round(min(score, 1.0), 4)


# ---- Feeds ----------------------------------------------------------------------------------


def rank_trending(
    signals: list[RepoSignals], period: str, cfg: RankingConfig, now: datetime
) -> tuple[list[FeedEntry], Basis]:
    tc = cfg.trending
    if period != "all":
        days = tc.periods[period]
        with_growth = [s for s in signals if _gained(s.stars_gained, days).value is not None]
        if with_growth:
            rows = []
            for s in with_growth:
                stars = _gained(s.stars_gained, days)
                if (stars.value or 0) < tc.min_stars_gained[period]:
                    continue
                forks = _gained(s.forks_gained, days)
                commits = _gained(s.commits, days)
                rows.append(
                    (
                        s,
                        float(stars.value or 0),
                        {
                            "period_days": days,
                            "stars_gained": stars.value,
                            "stars_gained_lower_bound": stars.lower_bound,
                            "stars_basis": stars.basis,
                            "forks_gained": forks.value,
                            "commits": commits.value,
                            "active_weeks_of_last_4": s.active_weeks_of_last_4,
                        },
                    )
                )
            rows.sort(
                key=lambda r: (
                    -r[1],
                    -(r[2]["forks_gained"] or 0),
                    -(r[0].active_weeks_of_last_4 or 0),
                    str(r[0].repository_id),
                )
            )
            return _ranked(rows, "growth", tc.limit), "growth"

    # Popularity + recent activity (all time, or no growth history for the period).
    rows = []
    for s in signals:
        since_push = _days_since(s.pushed_at, now)
        recent = since_push is not None and since_push <= tc.active_within_days
        signal: dict[str, Any] = {"stars": s.stars, "recently_active": recent}
        if s.pushed_at:
            signal["pushed_at"] = s.pushed_at.isoformat()
        commits_30 = _gained(s.commits, 30).value
        if commits_30 is not None:
            signal["commits_30d"] = commits_30
        rows.append((s, float(s.stars or 0), signal))
    if period == "all":
        rows.sort(key=lambda r: (-(r[0].stars or -1), str(r[0].repository_id)))
    else:
        rows.sort(
            key=lambda r: (
                not r[2]["recently_active"],
                -(r[0].stars or -1),
                str(r[0].repository_id),
            )
        )
    return _ranked(rows, "popularity_activity", tc.limit), "popularity_activity"


def rank_rising(
    signals: list[RepoSignals], cfg: RankingConfig, now: datetime
) -> tuple[list[FeedEntry], Literal["growth", "insufficient_history"]]:
    rc = cfg.rising
    window = rc.window_days
    if not any(_gained(s.stars_gained, window).value is not None for s in signals):
        return [], "insufficient_history"
    by_stars = sorted(signals, key=lambda s: -(s.stars or 0))
    excluded = {s.repository_id for s in by_stars[: rc.exclude_top_popular]}
    rows = []
    for s in signals:
        g30 = _gained(s.stars_gained, window)
        if s.repository_id in excluded or g30.value is None or g30.value < rc.min_stars_gained:
            continue
        if (s.active_weeks_of_last_4 or 0) < rc.min_active_weeks:
            continue
        before = max((s.stars or 0) - g30.value, rc.size_floor)
        ratio = g30.value / before
        g7 = _gained(s.stars_gained, 7)
        accelerating = g7.value is not None and g7.value / 7 > g30.value / window
        score = ratio * (rc.acceleration_boost if accelerating else 1.0)
        rows.append(
            (
                s,
                score,
                {
                    "stars_gained_30d": g30.value,
                    "stars_gained_30d_lower_bound": g30.lower_bound,
                    "stars_gained_7d": g7.value,
                    "growth_ratio": round(ratio, 4),
                    "accelerating": accelerating,
                    "active_weeks_of_last_4": s.active_weeks_of_last_4,
                },
            )
        )
    rows.sort(key=lambda r: (-r[1], str(r[0].repository_id)))
    return _ranked(rows, "growth", rc.limit), "growth"


def rank_new(signals: list[RepoSignals], cfg: RankingConfig, now: datetime) -> list[FeedEntry]:
    nc = cfg.new
    rows = []
    for s in signals:
        age = _days_since(s.created_at, now)
        indexed = _days_since(s.first_indexed_at, now)
        first_release = _days_since(s.first_release_at, now)
        if age is not None and age <= nc.created_within_days:
            reason = "created"
        elif (
            s.discovery_source == "search"
            and indexed is not None
            and indexed <= nc.discovered_within_days
        ):
            reason = "discovered"
        elif first_release is not None and first_release <= nc.first_release_within_days:
            reason = "first_release"
        else:
            continue
        per_day = (s.stars or 0) / max(age or 7.0, 7.0)
        traction = min(1.0, math.log10(1 + per_day) / 2)
        rows.append(
            (
                s,
                traction + s.readme_completeness,
                {
                    "reason": reason,
                    "age_days": None if age is None else int(age),
                    "stars": s.stars,
                    "readme_completeness": s.readme_completeness,
                },
            )
        )
    rows.sort(key=lambda r: (-r[1], str(r[0].repository_id)))
    return _ranked(rows, "growth", nc.limit)


def _percentile(values: list[int], pct: float) -> float:
    ordered = sorted(values)
    if len(ordered) == 1:
        return float(ordered[0])
    position = pct / 100 * (len(ordered) - 1)
    low = math.floor(position)
    high = min(low + 1, len(ordered) - 1)
    return ordered[low] + (ordered[high] - ordered[low]) * (position - low)


def rank_hidden_gems(
    signals: list[RepoSignals], cfg: RankingConfig, now: datetime
) -> list[FeedEntry]:
    hc = cfg.hidden_gems
    by_category: dict[str, list[int]] = {}
    for s in signals:
        if s.stars is not None:
            by_category.setdefault(s.category, []).append(s.stars)
    all_stars = [stars for values in by_category.values() for stars in values]
    global_threshold = _percentile(all_stars, hc.star_percentile_max) if all_stars else 0.0
    thresholds: dict[str, tuple[float, str]] = {
        c: (_percentile(v, hc.star_percentile_max), "category")
        if len(v) >= hc.min_category_size
        else (global_threshold, "global")
        for c, v in by_category.items()
    }
    rows = []
    for s in signals:
        if s.stars is None:
            continue
        threshold, scope = thresholds[s.category]
        if s.stars >= threshold:
            continue
        since_push = _days_since(s.pushed_at, now)
        if since_push is None or since_push > hc.pushed_within_days:
            continue
        if hc.require_license and not s.has_license:
            continue
        if s.readme_completeness < hc.min_readme_completeness:
            continue
        recency = 1 - since_push / hc.pushed_within_days
        rows.append(
            (
                s,
                0.6 * s.readme_completeness + 0.4 * recency,
                {
                    "stars": s.stars,
                    "category_star_threshold": round(threshold),
                    "threshold_scope": scope,
                    "readme_completeness": s.readme_completeness,
                    "days_since_push": int(since_push),
                },
            )
        )
    rows.sort(key=lambda r: (-r[1], str(r[0].repository_id)))
    return _ranked(rows, "growth", hc.limit)


def rank_weekly(
    feeds: dict[str, list[FeedEntry]],
    signals_by_id: dict[Any, RepoSignals],
    cfg: RankingConfig,
) -> list[FeedEntry]:
    wc = cfg.weekly
    chosen: list[tuple[FeedEntry, str]] = []
    seen: set[uuid.UUID] = set()
    per_category: dict[str, int] = {}
    for feed in ("trending", "rising", "new", "hidden_gem"):
        taken = 0
        for entry in feeds.get(feed, []):
            if taken >= wc.per_feed or len(chosen) >= wc.total:
                break
            if entry.repository_id in seen:
                continue
            sig = signals_by_id.get(entry.repository_id)
            category = sig.category if sig else "unknown"
            if per_category.get(category, 0) >= wc.max_per_category:
                continue
            seen.add(entry.repository_id)
            per_category[category] = per_category.get(category, 0) + 1
            chosen.append((entry, feed))
            taken += 1
    return [
        FeedEntry(
            repository_id=e.repository_id,
            rank=i,
            score=e.score,
            signals={**e.signals, "from_feed": feed},
            basis=e.basis,
        )
        for i, (e, feed) in enumerate(chosen, start=1)
    ]
