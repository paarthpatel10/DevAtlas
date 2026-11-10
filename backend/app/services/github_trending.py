"""Track GitHub Trending (github.com/trending): GitHub's own "stars today" measurement.

Only the daily pages are fetched (`/trending`, `/trending/<language>`): github.com/robots.txt
disallows `?since=` URLs for automated clients, so weekly/monthly views are built from our own
stored daily observations instead. The page is untrusted HTML: we extract a few fields and
fail loudly (TrendingParseError) if the layout changes, rather than storing nothing silently.
"""

import html
import re
import ssl
import time
from collections.abc import Callable
from dataclasses import dataclass

import httpx
import truststore

USER_AGENT = "devatlas-trending/0.1 (+https://github.com/trending; daily, low volume)"

_ARTICLE = re.compile(r'<article class="Box-row">(.*?)</article>', re.S)
_NAME = re.compile(r'<h2[^>]*>\s*<a[^>]*href="/([^"/]+/[^"/]+)"', re.S)
_DESCRIPTION = re.compile(r'<p class="col-9[^"]*">(.*?)</p>', re.S)
_LANGUAGE = re.compile(r'itemprop="programmingLanguage">([^<]+)<')
_STARGAZERS = re.compile(r'href="/[^"]+/stargazers"[^>]*>\s*([\d,]+)', re.S)
_FORKS = re.compile(r'href="/[^"]+/forks"[^>]*>\s*([\d,]+)', re.S)
_STARS_TODAY = re.compile(r"([\d,]+)\s+stars?\s+today")
_EMPTY_PAGE = re.compile(r"don.t have any trending repositories", re.I)


class TrendingParseError(Exception):
    """The trending page no longer has the structure we parse."""


@dataclass(frozen=True)
class TrendingRepo:
    rank: int
    full_name: str
    description: str | None
    language: str | None
    stars_total: int | None
    forks_total: int | None
    stars_today: int


def _int(match: re.Match[str] | None) -> int | None:
    return int(match.group(1).replace(",", "")) if match else None


def _text(fragment: str) -> str:
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", fragment)).split())


def parse_trending(page: str) -> list[TrendingRepo]:
    articles = _ARTICLE.findall(page)
    if not articles:
        if _EMPTY_PAGE.search(page):
            return []
        raise TrendingParseError("No repository entries found; the page layout may have changed.")
    repos: list[TrendingRepo] = []
    for article in articles:
        name = _NAME.search(article)
        stars_today = _int(_STARS_TODAY.search(article))
        if name is None or stars_today is None:
            raise TrendingParseError("A trending entry is missing its name or 'stars today'.")
        description = _DESCRIPTION.search(article)
        language = _LANGUAGE.search(article)
        repos.append(
            TrendingRepo(
                rank=len(repos) + 1,
                full_name=html.unescape(name.group(1)).strip(),
                description=(_text(description.group(1)) or None) if description else None,
                language=html.unescape(language.group(1)).strip() if language else None,
                stars_total=_int(_STARGAZERS.search(article)),
                forks_total=_int(_FORKS.search(article)),
                stars_today=stars_today,
            )
        )
    return repos


def language_slug(language: str) -> str:
    return language.strip().lower().replace(" ", "-")


class TrendingClient:
    def __init__(
        self,
        *,
        base_url: str = "https://github.com",
        transport: httpx.BaseTransport | None = None,
        delay_s: float = 2.0,
        sleep: Callable[[float], None] = time.sleep,
        timeout: float = 30.0,
    ) -> None:
        self._client = httpx.Client(
            base_url=base_url,
            headers={"User-Agent": USER_AGENT, "Accept": "text/html"},
            timeout=timeout,
            follow_redirects=True,
            transport=transport,
            verify=truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT),
        )
        self._delay = delay_s
        self._sleep = sleep
        self._requests = 0

    def __enter__(self) -> "TrendingClient":
        return self

    def __exit__(self, *exc: object) -> None:
        self._client.close()

    def fetch(self, language: str | None) -> list[TrendingRepo]:
        """Daily trending, overall (None) or for one language. No `since` parameter."""
        if self._requests:
            self._sleep(self._delay)
        self._requests += 1
        path = "/trending" if language is None else f"/trending/{language_slug(language)}"
        response = self._client.get(path)
        response.raise_for_status()
        return parse_trending(response.text)


# ---- Category inference for repositories found on GitHub Trending ------------------------

_CATEGORY_RULES: list[tuple[str, tuple[str, ...]]] = [
    ("mcp_automation", ("mcp", "model context protocol", "model-context-protocol")),
    (
        "llm_agents",
        (
            "llm",
            "llms",
            "agent",
            "agents",
            "agentic",
            "gpt",
            "claude",
            "chatbot",
            "rag",
            "language model",
            "prompt",
            "copilot",
            "skills",
        ),
    ),
    (
        "ai_ml",
        (
            "machine learning",
            "machine-learning",
            "deep learning",
            "deep-learning",
            "neural",
            "pytorch",
            "tensorflow",
            "reinforcement learning",
            "computer vision",
            "robotics",
            "physics engine",
            "diffusion",
            "model training",
        ),
    ),
    (
        "security",
        (
            "security",
            "osint",
            "pentest",
            "vulnerability",
            "exploit",
            "malware",
            "authentication",
            "encryption",
            "privacy",
        ),
    ),
    (
        "databases_search",
        (
            "database",
            "sql",
            "postgres",
            "key-value",
            "vector database",
            "search engine",
            "full-text",
            "cache",
        ),
    ),
    (
        "data_engineering",
        (
            "data pipeline",
            "etl",
            "data engineering",
            "dataframe",
            "analytics",
            "stock",
            "spreadsheet",
        ),
    ),
    (
        "devops_platform",
        (
            "devops",
            "kubernetes",
            "docker",
            "terraform",
            "cloud",
            "deploy",
            "infrastructure",
            "monitoring",
            "observability",
            "self-hosted",
        ),
    ),
    (
        "frontend",
        (
            "frontend",
            "react",
            "vue",
            "svelte",
            "css",
            "ui",
            "component",
            "design system",
            "animation",
            "web components",
        ),
    ),
    ("full_stack", ("full-stack", "fullstack", "saas", "starter kit", "boilerplate")),
    ("backend", ("backend", "api", "server", "web framework", "microservice")),
    ("learning", ("tutorial", "course", "learn", "awesome", "interview", "roadmap", "book")),
]


def infer_category(topics: list[str], language: str | None, description: str | None) -> str:
    """Best-effort category from topics and description; developer tools by default."""
    text = " ".join([*(t.replace("-", " ") for t in topics), *topics, description or ""]).lower()
    for category, keywords in _CATEGORY_RULES:
        for keyword in keywords:
            if re.search(rf"(?<![a-z0-9]){re.escape(keyword)}(?![a-z0-9])", text):
                return category
    return "developer_tools"
