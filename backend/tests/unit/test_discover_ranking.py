import uuid
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from app.services.discover_ranking import (
    RepoSignals,
    load_ranking_config,
    rank_hidden_gems,
    rank_new,
    rank_rising,
    rank_trending,
    rank_weekly,
    readme_completeness,
)
from app.services.history_service import Growth

NOW = datetime(2026, 11, 10, 12, tzinfo=UTC)
CFG = load_ranking_config()
UNKNOWN = Growth(None, False, None)


def g(value, lower=False, basis="events"):
    return Growth(value, lower, basis)


def sig(n: int, **kw) -> RepoSignals:
    base = RepoSignals(
        repository_id=uuid.UUID(int=n),
        category="backend",
        discovery_source="curated",
        stars=1000,
        forks=100,
        created_at=NOW - timedelta(days=2000),
        first_indexed_at=NOW,
        pushed_at=NOW - timedelta(days=2),
        has_license=True,
        readme_completeness=0.8,
        stars_gained={1: UNKNOWN, 7: UNKNOWN, 30: UNKNOWN},
        forks_gained={1: UNKNOWN, 7: UNKNOWN, 30: UNKNOWN},
        commits={1: UNKNOWN, 7: UNKNOWN, 30: UNKNOWN},
        active_weeks_of_last_4=None,
        latest_release=None,
        first_release_at=None,
    )
    return replace(base, **kw)


def ids(entries) -> list[int]:
    return [e.repository_id.int for e in entries]


# ---- Trending -------------------------------------------------------------------------


def test_trending_without_any_history_is_popularity_activity():
    repos = [
        sig(1, stars=5000, pushed_at=NOW - timedelta(days=200)),
        sig(2, stars=100),
        sig(3, stars=900),
    ]
    entries, basis = rank_trending(repos, "week", CFG, NOW)
    assert basis == "popularity_activity"
    assert ids(entries) == [3, 2, 1]  # recently pushed first, then by stars
    assert all(e.basis == "popularity_activity" for e in entries)
    assert all("stars_gained" not in e.signals for e in entries)


def test_trending_growth_orders_by_stars_gained_with_tie_breakers():
    repos = [
        sig(1, stars_gained={7: g(50)}, forks_gained={7: g(1)}),
        sig(2, stars_gained={7: g(50)}, forks_gained={7: g(9)}),
        sig(3, stars_gained={7: g(400)}),
        sig(4, stars_gained={7: g(2)}),  # below min_stars_gained (3) for week
        sig(5),  # no coverage: excluded rather than treated as 0
    ]
    entries, basis = rank_trending(repos, "week", CFG, NOW)
    assert basis == "growth"
    assert ids(entries) == [3, 2, 1]
    assert entries[0].signals["stars_gained"] == 400
    assert entries[0].signals["period_days"] == 7


def test_trending_all_time_is_always_popularity():
    repos = [sig(1, stars=10, stars_gained={7: g(999)}), sig(2, stars=50_000)]
    entries, basis = rank_trending(repos, "all", CFG, NOW)
    assert basis == "popularity_activity" and ids(entries) == [2, 1]


def test_trending_lower_bound_is_carried_in_signals():
    entries, _ = rank_trending([sig(1, stars_gained={30: g(3000, lower=True)})], "month", CFG, NOW)
    assert entries[0].signals["stars_gained_lower_bound"] is True


# ---- Rising ---------------------------------------------------------------------------


def test_rising_needs_history():
    entries, basis = rank_rising([sig(1), sig(2)], CFG, NOW)
    assert (entries, basis) == ([], "insufficient_history")


def test_rising_relative_growth_activity_and_acceleration():
    big = sig(1, stars=200_000, stars_gained={7: g(3000), 30: g(9000)}, active_weeks_of_last_4=4)
    small_fast = sig(2, stars=600, stars_gained={7: g(60), 30: g(100)}, active_weeks_of_last_4=4)
    small_steady = sig(3, stars=600, stars_gained={7: g(10), 30: g(100)}, active_weeks_of_last_4=3)
    inactive = sig(4, stars=600, stars_gained={7: g(60), 30: g(100)}, active_weeks_of_last_4=1)
    too_few = sig(5, stars=600, stars_gained={7: g(5), 30: g(5)}, active_weeks_of_last_4=4)
    cfg = CFG.model_copy(
        update={"rising": CFG.rising.model_copy(update={"exclude_top_popular": 1})}
    )
    entries, basis = rank_rising([big, small_fast, small_steady, inactive, too_few], cfg, NOW)
    assert basis == "growth"
    assert ids(entries) == [2, 3]  # big excluded as top popular; inactive/too_few ineligible
    assert entries[0].signals["accelerating"] is True
    assert entries[1].signals["accelerating"] is False
    assert entries[0].score == pytest.approx(100 / 500 * CFG.rising.acceleration_boost)


