from pathlib import Path

import httpx
import pytest

from app.services.github_trending import (
    TrendingClient,
    TrendingParseError,
    infer_category,
    language_slug,
    parse_trending,
)

SAMPLE = (Path(__file__).parents[1] / "fixtures" / "trending" / "trending_sample.html").read_text(
    encoding="utf-8"
)


def test_parse_real_page_structure():
    repos = parse_trending(SAMPLE)
    assert [r.full_name for r in repos] == ["anthropics/skills", "meta/astryx", "acme/tiny"]
    first = repos[0]
    assert first.rank == 1
    assert first.description == "Public repository for Agent Skills"
    assert first.language == "Python"
    assert first.stars_today == 1038
    assert first.stars_total == 191_538 and first.forks_total == 22_483


def test_parse_missing_language_description_and_singular_star():
    tiny = parse_trending(SAMPLE)[2]
    assert tiny.language is None and tiny.description is None
    assert tiny.stars_today == 1


def test_layout_change_raises_instead_of_returning_nothing():
    with pytest.raises(TrendingParseError):
        parse_trending("<html><body><h1>Trending</h1><div>new layout</div></body></html>")


def test_empty_trending_list_is_allowed_when_page_says_so():
    page = (
        "<html><body><h3>It looks like we don’t have any trending repositories for x.</h3>"
        "</body></html>"
    )
    assert parse_trending(page) == []


def test_client_fetches_allowed_daily_urls_only():
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, text=SAMPLE)

    sleeps: list[float] = []
    client = TrendingClient(
        transport=httpx.MockTransport(handler), sleep=sleeps.append, delay_s=2.0
    )
    client.fetch(None)
    client.fetch("C++")
    assert [r.url.path for r in seen] == ["/trending", "/trending/c++"]
    assert all("since" not in str(r.url) for r in seen)  # robots.txt disallows ?since=
    assert seen[0].headers["user-agent"].startswith("devatlas-trending")
    assert sleeps == [2.0]  # polite delay between requests


@pytest.mark.parametrize(
    ("name", "slug"),
    [("Python", "python"), ("C++", "c++"), ("C#", "c#"), ("Jupyter Notebook", "jupyter-notebook")],
)
def test_language_slug(name, slug):
    assert language_slug(name) == slug


@pytest.mark.parametrize(
    ("topics", "language", "description", "category"),
    [
        (["llm", "agents"], "Python", "", "llm_agents"),
        (["mcp"], "TypeScript", "An MCP server", "mcp_automation"),
        ([], "Python", "Physics engine for robotics and reinforcement learning", "ai_ml"),
        (["osint"], "Python", "Hunt down social media accounts", "security"),
        (["react", "ui"], "TypeScript", "", "frontend"),
        ([], "Go", "A fast key-value database", "databases_search"),
        ([], "Rust", "", "developer_tools"),
    ],
)
def test_infer_category(topics, language, description, category):
    assert infer_category(topics, language, description) == category
