# DevAtlas: Open-Source Intelligence Platform (V0)

Describe an engineering problem ("I need background jobs with retries for a project using
FastAPI") and get a short list of open-source repositories, with quotes from each
project's own README showing which of your requirements it mentions. Unknowns and
inferred compatibility are labelled as such.

> `DevAtlas` is the internal working name; the UI uses a neutral placeholder brand.
> The product specification is [`open_source_intelligence_v0_spec.md`](open_source_intelligence_v0_spec.md).

## Status: M1 (discovery foundation) + Discover (trending and repository intelligence)

What works today, in demo mode with no AI credentials:

- **Explore**: browse 71 curated, real GitHub repositories; keyword search; category,
  language and license filters; sorting; pagination.
- **Repository detail**: GitHub metadata, an extractive overview, feature bullets quoted
  from the README, maintenance signals, sources.
- **Ask AI**: natural-language request → query understanding → hybrid retrieval
  (Postgres full-text + pgvector, fused with Reciprocal Rank Fusion) → rerank by
  requirements evidenced in the README → per-requirement evidence quotes, stack
  compatibility (evidenced / inferred / not established) and limitations.
- **Saved**: save and unsave from any page; a saved list.
- **Discover**: Trending (today / week / month, from GitHub Trending), Rising, New & recently
  discovered, Hidden gems and a weekly mix, filterable by category and language. Every card
  shows the measured signals behind its placement; without enough history a feed says it is
  popularity-based instead of claiming growth ([methodology](docs/discover-ranking.md)).
- **Repository intelligence**: Gemini-generated reports (what it is, why it is notable, who
  should care, use cases, project ideas, technical overview, limitations) in which every item
  cites README excerpts; "Ask AI about this repository" answers only from the repository's
  own documentation; "What can I build?" ideas on demand.
- **Compare**: 2–4 repositories on the same dimensions, with no overall winner.
- **Relevance smoke benchmark**: 15 developer queries, hit@5 = 1.00, MRR = 0.93
  (see [Evaluation](#evaluation) for the caveat).

The roadmap (M2–M7) and all technical decisions are in
[`docs/superpowers/plans/2026-11-10-v0-roadmap.md`](docs/superpowers/plans/2026-11-10-v0-roadmap.md).

## Architecture

```text
 Next.js 16 UI (frontend/)          Explore · Ask AI · Repository · Saved
        │ HTTP (JSON, /api/v1)
 FastAPI modular monolith (backend/app)
   api/        routes, error schema, request limits, demo-user dependency
   services/   ingestion · chunking · search (FTS + pgvector) · RRF ranking
               · recommendation pipeline · evidence · evaluation
   ai/         provider interfaces · mock providers · query understanding · analyzer
        │
 PostgreSQL + pgvector (hosted on Neon)
   repositories · analyses · README chunks · embeddings (HNSW, cosine) · snapshots
   · users · saved_repositories
        ▲
 CLI jobs (backend/scripts): build GitHub snapshot → seed (chunk, analyse, embed, index)
```

Ingestion and analysis run as idempotent CLI jobs, never in request paths. Repository
content is untrusted: it is stored as text, rendered as plain text, and never treated as
instructions.

## Prerequisites

- Python 3.12+ and [uv](https://docs.astral.sh/uv/); Node.js 22 and npm.
- A PostgreSQL database with the `vector` extension. The project is developed against
  [Neon](https://neon.tech) (free tier): one branch for the app, a second branch for tests.
  `docker-compose.yml` offers a local `pgvector/pgvector:pg17` alternative (not verified on
  the primary development machine).
- Optional: a GitHub token with public read access, only needed to rebuild the snapshot.

## Configuration

Settings are read from the repo-root `.env`, then `backend/.env` (later files win).
See [`backend/.env.example`](backend/.env.example) and
[`frontend/.env.example`](frontend/.env.example).

| Variable | Purpose |
|----------|---------|
| `DATABASE_URL` (or `neon_db`) | App database. Plain `postgresql://` URLs are converted to the psycopg driver automatically. |
| `DATABASE_URL_UNPOOLED` | Optional direct (non-pooled) URL for migrations. |
| `TEST_DATABASE_URL` (or `neon_db_test`) | Separate database for tests. **It is wiped by the test suite.** |
| `GITHUB_TOKEN` | Optional; raises the GitHub API limit from 60 to 5,000 requests/hour. |
| `AI_PROVIDER` | `auto` (default: Gemini when a key is set, otherwise the deterministic mock), `mock`, or `gemini`. |
| `GEMINI_API_KEY` (or `gemini`) | Gemini key for intelligence reports, build ideas and repository Q&A. |
| `GEMINI_MODEL` | Default `gemini-3.5-flash-lite` (the free tier allows only 20 requests/day for `gemini-3.5-flash`). |
| `AI_REQUESTS_PER_MINUTE` | Limit for on-demand AI endpoints and the report job (default 10). |
| `NEXT_PUBLIC_API_BASE_URL` | Frontend → API base URL (default `http://localhost:8000/api/v1`). |

Secrets live only in `.env` files (git-ignored) and are never sent to the browser.

## Run it locally (PowerShell)

```powershell
# Backend
cd backend
uv sync
uv run alembic upgrade head              # create the schema
uv run python -m scripts.seed_demo_data  # load the committed snapshot (idempotent)
uv run uvicorn app.main:app --reload     # http://localhost:8000/docs

# Frontend (second terminal)
cd frontend
npm install
npm run dev                              # http://localhost:3000
```

Behind a TLS-inspecting corporate proxy, use the OS certificate store:
`$env:UV_NATIVE_TLS=1` for uv and `$env:NODE_OPTIONS="--use-system-ca"` for npm/Next.js.

## Background jobs (Discover)

All jobs are idempotent CLI scripts (no queue service); run them from `backend/`:

| Job | What it does | Suggested schedule |
|-----|--------------|--------------------|
| `uv run python -m scripts.track_github_trending` | Record github.com/trending (daily view) and add new trending repositories | daily |
| `uv run python -m scripts.refresh_repositories` | GitHub metadata + daily snapshot + recent stars/forks/commits/releases | daily |
| `uv run python -m scripts.compute_feeds` | Recompute Trending/Rising/New/Hidden gems/Weekly | daily, after refresh |
| `uv run python -m scripts.generate_insights` | Gemini reports for new or changed READMEs (throttled, resumable) | daily |
| `uv run python -m scripts.discover_new` | Find new repositories via GitHub search (quality-filtered) | weekly |
| `uv run python -m scripts.backfill_history --days 35` | One-off history backfill | once / after adding repositories |
| `uv run python -m scripts.export_snapshots` | Write history and reports to `backend/data/` for offline seeding | after the jobs above |

Windows Task Scheduler example (daily at 06:00):

```powershell
# refresh.ps1 (save next to the repository, adjust the path)
Set-Location C:/path/to/DevAtlas/backend
uv run python -m scripts.track_github_trending
uv run python -m scripts.refresh_repositories
uv run python -m scripts.compute_feeds
uv run python -m scripts.generate_insights

# Register it once:
schtasks /Create /SC DAILY /ST 06:00 /TN "DevAtlas refresh" /TR "powershell -NoProfile -File C:/path/to/DevAtlas/refresh.ps1"
```

## Tests and checks

```powershell
cd backend
uv run ruff check .
uv run pytest -q                          # unit tests always; DB tests need TEST_DATABASE_URL
uv run pytest -q -m "not benchmark"       # skip the slow benchmark (seeds 71 repos)

cd ../frontend
npm run lint
npm test
npm run build
```

CI (`.github/workflows/ci.yml`) runs the same checks. Database tests run in CI only if a
`TEST_DATABASE_URL` repository secret is configured; otherwise they are skipped.

## Data

- `backend/data/curated_repositories.yaml`: the curated list (category, featured).
- `backend/data/seed_snapshot/*.json`: GitHub API responses captured on **10 Nov 2026**
  (metadata, languages, README truncated to 40,000 characters). Metrics are shown as
  "Snapshot · date", never as live values. Rebuild with
  `uv run python -m scripts.build_seed_snapshot --refresh`.
- Repositories are keyed by GitHub's stable repository ID, so renames (e.g.
  `casbin/casbin` → `apache/casbin`) update in place.

## Evaluation

`uv run python -m scripts.run_benchmark` runs [`backend/eval/benchmark.yaml`](backend/eval/benchmark.yaml)
against the app database and prints hit@5, MRR and precision@5 per query.
Current result (mock providers): **hit@5 1.00, MRR 0.93, mean P@5 0.40**. The demo
vocabulary was written alongside these queries, so this is a smoke test of the pipeline,
not an unbiased measurement; a larger held-out set is planned for M4. Low P@5 shows that
lower-ranked results are noisy (very large READMEs mention many concepts).

## Demo mode and AI

Seeding loads committed snapshots of GitHub metadata, history and Gemini reports, so the
whole app, including Discover and stored reports, works without any credentials. Without a
Gemini key, only the on-demand actions ("Generate more ideas", "Ask AI about this
repository") are unavailable, and they say so.

Ask AI recommendations (the M1 pipeline) stay deterministic in every mode:

- **Embeddings** are deterministic feature-hashed word vectors: lexical, not truly
  semantic.
- **Query understanding** uses [`backend/data/vocabulary.yaml`](backend/data/vocabulary.yaml)
  (generic technical terms, no product names).
- **Analysis** is extractive only: summaries and capabilities are copied from GitHub
  metadata and README feature lists. Fields it cannot establish (problem solved, use
  cases, limitations) are shown as "Not established".

The UI shows a "Demo mode: mock AI" badge and labels generated analysis.

## Deviations from the specification

1. **Database hosting**: hosted Neon instead of Docker Compose for local development
   (Compose file provided, unverified).
2. **No Redis/Celery**: ingestion and processing are CLI jobs (allowed by spec §7.1).
3. **Mock AI is lexical/extractive** until Bedrock providers land in M3.
4. **Seed data is a dated GitHub snapshot**, labelled as such in the UI.
5. **API surface**: `GET /repositories/facets` replaces `/repositories/categories`;
   `GET /me/saved` lists saves.
6. **Curated `category`/`featured`** are stored on repositories, separate from the
   generated analysis category.
7. **One current analysis per repository** (version, model and prompt version stored).
8. **Saves are a flat list in M1**; named collections arrive in M2.
9. **Explore search** uses AND keyword semantics and falls back to OR when nothing matches.
10. **No shadcn/ui yet**: native accessible elements and a few small components.
11. **Discover categories** follow the 12 categories from the Discover brief (supersedes the
    original 9); curated labels live in `backend/data/curated_repositories.yaml`.
12. **Contributor activity** is not collected; it is listed as unavailable rather than estimated.
13. **Compare list** is stored in the browser (no accounts yet).

## Known limitations

- **Star growth needs history.** The configured fine-grained GitHub token cannot list
  stargazers, so star growth builds up from daily snapshots: Trending is popularity-based
  until 1–30 days of snapshots exist, and Rising needs 30 days. A classic token (no scopes)
  enables an immediate 35-day backfill.
- **Getting-started links** in reports are often empty: cleaned README chunks drop link URLs,
  and only URLs present in the sources are kept.
- **Free-tier Gemini quotas** limit how many reports and answers can be generated per day.

- No LLM in the loop yet: explanations are templated from facts, and compatibility is
  established only by text mentions or a shared primary language.
- No authentication: everything belongs to one demo user.
- No conversation history persistence, feedback capture, project profiles, Tech Radar or
  comparison yet (M4–M6).
- Trending/growth is not shown: only one snapshot exists, so growth cannot be measured.
- Database tests are slow against a remote database (~6 minutes for the benchmark).