# ---- New ------------------------------------------------------------------------------


def test_new_eligibility_rules():
    created = sig(1, created_at=NOW - timedelta(days=20), stars=300)
    discovered = sig(2, discovery_source="search", first_indexed_at=NOW - timedelta(days=3))
    curated_seeded_today = sig(3)  # indexed today but curated: not "newly discovered"
    first_release = sig(4, first_release_at=NOW - timedelta(days=10))
    old = sig(5, first_release_at=NOW - timedelta(days=400))
    entries = rank_new([created, discovered, curated_seeded_today, first_release, old], CFG, NOW)
    assert set(ids(entries)) == {1, 2, 4}
    reasons = {e.repository_id.int: e.signals["reason"] for e in entries}
    assert reasons == {1: "created", 2: "discovered", 4: "first_release"}


# ---- Hidden gems ----------------------------------------------------------------------


def test_hidden_gems_use_category_relative_star_percentile():
    # Categories large enough (>= min_category_size) for a within-category percentile.
    giants = [sig(i, category="frontend", stars=100_000 + i) for i in range(10, 20)]
    gem_among_giants = sig(1, category="frontend", stars=2_000)
    tiny = [sig(i, category="learning", stars=40 + i) for i in range(20, 30)]
    not_gem_among_tiny = sig(2, category="learning", stars=2_000)
    entries = rank_hidden_gems(giants + tiny + [gem_among_giants, not_gem_among_tiny], CFG, NOW)
    chosen = set(ids(entries))
    assert 1 in chosen and 2 not in chosen


def test_hidden_gems_require_license_activity_and_documentation():
    peers = [sig(i, stars=50_000) for i in range(10, 16)]
    ok = sig(1, stars=500)
    no_license = sig(2, stars=500, has_license=False)
    stale = sig(3, stars=500, pushed_at=NOW - timedelta(days=200))
    thin_docs = sig(4, stars=500, readme_completeness=0.3)
    entries = rank_hidden_gems(peers + [ok, no_license, stale, thin_docs], CFG, NOW)
    assert ids(entries) == [1]
    assert entries[0].signals["category_star_threshold"] > 500


# ---- Weekly ---------------------------------------------------------------------------


def test_weekly_caps_per_feed_and_category_and_dedupes():
    repos = {i: sig(i, category="backend" if i < 10 else "frontend") for i in range(1, 20)}
    trending, _ = rank_trending(
        [replace(repos[i], stars_gained={7: g(100 - i)}) for i in (1, 2, 3, 4, 11)],
        "week",
        CFG,
        NOW,
    )
    feeds = {"trending": trending, "rising": [], "new": [], "hidden_gem": trending[:2]}
    weekly = rank_weekly(feeds, repos, CFG)
    chosen = ids(weekly)
    assert len(chosen) == len(set(chosen))
    assert sum(1 for i in chosen if i < 10) <= CFG.weekly.max_per_category
    assert len(chosen) <= CFG.weekly.total


# ---- README completeness ---------------------------------------------------------------


def test_readme_completeness_scores():
    assert readme_completeness(None) == 0.0
    full = (
        "# Tool\n\n" + "Intro text. " * 150 + "\n\n## Installation\n\npip install tool\n\n"
        "## Usage\n\n```python\nimport tool\n```\n\n## Features\n\n- one\n- two\n- three\n"
    )
    assert readme_completeness(full) == pytest.approx(1.0)
    assert readme_completeness("# Tool\n\nShort.") == 0.0


def test_hidden_gems_small_categories_use_the_global_percentile():
    # A 4-repo category is too small for a meaningful within-category percentile.
    small = [
        sig(i, category="security", stars=s) for i, s in ((30, 30_000), (31, 25_000), (32, 20_000))
    ]
    famous_in_small = sig(33, category="security", stars=11_000)
    others = [sig(i, category="backend", stars=200 + i) for i in range(40, 52)]
    entries = rank_hidden_gems(small + [famous_in_small] + others, CFG, NOW)
    assert 33 not in ids(entries)  # 11k stars is not lesser-known across the index
    assert entries[0].signals["threshold_scope"] in {"category", "global"}
