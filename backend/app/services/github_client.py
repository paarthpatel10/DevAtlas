"""GitHub REST API client for public repository metadata.

Handles timeouts, retries with exponential backoff, primary/secondary rate limits, and
renamed repositories (redirects). It is only used by offline jobs, never in request paths.
"""

import base64
import logging
import ssl
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import httpx
import truststore

logger = logging.getLogger(__name__)


class GitHubError(Exception):
    pass


class GitHubNotFound(GitHubError):
    pass


class GitHubForbidden(GitHubError):
    """The token may not read this resource (e.g. stargazers with a fine-grained token)."""


class GitHubRateLimited(GitHubError):
    def __init__(self, message: str, reset_at: datetime | None = None) -> None:
        super().__init__(message)
        self.reset_at = reset_at


@dataclass(frozen=True)
class ReadmeResult:
    text: str
    html_url: str
    download_url: str | None


class GitHubClient:
    def __init__(
        self,
        base_url: str,
        token: str | None,
        *,
        transport: httpx.BaseTransport | None = None,
        timeout: float = 15.0,
        max_retries: int = 4,
        max_wait_seconds: float = 60.0,
        sleep: Callable[[float], None] = time.sleep,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "devatlas-ingest",
        }
        if token:
            headers["Authorization"] = f"Bearer {token}"
        self._client = httpx.Client(
            base_url=base_url,
            headers=headers,
            timeout=timeout,
            follow_redirects=True,
            transport=transport,
            # Verify TLS against the OS trust store (works behind TLS-inspecting proxies).
            verify=truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT),
        )
        self._max_retries = max_retries
        self._max_wait = max_wait_seconds
        self._sleep = sleep
        self._now = now

    def __enter__(self) -> "GitHubClient":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def close(self) -> None:
        self._client.close()

    # Public API -------------------------------------------------------------------------

    def get_repository(self, full_name: str) -> dict[str, Any]:
        return self._request(f"/repos/{full_name}").json()

    def get_readme(self, full_name: str) -> ReadmeResult | None:
        try:
            data = self._request(f"/repos/{full_name}/readme").json()
        except GitHubNotFound:
            return None
        raw = base64.b64decode(data.get("content") or "")
        return ReadmeResult(
            text=raw.decode("utf-8", errors="replace"),
            html_url=data["html_url"],
            download_url=data.get("download_url"),
        )

    def get_languages(self, full_name: str) -> dict[str, int]:
        return self._request(f"/repos/{full_name}/languages").json()

    def graphql(self, query: str, variables: dict[str, Any]) -> dict[str, Any]:
        payload = self._request(
            "/graphql", method="POST", json={"query": query, "variables": variables}
        ).json()
        errors = payload.get("errors") or []
        if any(e.get("type") == "FORBIDDEN" for e in errors):
            raise GitHubForbidden(errors[0].get("message", "forbidden"))
        if errors:
            raise GitHubError("; ".join(str(e.get("message")) for e in errors)[:300])
        return payload["data"]

    def get_commit_activity(
        self, full_name: str, attempts: int = 3, wait_s: float = 2.0
    ) -> list[dict[str, Any]] | None:
        """Weekly commit counts (with per-day breakdown) for the last year.

        GitHub computes these statistics lazily and answers 202 while it does; after
        `attempts` retries we give up and return None (no data, not zero commits).
        """
        for attempt in range(attempts + 1):
            response = self._request(f"/repos/{full_name}/stats/commit_activity")
            if response.status_code == 200:
                return response.json() or []
            if response.status_code == 204:
                return []
            if attempt < attempts:
                self._sleep(wait_s)
        return None

    # Internals --------------------------------------------------------------------------

    def _request(
        self, path: str, method: str = "GET", json: dict[str, Any] | None = None
    ) -> httpx.Response:
        attempt = 0
        while True:
            try:
                response = self._client.request(method, path, json=json)
            except httpx.TransportError as exc:
                self._backoff_or_raise(attempt, f"transport error: {exc}")
                attempt += 1
                continue

            status = response.status_code
            if status < 400:
                return response
            if status in (404, 451):
                raise GitHubNotFound(f"{path}: {status}")
            if status in (403, 429):
                wait = self._rate_limit_wait(response)
                if wait is not None:
                    self._sleep(wait)
                    continue
            if status >= 500:
                self._backoff_or_raise(attempt, f"server error {status}")
                attempt += 1
                continue
            raise GitHubError(f"{path}: {status} {self._message(response)}")

    def _backoff_or_raise(self, attempt: int, reason: str) -> None:
        if attempt >= self._max_retries:
            raise GitHubError(f"giving up after {attempt} retries: {reason}")
        delay = 2**attempt
        logger.warning("GitHub request failed (%s); retrying in %ss", reason, delay)
        self._sleep(delay)

    def _rate_limit_wait(self, response: httpx.Response) -> float | None:
        """Seconds to wait before retrying, or raise GitHubRateLimited. None = not a limit."""
        retry_after = response.headers.get("retry-after")
        if retry_after is not None and retry_after.isdigit():
            seconds = float(retry_after)
            if seconds <= self._max_wait:
                return seconds
            raise GitHubRateLimited(f"secondary rate limit; retry after {seconds}s")

        if response.headers.get("x-ratelimit-remaining") == "0":
            reset_header = response.headers.get("x-ratelimit-reset", "")
            reset_at = (
                datetime.fromtimestamp(int(reset_header), UTC) if reset_header.isdigit() else None
            )
            if reset_at is not None:
                seconds = max(0.0, (reset_at - self._now()).total_seconds())
                if seconds <= self._max_wait:
                    return seconds
            raise GitHubRateLimited("GitHub API rate limit exhausted", reset_at=reset_at)
        return None

    @staticmethod
    def _message(response: httpx.Response) -> str:
        try:
            return str(response.json().get("message", ""))
        except ValueError:
            return response.text[:200]
