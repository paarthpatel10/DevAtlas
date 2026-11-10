# M1 — Foundation + End-to-End Discovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A developer types "I need X for a project using Y" and gets a short, relevant, evidence-backed list of real open-source repositories, can open each one, browse/filter on Explore, and save results, all in demo mode with no AI or GitHub credentials.

**Architecture:** A modular-monolith FastAPI backend on hosted Postgres + pgvector (Neon), with a Next.js 16 frontend. The data comes from a committed snapshot of real GitHub API responses. A deterministic mock AI layer (hashed embeddings, vocabulary-based query understanding, extractive analysis) feeds hybrid retrieval (Postgres FTS + pgvector) fused with RRF, then evidence-based reranking and explanations.

**Tech Stack:** Python ≥3.12, uv, FastAPI, Pydantic v2, pydantic-settings, SQLAlchemy 2 (sync), psycopg 3, Alembic, pgvector, httpx, PyYAML, pytest, ruff · Next.js 16 (App Router), React 19, TypeScript, Tailwind v4, shadcn/ui, lucide-react, Vitest, Testing Library.

**Spec:** `open_source_intelligence_v0_spec.md`. Decisions, deviations, and the folder map are in `docs/superpowers/plans/2026-11-10-v0-roadmap.md`, so read §3 and §7 there first.

## Global Constraints

- Do not fabricate metrics: if a value is unavailable, show "Not available" or omit it (spec §5.2, §15).
- No "match percentage" or calibrated-sounding scores in the UI. Show signals (keyword rank, semantic rank, RRF score) instead (spec §6.5).
- Do not present generated analysis as official repository documentation. Label demo/extractive analysis (spec §5.4).
- Treat all ingested repository content as untrusted: render as plain text only, and never follow instructions in it (spec §1.1.9, §11.2).
- No secrets in frontend code. Configuration comes from env vars, documented in `.env.example` (spec §1.1.8).
- Dedupe repositories by GitHub repository ID, not name (spec §6.1).
- Seed and ingestion are idempotent (spec §15, §20).
- RRF: `RRF(d) = Σ 1/(k + rank_r(d))`, `k` configurable, default 60. Not a probability (spec §6.3).
- Every visible control works. No dead links: only Explore, Ask AI and Saved appear in nav in M1 (spec §10.2).
- Consistent error schema `{"error": {"code": str, "message": str, "details": any|null}}`, no stack traces in responses (spec §9).
- Python file I/O always uses `encoding="utf-8"`. Generated files use `\n` newlines.
- Commands are shown for PowerShell from the named directory. Backend commands run via `uv run`.

## Review Focus

1. **Query with no recognized vocabulary or no matches** (e.g. "something to make my thing nicer", "qwzxv"): expect results from hybrid retrieval or a clean empty state with guidance, never a 500. → tests in Task 10.
2. **Search text containing tsquery syntax** (`c++`, `"`, `&|!:*()`, `'`): expect no SQL/tsquery error, and results or an empty page. → tests in Task 8 and Task 9.
3. **Repository with missing data** (no README, null description, no license, null stars): expect ingest to succeed, the API to return nulls, and the UI to show "Not available" / "License not detected". → tests in Task 7 and Task 13.
4. **Owner/name casing and renames** (`/repositories/FastAPI/FASTAPI`, same `github_id` with a new name): expect resolution to one record, no duplicate, and an unknown repo to return 404 with the error schema. → tests in Task 7 and Task 9.
5. **Database unreachable** (bad URL or a Neon outage): expect `/health` to report `"database": "unavailable"` with HTTP 200, data endpoints to return 503 `database_unavailable`, and the frontend to show an error state with a Retry action. → tests in Task 2 and Task 12.

---

## Prerequisites (human, once)

