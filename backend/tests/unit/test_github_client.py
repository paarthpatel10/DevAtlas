import base64
from datetime import UTC, datetime

import httpx
import pytest

from app.services.github_client import (
    GitHubClient,
    GitHubError,
    GitHubNotFound,
    GitHubRateLimited,
    ReadmeResult,
)

NOW = datetime(2026, 11, 10, 12, 0, tzinfo=UTC)


def resp(status: int, json=None, headers=None) -> httpx.Response:
    return httpx.Response(status, json=json if json is not None else {}, headers=headers or {})


def make_client(responses: list[httpx.Response], token: str | None = None):
    queue = list(responses)
    requests: list[httpx.Request] = []
    sleeps: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        item = queue.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    client = GitHubClient(
        "https://api.github.com",
        token,
        transport=httpx.MockTransport(handler),
        sleep=sleeps.append,
        now=lambda: NOW,
    )
    client.requests = requests  # type: ignore[attr-defined]
    return client, sleeps


def test_retries_server_errors_with_backoff():
    client, sleeps = make_client([resp(502), resp(502), resp(200, json={"id": 1})])
    assert client.get_repository("o/n") == {"id": 1}
    assert sleeps == [1, 2]


def test_transport_errors_are_retried():
    client, sleeps = make_client([httpx.ConnectError("boom"), resp(200, json={"id": 2})])
    assert client.get_repository("o/n") == {"id": 2}
    assert sleeps == [1]


def test_gives_up_after_max_retries():
    client, sleeps = make_client([resp(503)] * 5)
    with pytest.raises(GitHubError):
        client.get_repository("o/n")
    assert sleeps == [1, 2, 4, 8]


def test_not_found_is_not_retried():
    client, sleeps = make_client([resp(404, json={"message": "Not Found"})])
    with pytest.raises(GitHubNotFound):
        client.get_repository("o/missing")
    assert sleeps == []


def test_rate_limit_far_in_future_raises_with_reset():
    reset = int(NOW.timestamp()) + 3600
    client, sleeps = make_client(
        [resp(403, headers={"x-ratelimit-remaining": "0", "x-ratelimit-reset": str(reset)})]
    )
    with pytest.raises(GitHubRateLimited) as e:
        client.get_repository("o/n")
    assert e.value.reset_at == datetime.fromtimestamp(reset, UTC)
    assert sleeps == []


def test_rate_limit_resetting_soon_waits_then_retries():
    reset = int(NOW.timestamp()) + 30
    client, sleeps = make_client(
        [
            resp(403, headers={"x-ratelimit-remaining": "0", "x-ratelimit-reset": str(reset)}),
            resp(200, json={"id": 3}),
        ]
    )
    assert client.get_repository("o/n") == {"id": 3}
    assert sleeps == [30]


def test_retry_after_is_honoured():
    client, sleeps = make_client([resp(429, headers={"retry-after": "2"}), resp(200, json={})])
    client.get_repository("o/n")
    assert sleeps == [2]


def test_other_client_errors_raise_with_message():
    client, _ = make_client([resp(422, json={"message": "Validation Failed"})])
    with pytest.raises(GitHubError, match="Validation Failed"):
        client.get_repository("o/n")


def test_readme_decoded():
    content = base64.b64encode("# Hi ✓".encode()).decode()
    client, _ = make_client(
        [
            resp(
                200,
                json={
                    "content": content,
                    "encoding": "base64",
                    "html_url": "https://github.com/o/n/blob/main/README.md",
                    "download_url": "https://raw.githubusercontent.com/o/n/main/README.md",
                },
            )
        ]
    )
    assert client.get_readme("o/n") == ReadmeResult(
        text="# Hi ✓",
        html_url="https://github.com/o/n/blob/main/README.md",
        download_url="https://raw.githubusercontent.com/o/n/main/README.md",
    )


def test_missing_readme_is_none():
    client, _ = make_client([resp(404, json={"message": "Not Found"})])
    assert client.get_readme("o/n") is None


def test_languages():
    client, _ = make_client([resp(200, json={"Python": 100, "Shell": 5})])
    assert client.get_languages("o/n") == {"Python": 100, "Shell": 5}


def test_token_sent_only_when_configured():
    with_token, _ = make_client([resp(200, json={})], token="abc")
    with_token.get_repository("o/n")
    assert with_token.requests[0].headers["authorization"] == "Bearer abc"
    without, _ = make_client([resp(200, json={})])
    without.get_repository("o/n")
    assert "authorization" not in without.requests[0].headers
    assert without.requests[0].headers["x-github-api-version"] == "2022-11-28"
