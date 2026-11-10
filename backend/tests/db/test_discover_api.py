from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import delete, select, update

from app.models import (
    DiscoveryFeedEntry,
    DiscoveryFeedRun,
    GitHubTrendingObservation,
    Repository,
    RepositoryDailyStat,
)
from app.services.activity_client import RepoActivity
from app.services.discover_ranking import load_ranking_config
from app.services.discover_service import compute_feeds
from app.services.history_service import record_activity

NOW = datetime.now(UTC)
TODAY = NOW.date()


def reset_history(session):
    session.execute(delete(RepositoryDailyStat))
    session.execute(delete(DiscoveryFeedEntry))
    session.execute(delete(DiscoveryFeedRun))
    session.execute(delete(GitHubTrendingObservation))
    session.execute(
        update(Repository).values(
            star_history_since=None, fork_history_since=None, commit_history_since=None
        )
    )
    session.commit()


def repo(session, full_name) -> Repository:
    return session.scalar(select(Repository).where(Repository.full_name == full_name))


def add_star_history(session, full_name, by_day: dict[date, int], capped=False):
    record_activity(
        session,
        repo(session, full_name),
        RepoActivity(
            stars_by_day=by_day,
            stars_capped=capped,
            forks_by_day={},
            forks_capped=False,
            commits_by_day={TODAY: 3},
            releases=[],
        ),
        TODAY - timedelta(days=35),
        TODAY,
    )
    session.commit()


@pytest.fixture
def history_free(seeded):
    reset_history(seeded)
    yield seeded
    reset_history(seeded)


def feed(api, name, **params):
    r = api.get(f"/api/v1/discover/{name}", params=params)
    assert r.status_code == 200, r.text
    return r.json()


def names(body) -> list[str]:
    return [i["full_name"] for i in body["items"]]


def test_not_computed_feed_is_empty_and_says_so(api, history_free):
    body = feed(api, "trending", period="week")
    assert body["items"] == [] and body["computed_at"] is None
    assert body["basis"] == "not_computed"


def test_trending_without_observations_or_history_never_lists_most_starred(api, history_free):
    compute_feeds(history_free, load_ranking_config(), NOW)
    history_free.commit()
    body = feed(api, "trending", period="day")
    assert body["basis"] == "insufficient_history"
    assert body["items"] == [] and "track_github_trending" in body["note"]
    assert api.get("/api/v1/discover/trending", params={"period": "all"}).status_code == 422


def add_trending(session, full_name, day, stars_today, scope="", rank=1):
    session.add(
        GitHubTrendingObservation(
            day=day,
            scope=scope,
            rank=rank,
            full_name=full_name,
            repository_id=repo(session, full_name).id,
            stars_today=stars_today,
            stars_total=None,
            forks_total=None,
            observed_at=NOW,
        )
    )
    session.commit()


def test_trending_from_github_trending_observations(api, history_free):
    add_trending(history_free, "acme/searchy", TODAY, 1038, rank=1)
    add_trending(history_free, "acme/ui", TODAY, 200, rank=2)
    compute_feeds(history_free, load_ranking_config(), NOW)
    history_free.commit()
    day = feed(api, "trending", period="day")
    assert day["basis"] == "github_trending"
    assert names(day) == ["acme/searchy", "acme/ui"]
    top = day["items"][0]
    assert "+1,038 stars today on GitHub Trending" in top["signal_text"]
    assert "trending" in top["labels"]
    week = feed(api, "trending", period="week")
    assert "1 day of GitHub Trending observations" in week["note"]
    assert (
        "On GitHub Trending 1 of 1 observed day (+1,038 stars reported)"
        in (week["items"][0]["signal_text"])
    )
    rising = feed(api, "rising")
    assert rising["basis"] == "insufficient_history" and "1 day so far" in rising["note"]


def test_trending_week_with_history_is_growth_based(api, history_free):
    add_star_history(history_free, "acme/jobs", {TODAY: 40, TODAY - timedelta(days=2): 60})
    add_star_history(history_free, "acme/searchy", {TODAY: 5})
    compute_feeds(history_free, load_ranking_config(), NOW)
    history_free.commit()
    body = feed(api, "trending", period="week")
    assert body["basis"] == "growth"
    assert names(body) == ["acme/jobs", "acme/searchy"]
    top = body["items"][0]
    assert "+100 stars in 7 days" in top["signal_text"]
    assert "trending" in top["labels"]
    assert top["signals"]["stars_gained"] == 100


def test_capped_growth_renders_as_lower_bound(api, history_free):
    add_star_history(history_free, "acme/jobs", {TODAY: 3000}, capped=True)
    compute_feeds(history_free, load_ranking_config(), NOW)
    history_free.commit()
    top = feed(api, "trending", period="month")["items"][0]
    assert "≥3,000 stars in 30 days" in top["signal_text"]


def test_filters_category_and_language(api, history_free):
    for name in ("acme/jobs", "acme/ui", "acme/searchy"):
        add_star_history(history_free, name, {TODAY: 10})
    compute_feeds(history_free, load_ranking_config(), NOW)
    history_free.commit()
    assert names(feed(api, "trending", period="week", category="frontend")) == ["acme/ui"]
    assert names(feed(api, "trending", period="week", language="rust")) == ["acme/searchy"]


def test_rising_without_history_reports_insufficient_history(api, history_free):
    compute_feeds(history_free, load_ranking_config(), NOW)
    history_free.commit()
    body = feed(api, "rising")
    assert body["items"] == [] and body["basis"] == "insufficient_history"
    assert body["computed_at"] is not None


def test_unknown_feed_and_bad_period_are_rejected(api, history_free):
    assert api.get("/api/v1/discover/popular").status_code == 422
    assert api.get("/api/v1/discover/trending", params={"period": "year"}).status_code == 422


def test_categories_with_counts_and_top_items(api, history_free):
    compute_feeds(history_free, load_ranking_config(), NOW)
    history_free.commit()
    r = api.get("/api/v1/discover/categories")
    assert r.status_code == 200
    by_value = {c["value"]: c for c in r.json()}
    assert by_value["backend"]["count"] == 2  # acme/jobs and acme/bare
    assert by_value["backend"]["label"] == "Backend Engineering"
    assert 1 <= len(by_value["backend"]["top"]) <= 3