1. Create a free Neon project (https://neon.tech). Create a second branch named `test`. Copy both connection strings, and change the scheme to `postgresql+psycopg://` (keep `?sslmode=require`).
2. Optional but recommended: create a GitHub token with public read access (a fine-grained token with no extra permissions is enough).
3. Put the values in `backend/.env` (created in Task 1 from `.env.example`): `DATABASE_URL`, `TEST_DATABASE_URL`, `GITHUB_TOKEN`.

---

### Task 1: Backend scaffold, config, errors, logging, health (no DB yet)

**Files:**
- Create: `.gitignore`, `backend/pyproject.toml`, `backend/.env.example`, `backend/app/__init__.py`, `backend/app/main.py`, `backend/app/config.py`, `backend/app/core/{__init__,logging,errors,middleware}.py`, `backend/app/api/__init__.py`, `backend/app/api/v1/{__init__,router,health}.py`
- Test: `backend/tests/__init__.py`, `backend/tests/conftest.py`, `backend/tests/unit/test_health.py`, `backend/tests/unit/test_errors.py`

**Interfaces:**
- Produces:
  - `Settings` (pydantic-settings, reads `backend/.env`): `app_env: Literal["development","test","production"]="development"`, `app_name="Open Source Intelligence Platform"`, `api_v1_prefix="/api/v1"`, `database_url: str | None = None`, `test_database_url: str | None = None`, `github_token: SecretStr | None = None`, `github_api_base_url="https://api.github.com"`, `ai_provider: Literal["mock","bedrock"]="mock"`, `embedding_dim: int = 1024`, `rrf_k: int = 60`, `cors_origins: list[str] = ["http://localhost:3000"]`, `log_level="INFO"`, `max_request_bytes: int = 65536`. `get_settings() -> Settings` (lru_cached).
  - `create_app(settings: Settings | None = None) -> FastAPI` in `app/main.py`. Module-level `app = create_app()`.
  - `AppError(Exception)` with `code: str`, `message: str`, `status_code: int`, `details: Any = None`. Subclasses `NotFoundError` (404, `"not_found"`) and `DatabaseUnavailableError` (503, `"database_unavailable"`). `register_error_handlers(app)` handles `AppError`, `RequestValidationError` (422, `"validation_error"`, details = pydantic errors), `StarletteHTTPException` (code `"http_error"`), and bare `Exception` (500, `"internal_error"`, message `"An unexpected error occurred."`).
  - `configure_logging(level: str, json_output: bool) -> None`. JSON lines contain `ts, level, logger, message, request_id` when present.
  - Middleware: `RequestContextMiddleware` (sets `X-Request-ID`, logs method/path/status/duration_ms, never bodies) and `BodySizeLimitMiddleware` (Content-Length > `max_request_bytes` → 413 `"payload_too_large"`).
  - `GET /api/v1/health` → `HealthOut{status: Literal["ok","degraded"], app_env, ai_provider, demo_mode: bool, database: Literal["ok","unavailable","not_configured"]}`. In this task `database` is always `"not_configured"` and `status` is `"ok"`. Task 2 wires the real check.

- [ ] **Step 1: Create the uv project.** In `backend/`: `uv init --app --name devatlas-backend --python ">=3.12"`, delete the generated `main.py`/`hello.py`, then `uv add fastapi "uvicorn[standard]" pydantic-settings "sqlalchemy>=2" "psycopg[binary]>=3.2" alembic pgvector httpx pyyaml` and `uv add --dev pytest ruff`. Configure pytest in `pyproject.toml`: `testpaths=["tests"]`, `markers=["db: needs TEST_DATABASE_URL", "benchmark: relevance benchmark"]`. Configure ruff: `line-length=100`, `select=["E","F","I","B","UP"]`.

- [ ] **Step 2: Write `.gitignore`** (root) covering `.env`, `.venv/`, `__pycache__/`, `.pytest_cache/`, `.ruff_cache/`, `node_modules/`, `.next/`, `*.log`. Write `backend/.env.example` with every `Settings` field (blank secrets, `AI_PROVIDER=mock`) plus commented Bedrock vars from spec §14 marked "M3".

- [ ] **Step 3: Write failing tests.**

```python
# tests/unit/test_health.py
def test_health_reports_demo_mode_without_database(client):
    r = client.get("/api/v1/health")
    assert r.status_code == 200
    body = r.json()
    assert body == {"status": "ok", "app_env": "test", "ai_provider": "mock",
                    "demo_mode": True, "database": "not_configured"}
    assert "x-request-id" in r.headers

# tests/unit/test_errors.py
def test_unknown_route_uses_error_schema(client):
    r = client.get("/api/v1/does-not-exist")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "http_error"

def test_unhandled_exception_hides_internals(client_with_boom_route):
    r = client_with_boom_route.get("/boom")   # route raises RuntimeError("secret detail")
    assert r.status_code == 500
    assert r.json() == {"error": {"code": "internal_error",
                                  "message": "An unexpected error occurred.", "details": None}}

def test_oversized_body_rejected(client):
    r = client.post("/api/v1/health", content=b"x" * 70000,
                    headers={"content-type": "application/json"})
    assert r.status_code == 413
    assert r.json()["error"]["code"] == "payload_too_large"
```

`tests/conftest.py` fixtures: `settings` (`Settings(app_env="test", database_url=None, _env_file=None)`), `client` (`TestClient(create_app(settings))`), `client_with_boom_route` (the app with an extra route that raises, built with `TestClient(app, raise_server_exceptions=False)`).

- [ ] **Step 4: Run** `uv run pytest tests/unit -q`. Expected: FAIL (`ModuleNotFoundError: app.main`).
- [ ] **Step 5: Implement** the interfaces above. `create_app` adds CORS from `settings.cors_origins`, both middlewares, error handlers, and the v1 router at `settings.api_v1_prefix`. OpenAPI docs are enabled only when `app_env != "production"`.
- [ ] **Step 6: Run** `uv run pytest tests/unit -q` → all PASS. Run `uv run ruff check .` → clean. Run `uv run uvicorn app.main:app --reload` and confirm `http://localhost:8000/api/v1/health` responds.
- [ ] **Step 7: Commit** `feat(backend): scaffold FastAPI app with config, error schema, logging, health`.

---

### Task 2: Database layer, models, initial migration, DB health

**Files:**
- Create: `backend/app/db/{__init__,base,session}.py`, `backend/alembic.ini`, `backend/app/db/migrations/{env.py,script.py.mako}`, `backend/app/db/migrations/versions/0001_initial.py`, `backend/app/models/{__init__,user,repository,saved}.py`, `docker-compose.yml`
- Modify: `backend/app/api/v1/health.py`, `backend/app/main.py`
- Test: `backend/tests/db/__init__.py`, `backend/tests/db/conftest.py`, `backend/tests/db/test_migrations.py`, `backend/tests/unit/test_health_db.py`

**Interfaces:**
- Consumes: `Settings`, `DatabaseUnavailableError` (Task 1).
- Produces:
  - `Base` (DeclarativeBase) with a `TimestampMixin` (`created_at`, `updated_at`, timezone-aware, server defaults `now()`).
  - `get_engine(url: str) -> Engine` (`pool_pre_ping=True`, `connect_args={"connect_timeout": 5}`), `SessionFactory`, and the FastAPI dependency `get_db() -> Iterator[Session]`. It raises `DatabaseUnavailableError` when `database_url` is None or on `OperationalError` at connect time.
  - `check_database(engine) -> Literal["ok","unavailable"]` (runs `SELECT 1`).
  - Models (UUID PKs `default=uuid4`; all FKs `ondelete="CASCADE"`):
    - `User`: `id, email (unique), display_name, created_at, updated_at`.
    - `Repository`: columns from spec §8.2, plus `license_name: str|None`, `readme_truncated: bool=False`, `category: str` (curated), `featured: bool=False`, `data_source: str` (`"seed_snapshot"|"github_live"`), `source_fetched_at: datetime`, `search_vector: TSVECTOR|None`. `github_id` BigInteger unique. Unique index on `lower(full_name)`. GIN index on `search_vector`. Indexes on `category`, `primary_language`, `license_spdx`. `languages` JSONB default `{}`; `topics` JSONB default `[]`.
    - `RepositoryAnalysis`: spec §8.3 fields + `supported_languages` JSONB, `prompt_version: str`. `repository_id` unique (one current analysis). JSON fields default `[]`.
    - `RepositoryChunk`: spec §8.4 + `position: int`. Unique `(repository_id, position)`.
    - `RepositoryEmbedding`: spec §8.5 + `kind: str` (`"summary"|"chunk"`), `embedding = mapped_column(VECTOR(1024))`. HNSW index `ix_repository_embeddings_embedding_hnsw` with `postgresql_ops={"embedding": "vector_cosine_ops"}`.
    - `RepositorySnapshot`: spec §8.6. Unique `(repository_id, snapshot_at)`.
    - `SavedRepository`: spec §8.11. Unique `(user_id, repository_id)`.
  - Migration `0001_initial` creates `CREATE EXTENSION IF NOT EXISTS vector` and then all tables/indexes above. Its downgrade drops the tables (not the extension). `env.py` uses `config.get_main_option("sqlalchemy.url")` if set, else `get_settings().database_url`.
  - Health now reports `database` as `"ok"`, `"unavailable"`, or `"not_configured"`, with `status="degraded"` unless `"ok"`.
  - `docker-compose.yml`: a single `db` service on `pgvector/pgvector:pg17`, port 5432, env `POSTGRES_DB=opensource_intel`, `POSTGRES_PASSWORD=postgres`, and a named volume. A header comment says "Optional; not used on the primary dev machine (see roadmap D1)".

- [ ] **Step 1: Write failing tests.**

```python
# tests/unit/test_health_db.py
def test_health_degraded_when_database_unreachable():
    s = Settings(app_env="test", _env_file=None,
                 database_url="postgresql+psycopg://u:p@127.0.0.1:1/nope")
    r = TestClient(create_app(s)).get("/api/v1/health")
    assert r.status_code == 200
    assert r.json()["database"] == "unavailable" and r.json()["status"] == "degraded"

# tests/db/test_migrations.py   (pytestmark = pytest.mark.db)
def test_migrations_create_schema_from_clean_database(db_engine):
    tables = set(inspect(db_engine).get_table_names())
    assert {"users", "repositories", "repository_analyses", "repository_chunks",
            "repository_embeddings", "repository_snapshots", "saved_repositories"} <= tables

def test_github_id_is_unique(db_session):
    db_session.add_all([make_repo(github_id=1, full_name="a/x"),
                        make_repo(github_id=1, full_name="a/y")])
    with pytest.raises(IntegrityError):
        db_session.flush()

def test_full_name_unique_case_insensitive(db_session):
    db_session.add_all([make_repo(github_id=1, full_name="Org/Repo"),
                        make_repo(github_id=2, full_name="org/repo")])
    with pytest.raises(IntegrityError):
        db_session.flush()
```

`tests/db/conftest.py`: skip the whole package (`pytest.skip(allow_module_level=True)` in a `pytest_collection_modifyitems` hook, or a fixture `skipif`) when `Settings().test_database_url` is unset. `db_engine` (session scope) runs Alembic `downgrade base` then `upgrade head` against `TEST_DATABASE_URL`. `db_session` (function scope) runs `TRUNCATE users, repositories RESTART IDENTITY CASCADE` and then yields a session that is rolled back and closed afterwards. Helper `make_repo(**overrides) -> Repository` lives in `tests/factories.py` with minimal valid defaults (`category="backend"`, `data_source="seed_snapshot"`, `source_fetched_at=datetime(2026,11,10,tzinfo=UTC)`, etc.).

- [ ] **Step 2: Run** `uv run pytest -q`. Expected: `test_health_db` FAILS. DB tests FAIL (or SKIP if `TEST_DATABASE_URL` is unset; set it now per Prerequisites).
- [ ] **Step 3: Implement** the models, session, migration (hand-written; import `pgvector.sqlalchemy.VECTOR` and `sqlalchemy.dialects.postgresql.TSVECTOR, JSONB, UUID`), and the health check.
- [ ] **Step 4: Run** `uv run pytest -q` → all PASS. Then `uv run alembic upgrade head` against the dev `DATABASE_URL` → succeeds. `GET /api/v1/health` shows `"database": "ok"`.
- [ ] **Step 5: Commit** `feat(backend): add Postgres/pgvector models, initial migration, DB health`.

---

### Task 3: AI provider interfaces and deterministic mock providers

**Files:**
- Create: `backend/app/ai/{__init__,provider,mock_providers}.py`
- Test: `backend/tests/unit/test_mock_providers.py`

**Interfaces:**
- Produces:
  - `class EmbeddingProvider(Protocol)`: `model_name: str`, `dimension: int`, `embed_texts(texts: Sequence[str]) -> list[list[float]]`.
  - `class LLMProvider(Protocol)`: `model_name: str`, `generate_text(system: str, prompt: str) -> str`, `generate_structured(system: str, prompt: str, schema: type[BaseModel]) -> BaseModel`. M1 does not call it. It exists so M3 plugs in without changing callers.
  - `HashingEmbeddingProvider(dimension: int = 1024)`, `model_name = "mock-hashing-v1"`. Tokenize with lowercase `[a-z0-9]+(?:[+#.][a-z0-9+#]*)?` (keeps `c++`, `c#`, `next.js`). Drop a small English stopword set. Features are unigrams (weight 1.0) and adjacent bigrams (weight 0.5). The index is `int.from_bytes(blake2b(feature, digest_size=8).digest()) % dimension`, and the sign comes from bit 0 of a second blake2b with `person=b"sign"`. The result is L2-normalized. Text with no tokens gives an all-zeros vector.
  - `MockLLMProvider`: `generate_*` raise `NotImplementedError("Mock LLM is not used for generation in demo mode")`.
  - `Providers` dataclass (`llm: LLMProvider`, `embeddings: EmbeddingProvider`) and `get_providers(settings: Settings) -> Providers`. For `"bedrock"` it raises `AppError(code="provider_not_available", status_code=500, message="Bedrock provider arrives in milestone M3; set AI_PROVIDER=mock")`.

- [ ] **Step 1: Write failing tests.**

```python
def test_embeddings_are_deterministic_normalized_and_sized():
    p = HashingEmbeddingProvider(dimension=1024)
    a1, a2 = p.embed_texts(["Distributed task queue with retries"] * 2)
    assert a1 == a2 and len(a1) == 1024
    assert math.isclose(sum(x * x for x in a1), 1.0, rel_tol=1e-9)

def test_related_text_is_closer_than_unrelated():
    p = HashingEmbeddingProvider()
    q, near, far = p.embed_texts(["background task queue with retries",
                                  "a task queue for background jobs, supports retries",
                                  "css utility classes for styling buttons"])
    assert dot(q, near) > dot(q, far)

def test_empty_text_gives_zero_vector():
    assert set(HashingEmbeddingProvider().embed_texts(["  !!  "])[0]) == {0.0}

def test_tokenizer_keeps_cpp_and_nextjs():
    assert {"c++", "next.js"} <= set(tokenize("C++ and Next.js"))

def test_bedrock_not_available_in_m1():
    with pytest.raises(AppError) as e:
        get_providers(Settings(ai_provider="bedrock", _env_file=None))
    assert e.value.code == "provider_not_available"
```

- [ ] **Step 2: Run** `uv run pytest tests/unit/test_mock_providers.py -q` → FAIL (import error).
- [ ] **Step 3: Implement** the interfaces above. Expose `tokenize(text: str) -> list[str]` from `mock_providers.py`.
- [ ] **Step 4: Run** the same command → PASS.
- [ ] **Step 5: Commit** `feat(ai): add provider interfaces and deterministic mock embeddings`.

---

### Task 4: GitHub REST client with retries and rate-limit handling

**Files:**
- Create: `backend/app/services/{__init__,github_client}.py`
- Test: `backend/tests/unit/test_github_client.py`

**Interfaces:**
- Produces:
  - Exceptions: `GitHubError(Exception)`, `GitHubNotFound(GitHubError)`, `GitHubRateLimited(GitHubError)` with `reset_at: datetime | None`.
  - `ReadmeResult(text: str, html_url: str, download_url: str | None)` (dataclass).
  - `GitHubClient(base_url: str, token: str | None, *, transport: httpx.BaseTransport | None = None, timeout: float = 15.0, max_retries: int = 4, max_wait_seconds: float = 60.0, sleep: Callable[[float], None] = time.sleep, now: Callable[[], datetime] = lambda: datetime.now(UTC))`. It is a context manager (closes its `httpx.Client`).
    - `get_repository(full_name: str) -> dict` (GET `/repos/{full_name}`, follows redirects so renamed repos resolve).
    - `get_readme(full_name: str) -> ReadmeResult | None` (GET `/repos/{full_name}/readme`, decodes base64 `content` as UTF-8 with `errors="replace"`, returns None on 404).
    - `get_languages(full_name: str) -> dict[str, int]`.
  - Headers: `Accept: application/vnd.github+json`, `X-GitHub-Api-Version: 2022-11-28`, `User-Agent: devatlas-ingest`, and `Authorization: Bearer <token>` only when a token is set.
  - Retry policy (shared `_request`):
    - 404 or 451 → `GitHubNotFound`, no retry.
    - 5xx, `httpx.TransportError`, or a timeout → retry with backoff of `2**attempt` seconds (1, 2, 4, 8), up to `max_retries`, then `GitHubError`.
    - 403 or 429 with a `retry-after` header → sleep that many seconds if ≤ `max_wait_seconds`, then retry. Otherwise `GitHubRateLimited`.
    - 403 or 429 with `x-ratelimit-remaining: 0` → wait until `x-ratelimit-reset` (epoch) if that is ≤ `max_wait_seconds` away, then retry. Otherwise `GitHubRateLimited(reset_at)`.
    - Any other 4xx → `GitHubError` carrying the status and the GitHub `message`.

- [ ] **Step 1: Write failing tests** using `httpx.MockTransport` and a recording `sleep`:

```python
def test_retries_server_errors_with_backoff(): # 502, 502, 200
    client, sleeps = make_client([resp(502), resp(502), resp(200, json={"id": 1})])
    assert client.get_repository("o/n") == {"id": 1}
    assert sleeps == [1, 2]

def test_not_found_is_not_retried():
    client, sleeps = make_client([resp(404, json={"message": "Not Found"})])
    with pytest.raises(GitHubNotFound): client.get_repository("o/missing")
    assert sleeps == []

def test_rate_limit_far_in_future_raises_with_reset():
    reset = int(NOW.timestamp()) + 3600
    client, _ = make_client([resp(403, headers={"x-ratelimit-remaining": "0",
                                                "x-ratelimit-reset": str(reset)})])
    with pytest.raises(GitHubRateLimited) as e: client.get_repository("o/n")
    assert e.value.reset_at == datetime.fromtimestamp(reset, UTC)

def test_retry_after_is_honoured():
    client, sleeps = make_client([resp(429, headers={"retry-after": "2"}), resp(200, json={})])
    client.get_repository("o/n"); assert sleeps == [2]

def test_readme_decoded_and_missing_readme_is_none():
    ...  # base64 "IyBIaQ==" → ReadmeResult(text="# Hi", ...); 404 → None

def test_token_sent_only_when_configured():
    ...  # assert "authorization" in request.headers iff token given
```

- [ ] **Step 2: Run** `uv run pytest tests/unit/test_github_client.py -q` → FAIL.
- [ ] **Step 3: Implement** `GitHubClient` per the interface.
- [ ] **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `feat(ingest): add GitHub REST client with backoff and rate-limit handling`.

---

### Task 5: Curated list + snapshot builder + build the real seed snapshot

**Files:**
- Create: `backend/data/curated_repositories.yaml`, `backend/app/schemas/{__init__,snapshot}.py`, `backend/app/services/snapshot_builder.py`, `backend/scripts/{__init__,build_seed_snapshot}.py`, `backend/data/seed_snapshot/*.json` (generated)
- Test: `backend/tests/unit/test_snapshot_builder.py`

**Interfaces:**
- Consumes: `GitHubClient`, `GitHubNotFound`, `GitHubRateLimited` (Task 4).
- Produces:
  - `CuratedEntry(full_name: str, category: CategorySlug, featured: bool = False)` and `load_curated(path: Path) -> list[CuratedEntry]` (rejects duplicates case-insensitively).
  - `CategorySlug = Literal["ai_ml","llm_agents_mcp","backend","frontend","databases_search","devops_platform","data_engineering","developer_tools","learning"]`, plus `CATEGORY_LABELS: dict[CategorySlug, str]` (e.g. `"llm_agents_mcp": "LLMs, agents & MCP"`).
  - `RepoSnapshot` (pydantic, `extra="ignore"`): `github_id: int, full_name: str, owner: str, name: str, description: str|None, html_url: str, homepage_url: str|None, topics: list[str], primary_language: str|None, languages: dict[str,int], license_spdx: str|None, license_name: str|None, stars: int|None, forks: int|None, open_issues: int|None, archived: bool, default_branch: str|None, created_at_github, updated_at_github, pushed_at_github: datetime|None, readme_text: str|None, readme_url: str|None, readme_truncated: bool, fetched_at: datetime, category: CategorySlug, featured: bool`. Helper `RepoSnapshot.from_github(repo: dict, readme: ReadmeResult|None, languages: dict, entry: CuratedEntry, fetched_at: datetime) -> RepoSnapshot` truncates README to `README_MAX_CHARS = 40_000`, maps `license.spdx_id == "NOASSERTION"` → `license_spdx=None` with `license_name` kept, and uses the API's canonical `full_name` (renames).
  - `build_snapshot(client: GitHubClient, entries: list[CuratedEntry], out_dir: Path, *, refresh: bool = False, now: Callable[[], datetime]) -> BuildReport(written: list[str], skipped: list[str], failed: dict[str, str], rate_limited_until: datetime | None)`. File name: `f"{owner}__{name}.json".lower()` from the **requested** name, written with `json.dumps(..., indent=2, ensure_ascii=False, sort_keys=True)`, UTF-8, `\n`. Existing files are skipped unless `refresh`. `GitHubNotFound` is recorded in `failed` and the build continues. `GitHubRateLimited` stops the loop and sets `rate_limited_until`.
  - CLI: `uv run python -m scripts.build_seed_snapshot [--refresh] [--only owner/name ...]` prints the report and exits with 0, or with 2 when rate-limited (with the reset time and a "set GITHUB_TOKEN or rerun later" hint).
- Curated list (write exactly these; `*` = `featured: true`):
  - backend: `celery/celery*`, `rq/rq`, `coleifer/huey`, `Bogdanp/dramatiq`, `taskiq-python/taskiq`, `agronholm/apscheduler`, `fastapi/fastapi*`, `encode/starlette`, `pallets/flask`, `django/django`, `expressjs/express`, `nestjs/nest`, `casbin/casbin`, `casbin/pycasbin`, `authlib/authlib`, `keycloak/keycloak`, `ory/kratos`, `supabase/supabase`
  - frontend: `vercel/next.js*`, `facebook/react`, `vuejs/core`, `sveltejs/svelte`, `tailwindlabs/tailwindcss`, `shadcn-ui/ui*`, `TanStack/query`, `pmndrs/zustand`, `react-hook-form/react-hook-form`, `colinhacks/zod`
  - databases_search: `pgvector/pgvector*`, `redis/redis`, `meilisearch/meilisearch`, `typesense/typesense`, `qdrant/qdrant`, `duckdb/duckdb`, `sqlalchemy/sqlalchemy`, `prisma/prisma`
  - ai_ml: `pytorch/pytorch`, `huggingface/transformers*`, `scikit-learn/scikit-learn`, `mlflow/mlflow`
  - llm_agents_mcp: `langchain-ai/langchain`, `run-llama/llama_index`, `modelcontextprotocol/python-sdk*`, `modelcontextprotocol/servers`, `ollama/ollama*`, `vllm-project/vllm`, `BerriAI/litellm`, `pydantic/pydantic-ai`
  - devops_platform: `kubernetes/kubernetes`, `hashicorp/terraform`, `opentofu/opentofu`, `prometheus/prometheus`, `grafana/grafana`, `argoproj/argo-cd`, `traefik/traefik`
  - data_engineering: `apache/airflow`, `dagster-io/dagster`, `PrefectHQ/prefect`, `dbt-labs/dbt-core`, `apache/spark`, `pola-rs/polars`
  - developer_tools: `astral-sh/ruff*`, `astral-sh/uv`, `pre-commit/pre-commit`, `microsoft/playwright`, `pytest-dev/pytest`, `getsentry/sentry`
  - learning: `donnemartin/system-design-primer`, `microsoft/generative-ai-for-beginners`, `karpathy/nanoGPT`, `codecrafters-io/build-your-own-x`

- [ ] **Step 1: Write failing tests** with a fake client object (no network):

```python
def test_writes_snapshot_and_skips_existing(tmp_path):
    report = build_snapshot(fake_client(), [entry("Celery/Celery")], tmp_path, now=FIXED)
    assert report.written == ["celery/celery"]
    data = json.loads((tmp_path / "celery__celery.json").read_text(encoding="utf-8"))
    assert data["github_id"] == 123 and data["category"] == "backend"
    assert build_snapshot(fake_client(), [entry("celery/celery")], tmp_path, now=FIXED).skipped == ["celery/celery"]

def test_not_found_recorded_and_build_continues(tmp_path): ...
def test_rate_limit_stops_build_and_reports_reset(tmp_path): ...
def test_noassertion_license_becomes_unknown_spdx(): ...
def test_readme_truncated_at_limit(): ...  # 40_001 chars → len 40_000, readme_truncated True
def test_curated_list_rejects_case_insensitive_duplicates(tmp_path): ...
def test_repo_curated_file_is_valid():
    entries = load_curated(DATA_DIR / "curated_repositories.yaml")
    assert len(entries) == 71 and {e.category for e in entries} == set(CATEGORY_LABELS)
```

- [ ] **Step 2: Run** `uv run pytest tests/unit/test_snapshot_builder.py -q` → FAIL.
- [ ] **Step 3: Implement** the schema, builder, and CLI.
- [ ] **Step 4: Run** → PASS.
- [ ] **Step 5: Build the real snapshot.** Run `uv run python -m scripts.build_seed_snapshot` (with `GITHUB_TOKEN` set in `.env` if possible; otherwise rerun after each rate-limit reset until there are no failures except genuine 404s). Expected: ~71 JSON files in `backend/data/seed_snapshot/`. If any repo 404s, replace it in the curated YAML with a same-category real alternative, rerun, and note it in the commit message.
- [ ] **Step 6: Commit** `feat(ingest): add curated list, snapshot builder, and GitHub seed snapshot` (include the generated JSON).

---

### Task 6: README chunking and extractive mock analyzer

**Files:**
- Create: `backend/app/services/chunking.py`, `backend/app/schemas/analysis.py`, `backend/app/ai/repository_analyzer.py`
- Test: `backend/tests/unit/test_chunking.py`, `backend/tests/unit/test_mock_analyzer.py`

**Interfaces:**
- Consumes: `RepoSnapshot` (Task 5).
- Produces:
  - `Chunk(position: int, section_title: str | None, content: str, content_hash: str, source_url: str | None, source_type: Literal["readme","metadata"])`.
  - `clean_markdown(md: str) -> str`: strips HTML tags/comments, image syntax `![..](..)`, badge-only lines, and code fences' language tags (code content is kept), and collapses 3+ blank lines.
  - `chunk_readme(md: str, source_url: str | None, *, max_chars: int = 1200, overlap: int = 150, max_chunks: int = 40) -> list[Chunk]`: splits on `#`–`###` headings. The section title is the nearest heading. Long sections are split on paragraph boundaries with overlap. Chunks under 40 chars are dropped. `content_hash = sha256(content)`.
  - `metadata_chunk(snap: RepoSnapshot) -> Chunk` (position −1, source_type `"metadata"`, text = full_name + description + topics; `source_url = html_url`).
  - Schemas (pydantic, `extra="forbid"`): `Capability(name: str, description: str, evidence: list[str], confidence: Literal["high","medium","low"])`, and `RepositoryAnalysisOut(summary: str|None, problem_solved: str|None, category: str|None, subcategory: str|None, capabilities: list[Capability], use_cases: list[str], supported_languages: list[str], integrations: list[str], requirements: list[str], limitations: list[str], maturity: Literal["unknown","experimental","active","mature","inactive"], target_users: list[str], keywords: list[str], analysis_version: str, model_name: str, prompt_version: str)`.
  - `MockRepositoryAnalyzer.analyze(snap: RepoSnapshot, chunks: list[Chunk]) -> RepositoryAnalysisOut`. **Extractive only**:
    - `summary` is the description, or else the first prose paragraph of the README (≤300 chars), or else None.
    - `problem_solved`, `subcategory`, and `use_cases` are left empty.
    - `capabilities` holds up to 8 bullet items from sections whose title matches `/feature|highlight|capabilit|why|what/i`. The name is the bullet text with markdown removed, cut to 80 chars at a word boundary. Evidence is `[the full bullet text]`. Confidence is `"medium"`.
    - `supported_languages` lists the top 3 languages by bytes. `keywords` are the topics with `-` replaced by spaces.
    - `category` is the curated category. `maturity` is `"inactive"` if the repo is archived, else `"unknown"`.
    - `analysis_version="mock-extractive-v1"`, `model_name="mock"`, `prompt_version="none"`.

- [ ] **Step 1: Write failing tests.**

```python
def test_chunks_follow_headings_and_hash_content(): ...  # "# A\npara\n## B\npara2" → titles ["A","B"]
def test_long_section_split_with_overlap(): ...           # 3000-char section → ≥3 chunks, each ≤1200, consecutive overlap
def test_html_images_and_badges_removed():
    out = clean_markdown('<p align="center"><img src="x"></p>\n[![CI](b.svg)](ci)\nReal text')
    assert out.strip() == "Real text"
def test_max_chunks_enforced(): ...
def test_empty_or_none_readme_gives_no_chunks(): assert chunk_readme("", None) == []
def test_analyzer_extracts_feature_bullets_with_evidence(): ...
def test_analyzer_never_invents_fields_when_readme_missing():
    a = MockRepositoryAnalyzer().analyze(snap(readme_text=None, description=None), [])
    assert a.summary is None and a.capabilities == [] and a.problem_solved is None
def test_analysis_schema_rejects_unknown_fields(): ...
```

- [ ] **Step 2: Run** `uv run pytest tests/unit/test_chunking.py tests/unit/test_mock_analyzer.py -q` → FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** → PASS. Also run a quick sanity script over the real snapshot: `uv run python -c "..."` printing chunk counts per repo. Every repo with a README must get ≥1 chunk.
- [ ] **Step 5: Commit** `feat(analysis): add README chunking and extractive mock analyzer`.

---

### Task 7: Ingestion service, demo user, and idempotent seed command

**Files:**
- Create: `backend/app/services/ingestion_service.py`, `backend/app/services/users.py`, `backend/scripts/seed_demo_data.py`, `backend/tests/fixtures/snapshots/*.json` (4 synthetic test fixtures: `acme__jobs.json` (Python task queue README mentioning retries and scheduling), `acme__ui.json` (TypeScript UI kit), `acme__bare.json` (no README, null description, null license, null stars), `acme__searchy.json` (search engine))
- Test: `backend/tests/db/test_ingestion.py`

**Interfaces:**
- Consumes: `RepoSnapshot`, `chunk_readme`, `metadata_chunk`, `MockRepositoryAnalyzer`, `Providers`, models.
- Produces:
  - `DEMO_USER_ID = UUID("00000000-0000-4000-8000-000000000001")`, `ensure_demo_user(session) -> User` (email `demo@example.com`, display name `Demo user`).
  - `IngestResult(repository_id: UUID, created: bool, content_changed: bool)`.
  - `ingest_snapshot(session: Session, snap: RepoSnapshot, providers: Providers, *, data_source: str = "seed_snapshot") -> IngestResult`:
    1. Upsert by `github_id`, updating every metadata column (including `full_name`, `owner`, and `name`, so renames update in place). Set `last_ingested_at=now`, `source_fetched_at=snap.fetched_at`.
    2. Insert a `RepositorySnapshot(stars, forks, open_issues, snapshot_at=snap.fetched_at)` unless one already exists for that timestamp.
    3. Build chunks: `[metadata_chunk] + chunk_readme(...)`. If the ordered list of `content_hash` values equals the stored one **and** an analysis exists, then `content_changed=False` and stop here.
    4. Otherwise delete the old chunks (which cascades to embeddings), insert the new chunks, upsert the analysis, and embed. One `summary` embedding: `full_name + description + keywords + summary + capability names`. One embedding per chunk: `section_title + content`. Texts that embed to an all-zero vector are skipped.
    5. `refresh_search_vector(session, repo_id)` runs a single parameterized `UPDATE`. Weight A = name + owner. B = description + topics + analysis keywords + capability names. C = `left(readme_content, 100000)`. Dictionary `'english'`; topics have `-` replaced by spaces.
  - `seed_from_directory(session, directory: Path, providers: Providers) -> SeedReport(created: int, updated: int, unchanged: int)`: commits once per repo and calls `ensure_demo_user` first.
  - CLI: `uv run python -m scripts.seed_demo_data [--dir data/seed_snapshot]` prints the report.

- [ ] **Step 1: Write failing tests** (`pytestmark = pytest.mark.db`):

```python
def test_seed_is_idempotent(db_session, providers):
    first = seed_from_directory(db_session, FIXTURES, providers)
    second = seed_from_directory(db_session, FIXTURES, providers)
    assert (first.created, second.created, second.unchanged) == (4, 0, 4)
    assert count(db_session, Repository) == 4
    assert count(db_session, RepositorySnapshot) == 4
    assert count(db_session, RepositoryChunk) == first_chunk_count  # unchanged

def test_rename_updates_in_place(db_session, providers):
    ingest_snapshot(db_session, snap("acme/jobs", github_id=9), providers)
    ingest_snapshot(db_session, snap("acme/jobs-ng", github_id=9), providers)
    assert [r.full_name for r in db_session.scalars(select(Repository))] == ["acme/jobs-ng"]

def test_changed_readme_rechunks_and_reembeds(db_session, providers): ...
def test_repo_with_missing_fields_ingests(db_session, providers):
    r = ingest_snapshot(db_session, load_fixture("acme__bare.json"), providers)
    repo = db_session.get(Repository, r.repository_id)
    assert repo.license_spdx is None and repo.stars is None and repo.readme_content is None
    assert repo.search_vector is not None    # metadata chunk still indexed
def test_demo_user_created_once(db_session): ...
```

- [ ] **Step 2: Run** `uv run pytest tests/db/test_ingestion.py -q` → FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** → PASS. Then seed the dev DB: `uv run python -m scripts.seed_demo_data` → `created≈71`. Run it again → `unchanged≈71`.
- [ ] **Step 5: Commit** `feat(ingest): idempotent ingestion with chunks, analysis, embeddings, seed command`.

---

### Task 8: Retrieval — keyword, semantic, and RRF fusion

**Files:**
- Create: `backend/app/services/ranking.py`, `backend/app/services/search_service.py`
- Test: `backend/tests/unit/test_rrf.py`, `backend/tests/unit/test_tsquery.py`, `backend/tests/db/test_search.py`

**Interfaces:**
- Consumes: models, `EmbeddingProvider`, `tokenize` (Task 3).
- Produces:
  - `SearchFilters(category: str|None = None, language: str|None = None, license_spdx: str|None = None, include_archived: bool = False)` (frozen dataclass). Language and license match case-insensitively.
  - `RankedHit(repository_id: UUID, rank: int, score: float, chunk_id: UUID | None = None)`.
  - `FusedHit(repository_id: UUID, score: float, ranks: dict[str, int | None])`.
  - `rrf_fuse(rankings: Mapping[str, Sequence[UUID]], k: int = 60) -> list[FusedHit]`: the rank is 1-based position. Sort by score descending, then best individual rank ascending, then `str(id)`. `k <= 0` raises `ValueError`.
  - `build_or_tsquery(terms: Sequence[str]) -> str | None`: each term → `tokenize` → keep tokens matching `^[a-z0-9]+$` (drops `c++`, `next.js`, etc. for the FTS path; the semantic path still sees them). A multi-token term becomes `(a <-> b)`. Terms are joined with ` | `. Returns None when empty. The string is passed as a bind parameter to `to_tsquery('english', :q)`.
  - `keyword_search(session, *, text: str | None = None, terms: Sequence[str] | None = None, filters: SearchFilters, limit: int = 50) -> list[RankedHit]`. `text` uses `websearch_to_tsquery('english', :text)` (AND semantics). `terms` uses `build_or_tsquery` (OR semantics). Ordered by `ts_rank_cd(search_vector, q, 32)` descending, then `stars` descending with nulls last.
  - `semantic_search(session, query_vector: list[float], *, filters: SearchFilters, limit: int = 50, chunk_pool: int = 300) -> list[RankedHit]`. Returns `[]` for an all-zero vector. Fetches the top `chunk_pool` embeddings by `cosine_distance` joined to filtered repositories, keeps the best (min distance) per repository, sets `score = 1 - distance`, and records `chunk_id`.
  - `apply_filters(stmt, filters) -> Select` (shared helper used by the repository listing in Task 9).

- [ ] **Step 1: Write failing tests.**

```python
# unit/test_rrf.py
def test_rrf_combines_lists():
    A, B, C = uuids(3)
    fused = rrf_fuse({"keyword": [A, B], "semantic": [B, C]}, k=60)
    assert [f.repository_id for f in fused] == [B, A, C]
    assert fused[0].score == pytest.approx(1/62 + 1/61)
    assert fused[1].ranks == {"keyword": 1, "semantic": None}
def test_rrf_tie_break_is_deterministic(): ...
def test_rrf_rejects_non_positive_k(): ...

# unit/test_tsquery.py
@pytest.mark.parametrize("terms", [["c++"], ['"'], ["&|!:*()"], ["'; drop table"], []])
def test_hostile_terms_never_produce_invalid_syntax(terms):
    q = build_or_tsquery(terms)
    assert q is None or re.fullmatch(r"[a-z0-9 |()<\->]+", q)
def test_multiword_terms_become_phrases():
    assert build_or_tsquery(["task queue", "retries"]) == "(task <-> queue) | retries"

# db/test_search.py   (seeded with the 4 fixtures)
def test_keyword_text_search_finds_readme_term(seeded): ...   # "retries" → acme/jobs first
def test_keyword_or_terms_search(seeded): ...
@pytest.mark.parametrize("text", ["c++", '"unbalanced', "a & | ! b", "'; drop table repositories; --"])
def test_keyword_search_tolerates_hostile_text(seeded, text):
    keyword_search(seeded, text=text, filters=SearchFilters())   # must not raise
def test_filters_restrict_results(seeded): ...                 # language="typescript" → only acme/ui
def test_semantic_search_ranks_related_repo_first(seeded, providers): ...
def test_semantic_search_zero_vector_returns_empty(seeded): ...
```

- [ ] **Step 2: Run** `uv run pytest tests/unit/test_rrf.py tests/unit/test_tsquery.py tests/db/test_search.py -q` → FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `feat(search): keyword FTS, pgvector semantic search, and RRF fusion`.

---

### Task 9: Repository, facets, and saves API

**Files:**
- Create: `backend/app/schemas/common.py`, `backend/app/schemas/repository.py`, `backend/app/services/repository_service.py`, `backend/app/api/v1/repositories.py`, `backend/app/api/v1/saved.py`, `backend/app/api/deps.py`
- Modify: `backend/app/api/v1/router.py`
- Test: `backend/tests/db/test_repositories_api.py`, `backend/tests/unit/test_health_db.py` (add the 503 test)

**Interfaces:**
- Consumes: `get_db`, `ensure_demo_user`/`DEMO_USER_ID`, `keyword_search`, `apply_filters`, `SearchFilters`, `CATEGORY_LABELS`.
- Produces:
  - `get_current_user(session = Depends(get_db)) -> User` (the demo user, created if missing).
  - `Page[T]` generic: `items: list[T], page: int, page_size: int, total: int`.
  - `RepositoryCard`: `id, owner, name, full_name, description, html_url, primary_language, topics, license_spdx, license_name, stars, forks, pushed_at_github, archived, category, category_label, featured, data_source, source_fetched_at, is_saved: bool`.
  - `RepositoryDetail(RepositoryCard)`: adds `homepage_url, readme_url, languages, open_issues, created_at_github, updated_at_github, default_branch, readme_truncated, analysis: AnalysisView | None, maintenance_signals: list[Signal], sources: list[SourceRef]`.
    - `AnalysisView` is `RepositoryAnalysisOut` plus `generated_by_label: str` (`"Extractive demo analyzer (no LLM)"` for `model_name=="mock"`).
    - `Signal(label: str, value: str, explanation: str)` is built only from stored facts: "Last push" (date), "Archived" (if true), "Open issues" (if known). Each explanation reads "From GitHub metadata, snapshot <date>".
    - `SourceRef(label, url)` covers the GitHub repository, the README (if `readme_url`), and the homepage (if any).
  - Routes (static paths are registered **before** `/{owner}/{name}`):
    - `GET /repositories?q&category&language&license&sort&page&page_size` → `Page[RepositoryCard]`. `q` is ≤200 chars. `sort` is one of `relevance|stars|recent|name|featured`: the default is `relevance` when `q` is set, otherwise `featured` (featured first, then stars descending with nulls last). `page` ≥1. `page_size` is 1–50 with default 20. With `q`, use `keyword_search(text=q)`, and if that gives 0 hits, retry with `terms=q.split()` (OR fallback, roadmap deviation 9).
    - `GET /repositories/facets` → `{categories: [{value, label, count}], languages: [{value, count}], licenses: [{value, count}]}`, counting non-archived repos and excluding nulls.
    - `GET /repositories/{owner}/{name}` → `RepositoryDetail`, matched case-insensitively. Unknown repo → `NotFoundError("Repository owner/name not found")`.
    - `POST /repositories/{owner}/{name}/save` → `{"saved": true}`, idempotent (200 every time).
    - `DELETE /repositories/{owner}/{name}/save` → `{"saved": false}`, idempotent.
    - `GET /me/saved?page&page_size` → `Page[RepositoryCard]`, newest save first.
  - Any `OperationalError` during a request becomes `DatabaseUnavailableError` (503).

- [ ] **Step 1: Write failing tests** (`TestClient` with `get_db` overridden to the test session, seeded with fixtures):

```python
def test_list_default_sort_featured_then_stars(api): ...
def test_list_keyword_and_filters(api):
    r = api.get("/api/v1/repositories", params={"q": "retries", "language": "python"})
    assert [i["full_name"] for i in r.json()["items"]] == ["acme/jobs"]
def test_list_or_fallback_for_natural_phrase(api):
    r = api.get("/api/v1/repositories", params={"q": "retries banana"})   # AND finds nothing
    assert "acme/jobs" in [i["full_name"] for i in r.json()["items"]]
@pytest.mark.parametrize("q", ["c++", '"', "&|!:*()"])
def test_list_hostile_query_is_safe(api, q):
    assert api.get("/api/v1/repositories", params={"q": q}).status_code == 200
def test_pagination_metadata(api): ...      # page_size=2 → total 4, 2 items
def test_page_size_validation(api):
    r = api.get("/api/v1/repositories", params={"page_size": 500})
    assert r.status_code == 422 and r.json()["error"]["code"] == "validation_error"
def test_detail_case_insensitive_and_unknown_404(api):
    assert api.get("/api/v1/repositories/ACME/Jobs").json()["full_name"] == "acme/jobs"
    r = api.get("/api/v1/repositories/nobody/nothing")
    assert r.status_code == 404 and r.json()["error"]["code"] == "not_found"
def test_detail_missing_values_are_null_not_invented(api):
    d = api.get("/api/v1/repositories/acme/bare").json()
    assert d["stars"] is None and d["license_spdx"] is None and d["analysis"]["summary"] is None
def test_save_unsave_idempotent_and_listed(api):
    for _ in range(2): assert api.post("/api/v1/repositories/acme/jobs/save").json() == {"saved": True}
    assert [i["full_name"] for i in api.get("/api/v1/me/saved").json()["items"]] == ["acme/jobs"]
    assert api.get("/api/v1/repositories/acme/jobs").json()["is_saved"] is True
    for _ in range(2): assert api.delete("/api/v1/repositories/acme/jobs/save").json() == {"saved": False}
    assert api.get("/api/v1/me/saved").json()["total"] == 0
def test_facets_counts(api): ...

# tests/unit/test_health_db.py (add here: needs no database)
def test_data_endpoint_503_when_db_down():
    r = TestClient(create_app(bad_db_settings)).get("/api/v1/repositories")
    assert r.status_code == 503 and r.json()["error"]["code"] == "database_unavailable"
```

- [ ] **Step 2: Run** `uv run pytest tests/db/test_repositories_api.py -q` → FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** `uv run pytest -q` → all PASS. Smoke-test against the dev DB: `GET /api/v1/repositories?q=task%20queue` returns real seed repos.
- [ ] **Step 5: Commit** `feat(api): repository listing, detail, facets, and saves`.

---

### Task 10: Query understanding, evidence, reranking, and `POST /assistant/recommend`

**Files:**
- Create: `backend/data/vocabulary.yaml`, `backend/app/ai/vocabulary.py`, `backend/app/ai/query_understanding.py`, `backend/app/services/evidence.py`, `backend/app/services/recommendation_service.py`, `backend/app/schemas/recommendation.py`, `backend/app/api/v1/assistant.py`
- Test: `backend/tests/unit/test_query_understanding.py`, `backend/tests/unit/test_evidence.py`, `backend/tests/db/test_recommend_api.py`

**Interfaces:**
- Consumes: `keyword_search`, `semantic_search`, `rrf_fuse`, `SearchFilters`, `Providers`, `RepositoryCard` builder from `repository_service`, models.
- Produces:
  - `vocabulary.yaml` schema:
    ```yaml
    stack_terms:          # canonical name → role, implied language, aliases
      FastAPI: {role: backend, language: Python, aliases: ["fastapi", "fast api"]}
    capabilities:         # requirement concept
      background_jobs:
        label: background jobs
        triggers: ["background job", "background jobs", "task queue", "job queue", "worker", "async task"]
        expansions: ["task queue", "job queue", "worker", "asynchronous tasks"]
        category: backend
    licenses: {mit: MIT, "apache": Apache-2.0, "apache 2": Apache-2.0, gpl: GPL-3.0}
    ```
    Required `stack_terms` (at least): Python, TypeScript, JavaScript, Go, Rust, Java, FastAPI, Django, Flask, Express, NestJS, Next.js, React, Vue, Svelte, PostgreSQL, MySQL, Redis, MongoDB, Kubernetes, Docker, AWS. Required `capabilities` (at least): background_jobs, retries, scheduling, rbac (role-based access control/authorization/permissions), authentication, multi_tenancy, full_text_search (incl. "typo tolerance", "search engine"), vector_search (embeddings, similarity search, vector database), local_llm (run models locally, inference), agents_tools (agent, tool calling, MCP, model context protocol), data_pipelines (orchestration, workflows, ETL, DAG), infrastructure_as_code (provision, terraform-style IaC), linting_formatting, browser_testing (end-to-end tests), form_validation (schema validation), system_design_learning, monitoring_alerting (metrics, alerting, observability), server_state_caching (data fetching, caching), dataframes (analytics, columnar). Expansions must use generic technical terms, **not product names** (so recommendations come from the content, not the dictionary).
  - `Vocabulary.load(path) -> Vocabulary`, `match_phrases(text, phrases) -> list[str]` (case-insensitive, word-boundary, handles `.`/`+`/`-` in phrases).
  - `QueryIntent` (pydantic): `goal: str, requirements: list[str], constraints: list[str], known_stack: dict[str, list[str]], category: str | None, preferred_license: str | None, keywords: list[str], inferred: list[str], clarifying_question: str | None`.
  - `understand_query(text: str, vocab: Vocabulary) -> QueryIntent` (mock, deterministic):
    - `goal` is the trimmed query.
    - `requirements` are the labels of the capabilities whose triggers appear, in vocabulary order.
    - `known_stack` holds stack terms found in the text, grouped by role (canonical names).
    - `category` is the most common category among the matched capabilities (None if there are none).
    - `preferred_license` is set only when the query contains the word "license"/"licensed" near a known license.
    - `constraints` are the explicit phrases matched by `/(must|should|without|no|only|prefer)\b[^.,;]*/i`.
    - `keywords` are the requirement labels + expansions + stack names, de-duplicated.
    - `inferred` holds notes such as `"Category 'backend' inferred from: background jobs"`.
    - `clarifying_question` is `"What are you building, and what should the tool do? For example: 'a job queue for a FastAPI app'."` **only** when the query has fewer than 3 non-stopword tokens and no requirement or stack match. Otherwise it is None.
  - `Evidence(snippet: str, source_url: str | None, section_title: str | None, source_type: str)`. The snippet is a ±160-char window around the match, trimmed to word boundaries, with `…` added at cut points.
  - `find_evidence(chunks: Sequence[RepositoryChunk], phrases: Sequence[str], max_items: int = 2) -> list[Evidence]`.
  - Response schemas: `RequirementCheck(requirement: str, status: Literal["evidenced","not_established"], evidence: list[Evidence])`. `CompatibilityNote(stack_item: str, status: Literal["evidenced","inferred","not_established"], note: str, evidence: Evidence | None)`. `RetrievalSignals(keyword_rank: int|None, semantic_rank: int|None, rrf_score: float, requirements_evidenced: int, requirements_total: int)`. `Recommendation(rank: int, repository: RepositoryCard, reasons: list[str], requirements: list[RequirementCheck], compatibility: list[CompatibilityNote], limitations: list[str], signals: RetrievalSignals)`. `RecommendRequest(query: str (3..1000 chars, stripped), max_results: int = 5 (1..10), filters: FilterIn | None)`. `RecommendResponse(query: str, intent: QueryIntent, results: list[Recommendation], pipeline: PipelineInfo(provider: str, embedding_model: str, rrf_k: int, keyword_candidates: int, semantic_candidates: int, notes: list[str]), clarifying_question: str | None)`.
  - `recommend(session, request: RecommendRequest, providers: Providers, vocab: Vocabulary, settings: Settings, user_id: UUID) -> RecommendResponse`, implementing spec §6.5:
    1. **Understand** with `understand_query`.
    2. **Expand:** the semantic text is `goal + requirement labels + expansions`. The keyword terms are `intent.keywords` plus non-stopword query tokens.
    3. **Retrieve:** `keyword_search(terms=…, limit=50)` and `semantic_search(embed(semantic_text), limit=50)`, both using the request filters (archived excluded).
    4. **Merge:** `rrf_fuse({"keyword": …, "semantic": …}, k=settings.rrf_k)` and take the top 30.
    5. **Rerank:** load the chunks for the candidates. For each requirement, run `find_evidence` with that capability's triggers+expansions. Coverage = the number of evidenced requirements. If the intent has ≥1 requirement, drop candidates with coverage 0. Sort by (coverage descending, RRF score descending). Stars are **never** used.
    6. **Verify:** compatibility per stack item. `evidenced` when an alias appears in the repo's chunks (with an evidence snippet). `inferred` when the stack item's language equals the repo's `primary_language` (note: `"Same primary language (Python); integration not confirmed by source."`). Otherwise `not_established`. A stack item that is a language itself compares directly with `primary_language` → `evidenced` (source: GitHub metadata).
    7. **Explain** with factual, templated reasons only: `"README mentions: retries, scheduling"`, `"Curated category: Backend"`, `"Matched by keyword search (rank 2) and semantic search (rank 1)"`. Limitations come from facts: `"Archived on GitHub"`, `"No license detected in GitHub metadata"`, `"Not established from source: <requirement>"` for each uncovered requirement, and `"No push in over 12 months as of snapshot <date>"` when `source_fetched_at - pushed_at_github > 365 days`.
    8. **Learn:** deferred to M4 (feedback capture). Add `"Feedback capture arrives in M4"` to `pipeline.notes`.
    - The first `max_results` are returned with `rank` 1..n. If there are zero results, return `results=[]`, plus a `pipeline.notes` entry suggesting the user rephrase or remove filters.
  - `POST /api/v1/assistant/recommend` → `RecommendResponse` (sets `is_saved` on cards for the current user).

- [ ] **Step 1: Write failing tests.**

```python
# unit/test_query_understanding.py
def test_extracts_requirements_stack_and_category(vocab):
    i = understand_query("I am building a FastAPI application and need background jobs "
                         "with retries and scheduling", vocab)
    assert i.requirements == ["background jobs", "retries", "scheduling"]
    assert i.known_stack == {"backend": ["FastAPI"]}
    assert i.category == "backend" and i.preferred_license is None
    assert any("inferred" in n.lower() or "backend" in n for n in i.inferred)
def test_does_not_invent_constraints(vocab):
    assert understand_query("vector database for embeddings", vocab).constraints == []
def test_explicit_constraint_kept(vocab):
    assert "without Redis" in understand_query("task queue without Redis", vocab).constraints[0]
def test_short_vague_query_asks_clarifying_question(vocab):
    assert understand_query("help me", vocab).clarifying_question is not None
def test_short_but_specific_query_does_not_ask(vocab):
    assert understand_query("rbac", vocab).clarifying_question is None
def test_dotted_and_cased_stack_terms(vocab):
    assert understand_query("NEXT.JS app with postgres", vocab).known_stack == \
        {"frontend": ["Next.js"], "database": ["PostgreSQL"]}

# unit/test_evidence.py
def test_snippet_window_and_source(): ...   # 1000-char chunk, match at 500 → snippet ≤ 330 chars, starts/ends with "…", source_url/section_title copied
def test_word_boundary_no_false_positive():
    assert find_evidence([chunk("Retrying is unsupported; see retryable-x")], ["retry"]) == []
    assert find_evidence([chunk("Automatic retries with backoff")], ["retries"])[0].snippet

# db/test_recommend_api.py (fixtures seeded)
def test_recommend_returns_evidenced_shortlist(api):
    r = api.post("/api/v1/assistant/recommend",
                 json={"query": "Python task queue with retries and scheduling for FastAPI"})
    body = r.json()
    top = body["results"][0]
    assert top["repository"]["full_name"] == "acme/jobs"
    assert {c["requirement"]: c["status"] for c in top["requirements"]}["retries"] == "evidenced"
    assert top["requirements"][0]["evidence"][0]["snippet"]
    assert "%" not in json.dumps(body["results"])   # no match percentages anywhere
    fastapi = next(c for c in top["compatibility"] if c["stack_item"] == "FastAPI")
    assert fastapi["status"] in {"evidenced", "inferred"}
def test_unrelated_repos_filtered_out_when_requirements_known(api): ...  # acme/ui not in results
def test_unknown_vocabulary_query_still_returns_hybrid_results(api):
    r = api.post("/api/v1/assistant/recommend", json={"query": "something for searching my products"})
    assert r.status_code == 200
def test_nonsense_query_returns_empty_with_note(api):
    body = api.post("/api/v1/assistant/recommend", json={"query": "qwzxv plorf"}).json()
    assert body["results"] == [] and body["pipeline"]["notes"]
def test_query_validation(api):
    assert api.post("/api/v1/assistant/recommend", json={"query": "  "}).status_code == 422
def test_missing_license_listed_as_limitation(api): ...
```

- [ ] **Step 2: Run** `uv run pytest tests/unit/test_query_understanding.py tests/unit/test_evidence.py tests/db/test_recommend_api.py -q` → FAIL.
- [ ] **Step 3: Implement** (vocabulary first, then understanding, evidence, service, route).
- [ ] **Step 4: Run** `uv run pytest -q` → all PASS.
- [ ] **Step 5: Commit** `feat(assistant): evidence-backed recommendation pipeline with hybrid retrieval`.

---

### Task 11: Relevance smoke benchmark

**Files:**
- Create: `backend/eval/benchmark.yaml`, `backend/app/services/evaluation.py`, `backend/scripts/run_benchmark.py`
- Test: `backend/tests/unit/test_evaluation_metrics.py`, `backend/tests/db/test_benchmark.py`

**Interfaces:**
- Consumes: `recommend` (Task 10), the seed snapshot (Task 5).
- Produces:
  - `benchmark.yaml` entries: `{id, query, expected: [full_name...], must_have: [requirement labels], notes}`. Write exactly these 15:

    | id | query | expected (any) |
    |---|---|---|
    | jobs | I am building a FastAPI application and need background jobs with retries and scheduling | celery/celery, rq/rq, coleifer/huey, Bogdanp/dramatiq, taskiq-python/taskiq, agronholm/apscheduler |
    | rbac | role-based access control for a multi-tenant SaaS using Next.js and FastAPI | casbin/casbin, casbin/pycasbin, keycloak/keycloak |
    | fts | typo-tolerant full-text search engine for a product catalog | meilisearch/meilisearch, typesense/typesense |
    | vector | vector database for semantic similarity search over embeddings | qdrant/qdrant, pgvector/pgvector |
    | local-llm | run large language models locally on my laptop | ollama/ollama, vllm-project/vllm |
    | mcp | build an agent that calls tools through the Model Context Protocol | modelcontextprotocol/python-sdk, modelcontextprotocol/servers, pydantic/pydantic-ai, langchain-ai/langchain |
    | pipelines | orchestrate data pipelines with scheduling and retries | apache/airflow, dagster-io/dagster, PrefectHQ/prefect |
    | iac | infrastructure as code to provision cloud resources | hashicorp/terraform, opentofu/opentofu |
    | lint | fast Python linter and code formatter | astral-sh/ruff |
    | e2e | end-to-end browser testing for my web app | microsoft/playwright |
    | forms | form validation in React with TypeScript schemas | react-hook-form/react-hook-form, colinhacks/zod |
    | sysdesign | learn how large-scale systems are designed | donnemartin/system-design-primer |
    | monitoring | metrics monitoring and alerting for Kubernetes clusters | prometheus/prometheus, grafana/grafana |
    | server-state | fetch, cache and sync server state in a React app | TanStack/query |
    | dataframes | fast DataFrame library for analytics in Python | pola-rs/polars, duckdb/duckdb |

  - `hit_at_k(ranked: list[str], expected: set[str], k: int) -> bool`, `reciprocal_rank(ranked, expected) -> float` (0.0 if absent), `precision_at_k(ranked, expected, k) -> float`. All compare case-insensitively.
  - `run_benchmark(session, providers, vocab, settings, path) -> BenchmarkReport(per_query: list[QueryResult(id, ranked, hit_at_5, rr, p_at_5)], hit_rate_at_5: float, mrr: float, mean_p_at_5: float)`.
  - CLI: `uv run python -m scripts.run_benchmark` prints a table and the aggregates (against `DATABASE_URL`).

- [ ] **Step 1: Write failing tests.**

```python
# unit
def test_metrics():
    assert reciprocal_rank(["a/x", "b/y"], {"B/Y"}) == 0.5
    assert hit_at_k(["a", "b", "c"], {"c"}, 2) is False
    assert precision_at_k(["a", "b"], {"a"}, 5) == pytest.approx(0.2)
# db, marked benchmark: seeds the REAL snapshot (module-scoped) into the test DB
def test_benchmark_hit_rate_floor(real_seeded_session, providers, vocab, settings):
    report = run_benchmark(real_seeded_session, providers, vocab, settings, BENCHMARK)
    assert report.hit_rate_at_5 >= 0.8, report.per_query
```

- [ ] **Step 2: Run** `uv run pytest tests/unit/test_evaluation_metrics.py tests/db/test_benchmark.py -q` → FAIL.
- [ ] **Step 3: Implement** the metrics and runner. Then run the benchmark. If the hit rate is below 0.8, improve **vocabulary triggers/expansions with generic terms** or the chunking/weighting. Do not add product names to expansions or special-case queries. Record the final hit@5 and MRR in the commit message.
- [ ] **Step 4: Run** `uv run pytest -q` → all PASS.
- [ ] **Step 5: Commit** `test(eval): add relevance smoke benchmark (hit@5=<x>, MRR=<y>)`.

---

### Task 12: Frontend scaffold, design system, app shell, API client

**Files:**
- Create: `frontend/` via create-next-app; `frontend/.env.example`; `frontend/lib/{api,types,format}.ts`; `frontend/components/layout/{app-shell,nav-links,mobile-nav,demo-badge}.tsx`; `frontend/components/states/{empty-state,error-state}.tsx`; `frontend/app/layout.tsx`, `frontend/app/page.tsx`, `frontend/app/(app)/layout.tsx`, `frontend/app/(app)/error.tsx`; `frontend/vitest.config.ts`, `frontend/vitest.setup.ts`
- Test: `frontend/tests/api.test.ts`, `frontend/tests/format.test.ts`

**Interfaces:**
- Consumes: the backend API (Tasks 1, 9, 10).
- Produces:
  - `lib/types.ts`: TS mirrors of `Page<T>`, `RepositorySummary` (mirrors backend `RepositoryCard`; renamed so it doesn't clash with the component), `RepositoryDetail`, `AnalysisView`, `Signal`, `SourceRef`, `Facets`, `Health`, `QueryIntent`, `Evidence`, `RequirementCheck`, `CompatibilityNote`, `RetrievalSignals`, `Recommendation`, `RecommendResponse`, `ApiErrorBody`.
  - `lib/api.ts`: `API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api/v1"`. `class ApiError extends Error { status: number; code: string; details: unknown }`. `apiFetch<T>(path: string, init?: RequestInit): Promise<T>` (JSON. A non-2xx response with the error schema → `ApiError(code)`. A non-JSON error → `ApiError(code "http_error")`. A network failure → `ApiError(status 0, code "network_error", message "Cannot reach the API. Is the backend running?")`). Typed helpers: `getHealth()`, `listRepositories(params: {q?, category?, language?, license?, sort?, page?, pageSize?})`, `getFacets()`, `getRepository(owner, name)`, `saveRepository(owner, name)`, `unsaveRepository(owner, name)`, `listSaved(page?)`, `recommend(body: {query: string; max_results?: number})`. Server-side calls pass `cache: "no-store"`.
  - `lib/format.ts`: `formatCount(n: number | null | undefined): string` (`null` → `"Not available"`, `1234` → `"1.2k"`, `1_250_000` → `"1.3M"`, `999` → `"999"`), `formatDate(iso: string | null): string` (`null` → `"Not available"`, otherwise e.g. `"12 Mar 2026"` in en-GB, UTC), `snapshotLabel(dataSource, fetchedAt)` → `"Snapshot · 10 Nov 2026"` for `seed_snapshot`, `"Live · …"` otherwise.
  - Shell: a header with a product-name placeholder ("Open-Source Intelligence", configurable via `lib/brand.ts`), nav links **Explore**, **Ask AI**, and **Saved** (active state via `usePathname`, `aria-current="page"`), a `DemoBadge` (a server component calling `getHealth()` that shows "Demo mode · mock AI" when `demo_mode`, and "API unreachable" with a tooltip on error), a mobile disclosure menu (a button with `aria-expanded`, closed on route change and Escape), and a skip-to-content link. `/` redirects to `/explore`.
  - `ErrorState({title, message, onRetry?})` and `EmptyState({title, message, action?})`. `(app)/error.tsx` uses `ErrorState` with `reset()`.

- [ ] **Step 1: Check current docs** for create-next-app, Tailwind v4, and shadcn CLI (Context7 `/vercel/next.js`, shadcn) and invoke the `frontend-design:frontend-design` skill for visual direction. Constraints from spec §10.1: a neutral background, one restrained accent, dense but calm, no gradients or glassmorphism, and no big hero.
- [ ] **Step 2: Scaffold.** From the repo root: `npx create-next-app@latest frontend --ts --tailwind --eslint --app --no-src-dir --import-alias "@/*" --use-npm --no-turbopack` (adjust flags to the current CLI). Then in `frontend/`: `npx shadcn@latest init` and `npx shadcn@latest add button input textarea badge card select skeleton separator tooltip`, then `npm i lucide-react` and `npm i -D vitest @vitejs/plugin-react jsdom @testing-library/react @testing-library/user-event @testing-library/jest-dom`. Add `"test": "vitest run"` to `package.json` scripts. Write `.env.example` with `NEXT_PUBLIC_API_BASE_URL=http://localhost:8000/api/v1`.
- [ ] **Step 3: Write failing tests.**

```ts
// tests/format.test.ts
test("formatCount never invents values", () => {
  expect(formatCount(null)).toBe("Not available");
  expect(formatCount(999)).toBe("999");
  expect(formatCount(1234)).toBe("1.2k");
  expect(formatCount(1_250_000)).toBe("1.3M");
});
test("snapshotLabel", () => expect(snapshotLabel("seed_snapshot", "2026-11-10T09:00:00Z")).toBe("Snapshot · 10 Nov 2026"));
// tests/api.test.ts (stub global fetch)
test("maps error schema to ApiError", async () => { /* 404 {error:{code:"not_found",...}} → rejects ApiError code not_found status 404 */ });
test("network failure becomes network_error", async () => { /* fetch rejects TypeError → code network_error, status 0 */ });
test("listRepositories builds query string and omits empty params", async () => { /* expect URL ...?q=queue&page_size=20 */ });
```

- [ ] **Step 4: Run** `npm test` → FAIL.
- [ ] **Step 5: Implement** the lib files and the shell.
- [ ] **Step 6: Run** `npm test` → PASS. Run `npm run lint` → clean. Run `npm run build` → succeeds. Run `npm run dev` with the backend running and check: the shell renders, the demo badge shows "Demo mode · mock AI", nav works by keyboard, and the mobile menu toggles. With the backend stopped, the badge shows "API unreachable".
- [ ] **Step 7: Commit** `feat(frontend): scaffold Next.js app shell, API client, and states`.

---

### Task 13: Explore page, repository card, save button, detail page

**Files:**
- Create: `frontend/app/(app)/explore/{page,loading}.tsx`, `frontend/app/(app)/repositories/[owner]/[name]/{page,loading,not-found}.tsx`, `frontend/components/repository/{repository-card,save-button,metric,license-label,snapshot-note}.tsx`, `frontend/components/search/{search-bar,filter-bar,pagination}.tsx`
- Test: `frontend/tests/repository-card.test.tsx`, `frontend/tests/save-button.test.tsx`

**Interfaces:**
- Consumes: `lib/api.ts`, `lib/format.ts`, `lib/types.ts`, states (Task 12). Backend routes (Task 9).
- Produces:
  - `RepositoryCard({repo}: {repo: RepositorySummary})` shows:
    - The owner/name heading, linking to `/repositories/{owner}/{name}` (the whole card is reachable via that link, not a nested clickable div).
    - The description (plain text, clamped to 2 lines), primary language, stars and forks via `Metric` (shows "Not available"), last push date, up to 4 topics, and a category badge.
    - `LicenseLabel`: the SPDX id, else `license_name`, else "License not detected".
    - An external "GitHub" link (`target="_blank" rel="noopener noreferrer"`, to `html_url`) and a `SaveButton`.
  - `SaveButton({owner, name, initialSaved, onChange?})` is a client component with an optimistic toggle that calls `saveRepository`/`unsaveRepository`. On error it rolls back and shows inline text "Couldn't save — try again". It uses `aria-pressed`, and its label is "Save"/"Saved" (with an icon, not color alone).
  - Explore (`searchParams: Promise<{q?, category?, language?, license?, sort?, page?}>`) is a server component:
    - `SearchBar` (a client form that submits on Enter or the Search button and updates `?q=` while preserving filters). Placeholder: "Search repositories, topics, or describe what you're building". A secondary link "Describe a problem in Ask AI →" goes to `/ask?q=<q>`.
    - `FilterBar` uses selects for category, language, license, and sort, populated from `getFacets()`. Changes update the URL, and there is a "Clear filters" button.
    - A result count line ("24 repositories"), a responsive grid (1/2/3 columns), and `Pagination` (prev/next links with a disabled state).
    - The `SnapshotNote` banner reads: "Demo data: metrics are from a GitHub snapshot taken {date}."
    - Empty: `EmptyState` with "No repositories match. Try fewer words or clear filters." plus a Clear action. Error: `ErrorState` with Retry (`router.refresh()` via a small client wrapper).
    - `loading.tsx` shows card skeletons.
  - Detail (`params: Promise<{owner, name}>`) has these sections:
    - A header (name, description, GitHub link, SaveButton) and a metrics row (stars, forks, open issues, language, license, last push, default branch).
    - "Overview" (`analysis.summary` or "Not established"), with the label `analysis.generated_by_label` and the note "Generated analysis — not official project documentation".
    - "Capabilities" (each with its evidence quote in a `<blockquote>` and a link to the README source).
    - "Problem it solves" / "Use cases" / "Limitations", each showing "Not established (demo analyzer)" when empty.
    - "Maintenance signals" (label, value, explanation), "Languages" (top languages with percentages computed from bytes), "Sources" (`SourceRef` links), and an "Ask about alternatives" link to `/ask?q=Alternatives to {full_name}`.
    - Unknown repo → `notFound()` → the `not-found.tsx` page with a link back to Explore.

- [ ] **Step 1: Write failing tests.**

```tsx
test("card shows Not available for missing metrics and license fallback", () => {
  render(<RepositoryCard repo={{ ...card, stars: null, forks: null, license_spdx: null, license_name: null }} />);
  expect(screen.getAllByText("Not available").length).toBeGreaterThanOrEqual(2);
  expect(screen.getByText("License not detected")).toBeInTheDocument();
  expect(screen.getByRole("link", { name: /github/i })).toHaveAttribute("href", card.html_url);
  expect(screen.getByRole("link", { name: card.full_name })).toHaveAttribute("href", "/repositories/acme/jobs");
});
test("card renders README-derived text as plain text", () => {
  render(<RepositoryCard repo={{ ...card, description: "<img src=x onerror=alert(1)>" }} />);
  expect(screen.getByText("<img src=x onerror=alert(1)>")).toBeInTheDocument();
});
test("save button is optimistic and rolls back on failure", async () => {
  vi.mocked(saveRepository).mockRejectedValueOnce(new ApiError(503, "database_unavailable", "down"));
  render(<SaveButton owner="acme" name="jobs" initialSaved={false} />);
  await userEvent.click(screen.getByRole("button", { name: /save/i }));
  expect(await screen.findByText(/couldn't save/i)).toBeInTheDocument();
  expect(screen.getByRole("button", { name: /save/i })).toHaveAttribute("aria-pressed", "false");
});
```

- [ ] **Step 2: Run** `npm test` → FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** `npm test` and `npm run lint` and `npm run build` → PASS. Check manually against the seeded dev DB:
  - Search "queue" with Enter and with the button.
  - Category and language filters change the results.
  - Clear filters works.
  - Pagination works.
  - The card opens the detail page, and GitHub opens the real repo.
  - Save on a card is still saved after a reload.
  - A detail page for an unknown repo shows not-found.
  - The layout works at 375px width.
- [ ] **Step 5: Commit** `feat(frontend): Explore, repository cards, save, and detail page`.

---

### Task 14: Ask AI page

**Files:**
- Create: `frontend/app/(app)/ask/page.tsx`, `frontend/components/assistant/{ask-form,example-prompts,intent-summary,recommendation-card,requirement-list,compatibility-list,evidence-quote}.tsx`
- Test: `frontend/tests/ask.test.tsx`

**Interfaces:**
- Consumes: `recommend()` and the types (Task 12), `SaveButton`/`LicenseLabel`/`Metric` (Task 13), and `POST /assistant/recommend` (Task 10).
- Produces:
  - `/ask` page (reads `?q=` to prefill and auto-submit once), built from these parts:
    - `AskForm`: a labelled textarea "Describe what you're trying to build". Enter submits and Shift+Enter adds a newline. It has an "Ask" button, client-side validation (3–1000 chars, with an inline message), and the button is disabled while the request is pending.
    - `ExamplePrompts`: 4 buttons that fill the textarea and submit. Use the benchmark queries `jobs`, `rbac`, `vector`, and `pipelines`.
    - A session-only history list of earlier queries in this tab. Clicking one re-runs it. It is labelled "This session".
  - Response rendering:
    - `clarifying_question`, if present, is shown as a callout above the results.
    - `IntentSummary` ("How I read your request"): the requirements, the known stack, explicit constraints, and the inferred notes (each prefixed "Inferred:").
    - Results are a list of `RecommendationCard`s. Each card shows:
      - The rank, the repository name (linking to the detail page), the description, language, license, and stars.
      - "Why it fits" (`reasons`) and `RequirementList`. Each requirement shows a check or dash icon **and** text "Mentioned in source" / "Not established", plus up to 2 `EvidenceQuote`s (blockquote, with a section title and a "View source" link to `source_url`).
      - `CompatibilityList` (text badges "Evidenced" / "Inferred" / "Not established" with the note), and "Limitations".
      - A signals line: `Keyword rank 2 · Semantic rank 1 · RRF 0.032`, using a `<details>` element whose summary is "Why this order?" and explains RRF in one sentence.
      - `SaveButton` and a GitHub link.
    - A footer note reads `Demo mode: mock AI (lexical embeddings, extractive analysis)` when `pipeline.provider === "mock"`.
  - States:
    - Pending: 3 card skeletons with the text "Searching the repository index…".
    - Zero results: `EmptyState` with the pipeline notes and a link to Explore.
    - Error: `ErrorState` with Retry, re-submitting the same query.

- [ ] **Step 1: Write failing tests** (mock `recommend`):

```tsx
test("submits on Enter and renders evidence-backed results", async () => {
  vi.mocked(recommend).mockResolvedValue(responseFixture);   // 1 result, retries evidenced, FastAPI inferred
  render(<AskPage />);
  await userEvent.type(screen.getByLabelText(/describe what you're trying to build/i), "task queue with retries{Enter}");
  expect(await screen.findByRole("link", { name: "acme/jobs" })).toBeInTheDocument();
  expect(screen.getByText("Mentioned in source")).toBeInTheDocument();
  expect(screen.getByText("Inferred")).toBeInTheDocument();
  expect(screen.queryByText(/%/)).not.toBeInTheDocument();
});
test("rejects too-short input without calling the API", async () => { ... });
test("shows clarifying question", async () => { ... });
test("shows retryable error on API failure", async () => { ... });  // click Retry → recommend called twice
test("empty results show guidance", async () => { ... });
```

- [ ] **Step 2: Run** `npm test` → FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** `npm test`, `npm run lint`, and `npm run build` → PASS. Manual end-to-end against the seeded dev DB:
  - Ask the spec's milestone query "I need background jobs with retries for a project using FastAPI" and confirm a short list with evidence quotes appears.
  - Save one result, then open its detail page and confirm it shows as saved.
  - Also try the benchmark examples, keyboard-only use, and a 375px width.
- [ ] **Step 5: Commit** `feat(frontend): Ask AI page with evidence-backed recommendations`.

---

### Task 15: Saved page, README, CI, and final verification

**Files:**
- Create: `frontend/app/(app)/saved/{page,loading}.tsx`, `.github/workflows/ci.yml`
- Modify: `README.md` (root)
- Test: `frontend/tests/saved.test.tsx`

**Interfaces:**
- Consumes: `listSaved()`, `RepositoryCard`, `SaveButton`, states.
- Produces:
  - `/saved` lists saved repositories as cards with pagination. Unsaving from this page removes the card (via the `SaveButton` `onChange` callback). The empty state reads "Nothing saved yet. Save repositories from Explore or Ask AI." with links to both.
  - `ci.yml` runs on push and PR:
    - Job `backend`: `astral-sh/setup-uv`, `uv sync`, `uv run ruff check .`, and `uv run pytest -q`. DB tests skip because no `TEST_DATABASE_URL` secret is configured; this is noted in the README.
    - Job `frontend`: Node 22, `npm ci`, `npm run lint`, `npm test`, and `npm run build`.
  - `README.md` sections:
    - What it is.
    - Status (M1) and a demo flow.
    - Architecture (a diagram from spec §7.3, adapted: no Redis, CLI jobs).
    - Prerequisites (Neon, optional GitHub token).
    - Setup and commands (PowerShell): backend install, migrate (`uv run alembic upgrade head`), seed, run API, tests, benchmark, rebuild snapshot; frontend install, dev, test, build.
    - Environment variables (pointing to both `.env.example` files).
    - Demo mode explained (mock providers, snapshot data and its date).
    - Deviations from spec (copied from roadmap §7) and Known limitations (lexical mock semantics, no LLM analysis, no conversations/feedback/projects/radar yet).
    - Roadmap (link to the roadmap doc).

- [ ] **Step 1: Write the failing test** `saved.test.tsx`: renders the saved items; after unsave resolves the card disappears; when there are no items the empty state shows both links.
- [ ] **Step 2: Run** `npm test` → FAIL.
- [ ] **Step 3: Implement** the saved page, CI workflow, and README.
- [ ] **Step 4: Full verification** (use superpowers:verification-before-completion):
  - Backend: `uv run ruff check .` and `uv run pytest -q`, with `TEST_DATABASE_URL` set → all pass, benchmark included.
  - Frontend: `npm run lint`, `npm test`, and `npm run build` → pass.
  - Fresh-DB check on the Neon `test` branch:
    - `uv run alembic downgrade base` then `upgrade head`, then seed twice (second run `unchanged≈71`).
  - Walk through the spec §20 Product checklist items that are in M1 scope against the running app and record the results in the PR description:
    - Explore, keyword search, filters, detail, sources.
    - The natural-language question, retrieved candidates, reasons, evidence, and labelled unknowns.
    - Save/unsave and the saved view.
    - Demo mode, and mobile at 375px.
- [ ] **Step 5: Commit** `feat: saved page, CI, and setup documentation for M1`.
