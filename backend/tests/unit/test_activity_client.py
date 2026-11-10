import json
from datetime import UTC, date, datetime

import httpx
import pytest

from app.services.activity_client import fetch_activity
from app.services.github_client import GitHubClient, GitHubForbidden

SINCE = date(2026, 10, 6)


def page(kind: str, timestamps: list[str], has_next: bool, cursor: str = "c1") -> dict:
    field = "starredAt" if kind == "stargazers" else "createdAt"
    items = [{field: ts} for ts in timestamps]
    container = {"pageInfo": {"hasNextPage": has_next, "endCursor": cursor}}
    container["edges" if kind == "stargazers" else "nodes"] = items
    return {"data": {"repository": {kind: container}}}


class FakeGitHub:
    def __init__(self, routes: dict[str, list], commit_responses=None):
        self.routes = {k: list(v) for k, v in routes.items()}
        self.commit_responses = list(commit_responses or [])
        self.graphql_bodies: list[dict] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        if request.url.path == "/graphql":
            body = json.loads(request.content)
            self.graphql_bodies.append(body)
            for key in ("stargazers", "forks", "releases"):
                if f"{key}(" in body["query"]:
                    return httpx.Response(200, json=self.routes[key].pop(0))
        if request.url.path.endswith("/stats/commit_activity"):
            return self.commit_responses.pop(0)
        raise AssertionError(f"unexpected request {request.url}")


def client_for(fake: FakeGitHub) -> GitHubClient:
    return GitHubClient(
        "https://api.github.com",
        "t",
        transport=httpx.MockTransport(fake.handler),
        sleep=lambda s: None,
        now=lambda: datetime(2026, 11, 10, tzinfo=UTC),
    )


RELEASES = {
    "data": {
        "repository": {
            "releases": {
                "nodes": [
                    {
                        "tagName": "v2.0.0",
                        "name": "2.0",
                        "publishedAt": "2026-11-01T10:00:00Z",
                        "url": "https://github.com/o/n/releases/tag/v2.0.0",
                    }
                ]
            }
        }
    }
}
FORBIDDEN = {
    "data": {"repository": None},
    "errors": [
        {"type": "FORBIDDEN", "message": "Resource not accessible by personal access token"}
    ],
}
COMMITS_OK = httpx.Response(
    200,
    json=[
        {"week": int(datetime(2026, 9, 27, tzinfo=UTC).timestamp()), "days": [1] * 7, "total": 7},
        {
            "week": int(datetime(2026, 11, 8, tzinfo=UTC).timestamp()),
            "days": [0, 2, 3, 0, 0, 0, 0],
            "total": 5,
        },
    ],
)


def test_pagination_stops_at_since_and_buckets_by_utc_day():
    fake = FakeGitHub(
        {
            "stargazers": [
                page("stargazers", ["2026-11-09T23:30:00Z", "2026-11-09T01:00:00Z"], True),
                page("stargazers", ["2026-10-06T00:10:00Z", "2026-10-05T23:59:00Z"], True),
            ],
            "forks": [page("forks", ["2026-11-01T12:00:00Z"], False)],
            "releases": [RELEASES],
        },
        [COMMITS_OK],
    )
    activity = fetch_activity(client_for(fake), "o", "n", SINCE)
    assert activity.stars_by_day == {date(2026, 11, 9): 2, date(2026, 10, 6): 1}
    assert activity.stars_capped is False
    assert activity.forks_by_day == {date(2026, 11, 1): 1}
    assert activity.releases[0].tag == "v2.0.0"
    assert activity.releases[0].published_at == datetime(2026, 11, 1, 10, tzinfo=UTC)
    # commit weeks: the September week is before SINCE and dropped; Nov 9 = 2, Nov 10 = 3
    assert activity.commits_by_day == {date(2026, 11, 9): 2, date(2026, 11, 10): 3}
    assert len([b for b in fake.graphql_bodies if "stargazers(" in b["query"]]) == 2


def test_forbidden_stargazers_degrade_to_none_but_other_series_collected():
    fake = FakeGitHub(
        {
            "stargazers": [FORBIDDEN],
            "forks": [page("forks", [], False)],
            "releases": [RELEASES],
        },
        [COMMITS_OK],
    )
    activity = fetch_activity(client_for(fake), "o", "n", SINCE)
    assert activity.stars_by_day is None
    assert activity.forks_by_day == {}
    assert len(activity.releases) == 1


def test_page_cap_marks_series_capped():
    recent = ["2026-11-09T10:00:00Z"] * 3
    fake = FakeGitHub(
        {
            "stargazers": [page("stargazers", recent, True), page("stargazers", recent, True)],
            "forks": [page("forks", [], False)],
            "releases": [RELEASES],
        },
        [COMMITS_OK],
    )
    activity = fetch_activity(client_for(fake), "o", "n", SINCE, max_pages=2)
    assert activity.stars_by_day == {date(2026, 11, 9): 6}
    assert activity.stars_capped is True


def test_commit_stats_retry_on_202_then_give_up():
    pending = httpx.Response(202, json={})
    ok_fake = FakeGitHub({}, [pending, pending, COMMITS_OK])
    assert client_for(ok_fake).get_commit_activity("o/n") is not None
    give_up = FakeGitHub({}, [pending] * 4)
    assert client_for(give_up).get_commit_activity("o/n") is None


def test_graphql_forbidden_raises_typed_error():
    fake = FakeGitHub({"stargazers": [FORBIDDEN]})
    with pytest.raises(GitHubForbidden):
        client_for(fake).graphql("query { stargazers( }", {})
