from datetime import date

import httpx

from app.schemas.snapshot import CATEGORY_LABELS
from app.services.discovery_search import build_queries, load_search_config, select_candidates
from app.services.github_client import GitHubClient

CFG = load_search_config()
TODAY = date(2026, 11, 10)


def item(gid: int, **kw) -> dict:
    data = {
        "id": gid,
        "full_name": f"o/r{gid}",
        "fork": False,
        "archived": False,
        "description": "Useful tool",
        "license": {"spdx_id": "MIT"},
        "stargazers_count": 50,
    }
    data.update(kw)
    return data


def test_every_category_has_queries_with_qualifiers():
    queries = build_queries(CFG, TODAY)
    assert {category for category, _ in queries} == set(CATEGORY_LABELS)
    for _, q in queries:
        assert "created:>=2026-07-13" in q  # 120 days before TODAY
        assert f"stars:>={CFG.min_stars}" in q
        assert "fork:false" in q and "archived:false" in q


def test_candidate_filtering_rules():
    results = [
        (
            "backend",
            [
                item(1),
                item(2, fork=True),
                item(3, archived=True),
                item(4, license=None),
                item(5, description=""),
                item(6),  # known already
            ],
        ),
    ]
    chosen = select_candidates(results, known_github_ids={6}, cfg=CFG)
    assert [(c, r["id"]) for c, r in chosen] == [("backend", 1)]


def test_per_category_cap_and_cross_category_dedupe():
    many = [item(i) for i in range(1, 20)]
    results = [("backend", many), ("frontend", [item(1), item(100)])]
    chosen = select_candidates(results, known_github_ids=set(), cfg=CFG)
    backend = [r["id"] for c, r in chosen if c == "backend"]
    frontend = [r["id"] for c, r in chosen if c == "frontend"]
    assert len(backend) == CFG.per_category_limit
    assert frontend == [100]  # id 1 already taken by backend


def test_search_repositories_request():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = request.url
        return httpx.Response(200, json={"total_count": 1, "items": [item(9)]})

    client = GitHubClient("https://api.github.com", "t", transport=httpx.MockTransport(handler))
    assert client.search_repositories("topic:llm stars:>=20", per_page=30)[0]["id"] == 9
    assert seen["url"].path == "/search/repositories"
    assert seen["url"].params["q"] == "topic:llm stars:>=20"
    assert seen["url"].params["sort"] == "stars"


def test_profile_repos_and_star_outliers_are_skipped():
    results = [
        (
            "backend",
            [
                item(1, full_name="someone/someone"),
                item(2, stargazers_count=CFG.max_stars + 1),
                item(3, full_name="real/tool"),
            ],
        )
    ]
    chosen = select_candidates(results, known_github_ids=set(), cfg=CFG)
    assert [r["id"] for _, r in chosen] == [3]


def test_documentation_threshold():
    from app.services.discovery_search import documented_enough

    thin = "# Tool\n\nA tool."
    good = (
        "# Tool\n\n"
        + "Explains the tool. " * 100
        + "\n\n## Installation\n\npip install tool\n\n## Usage\n\n```python\nimport tool\n```\n"
    )
    assert documented_enough(thin, "https://github.com/o/r/blob/main/README.md", CFG) is False
    assert documented_enough(good, "https://github.com/o/r/blob/main/README.md", CFG) is True
