# DevAtlas: Open-Source Intelligence Platform (V0)

Describe an engineering problem ("I need background jobs with retries for a project using
FastAPI") and get a short list of open-source repositories, with quotes from each
project's own README showing which of your requirements it mentions. Unknowns and
inferred compatibility are labelled as such.

> `DevAtlas` is the internal working name; the UI uses a neutral placeholder brand.
> The product specification is [`open_source_intelligence_v0_spec.md`](open_source_intelligence_v0_spec.md).

## Status: milestone M1 (foundation + end-to-end discovery)

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
| `AI_PROVIDER` | `mock` (default, no credentials). `bedrock` arrives in M3. |
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

## Demo mode

With `AI_PROVIDER=mock` (the only provider in M1):

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

## Known limitations

- No LLM in the loop yet: explanations are templated from facts, and compatibility is
  established only by text mentions or a shared primary language.
- No authentication: everything belongs to one demo user.
- No conversation history persistence, feedback capture, project profiles, Tech Radar or
  comparison yet (M4–M6).
- Trending/growth is not shown: only one snapshot exists, so growth cannot be measured.
- Database tests are slow against a remote database (~6 minutes for the benchmark).
