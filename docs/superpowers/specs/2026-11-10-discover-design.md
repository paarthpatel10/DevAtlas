# Discover: Trending, Rising, New, Hidden Gems and Repository Intelligence (design)

**Status:** proposed (2026-11-10). **Builds on:** M1 (`feat/m1-foundation`).
**Spec:** `open_source_intelligence_v0_spec.md` (§2.3 D "Stay ahead", §5.5 Tech Radar, §6.7
comparison, §8.6 snapshots, §11 AI provider and prompt safety). **Request:** the user's
"Trending & Discover" feature brief (2026-11-10), summarised below.

## 1. Intent

Help developers find open-source projects **worth their attention**, not just popular ones,
and understand them quickly. The flow that must work end to end:

> Open Discover → find an unfamiliar repository → understand what it is → see why it is
> interesting (with evidence) → see what you could build with it → save it or open GitHub.

Every repository should answer: **What is it? Why is it interesting? How useful is it?**

## 2. Goals, non-goals, anti-goals

**Goals**
- A Discover page (new nav item) with feeds: Trending Now (today / week / month / all time),
  Rising, New & Recently Discovered, Hidden Gems, Explore by Category, and a Weekly collection.
- Real growth signals from stored history (stars, forks, commits, releases), never from a
  single snapshot.
- An AI intelligence report per repository, generated with Gemini, grounded in README
  excerpts and GitHub facts, with every claim traceable to a source excerpt.
- Card actions that all work: Explore, "Why is this interesting?", "What can I build with
  this?", Save, Compare.
- A repository detail page with the full report and "Ask AI about this repository".
- A comparison page for 2 to 4 repositories (spec §6.7: consistent dimensions, no winner).
- Discovery of new repositories through GitHub search within the curated categories.
- Demo mode still works with no credentials.

**Non-goals (this iteration)**
- Personalised discovery and following categories (deferred; *my call*, the user can pull
  them forward). Weekly collection is included because it is a cheap derived feed.
- Indexing all of GitHub, contributor-level analytics, private repositories.
- Real semantic embeddings (Gemini embeddings are a possible follow-up; search keeps the
  current hashed embeddings so M1 behaviour and benchmark stay stable).
- Celery/Redis: jobs remain idempotent CLI scripts (M1 decision D2), schedulable with
  Windows Task Scheduler or cron.

**Anti-goals (would be a failure even if it "works")**
- Any star growth, "trending" reason, capability, integration or idea that cannot be traced
  to stored data or a source excerpt.
- Calling popularity "quality" or "production ready", or showing opaque scores or match
  percentages.
- Calling GitHub or Gemini during page loads (other than the on-demand AI actions).
- A Discover page that is empty or misleading because history is missing.

## 3. Decisions

| # | Decision | Whose call |
|---|----------|-----------|
| D1 | **LLM provider = Gemini** via REST `generateContent` with `responseMimeType: application/json` + `responseSchema`, key from repo-root `.env` (`gemini`, also accepted as `GEMINI_API_KEY`). Model configurable (`GEMINI_MODEL`); the builder verifies an available Flash-class model with the models list endpoint and records it. Implemented behind the existing `LLMProvider` interface; `AI_PROVIDER=gemini`. | User (Gemini); model choice is the builder's |
| D2 | **Without a key**, everything except on-demand AI actions works: feeds, signals, cards, and stored reports. On-demand actions show "needs an AI provider" with the env var to set. | Mine |
| D3 | **Stored reports are committed as a dated snapshot** (`backend/data/insights_snapshot/*.json`, model and date recorded), like the GitHub snapshot, so demo mode shows real grounded reports without a key. | Mine |
| D4 | **History backfill** uses GitHub GraphQL (`stargazers` / `forks` ordered by date DESC, `releases`, default-branch commit history counts) because REST cannot reach recent stargazers of repos above ~40k stars. REST `/stats/commit_activity` may be used for weekly/daily commits. Backfill window: 35 days, capped at 30 pages per repo per connection; a capped count is stored and shown as a lower bound ("≥3,000"). | Mine (spec §7.1: GraphQL "where it offers a clear advantage") |
| D5 | **Categories** become the 12 from the brief. Existing slugs are kept where they map; `llm_agents_mcp` splits into `llm_agents` and `mcp_automation`; new `full_stack`, `security`. Labels: AI & Machine Learning, LLMs & AI Agents, MCP & Developer Automation, Backend Engineering, Frontend Engineering, Full-Stack Development, Databases & Search, Data Engineering, DevOps & Cloud, Security, Developer Productivity, Open-Source Learning Resources. Curated list re-labelled accordingly (e.g. MCP repos → `mcp_automation`, supabase → `full_stack`, keycloak/ory/kratos → `security`). | Mine |
| D6 | **Compare list** lives in the browser (localStorage, max 4) because there are no accounts; the comparison itself is a server endpoint. | Mine |
| D7 | Ranking parameters live in `backend/data/discover_ranking.yaml` and are documented in `docs/discover-ranking.md`. Feeds are **precomputed by a job**, not computed per request. | Mine |

## 4. Data: what is stored (database changes)

All via a new Alembic migration; reuse `repositories`, `repository_chunks`,
`repository_analyses`, `repository_snapshots`, `saved_repositories`.

- **`repositories`** (alter): `discovery_source` (`curated` | `search`), `first_indexed_at`
  (backfilled from `created_at`).
- **`repository_daily_stats`**: `repository_id`, `day` (date), `stars_gained`,
  `forks_gained`, `commits`, `stars_capped` (bool: count is a lower bound),
  unique (`repository_id`, `day`). Source of truth for windows (today / 7d / 30d).
  Filled by the backfill job and kept current by the refresh job.
- **`repository_releases`**: `repository_id`, `tag`, `name`, `published_at`, `url`,
  unique (`repository_id`, `tag`).
- **`repository_insights`**: one current report per repository: `report` (JSON, schema in
  §6), `model_name`, `prompt_version`, `source_hash` (hash of the chunks it was built from;
  a changed README makes the report stale), `generated_at`.
- **`ai_generations`**: cache for on-demand results (`kind` = `build_ideas` | `ask`,
  `repository_id`, `input_hash`, `output` JSON, `model_name`, `created_at`),
  unique (`kind`, `repository_id`, `input_hash`).
- **`discovery_feed_entries`**: precomputed feeds: `feed` (`trending` | `rising` | `new` |
  `hidden_gem` | `weekly`), `period` (`day` | `week` | `month` | `all` | null),
  `repository_id`, `rank`, `score`, `signals` (JSON: the numbers behind the placement),
  `basis` (`growth` | `popularity_activity`), `computed_at`. Replaced atomically per run.

`repository_snapshots` keeps a daily row per repository from every refresh (spec §8.6).

## 5. Discovery and ranking methodology

Jobs (CLI, idempotent, rate-limit aware, reusing `GitHubClient` with a GraphQL method):
1. `discover_new` — GitHub search per category (topics + language + `created:>` /
   `pushed:>` qualifiers from the ranking config), at most N new repositories per category
   per run, respecting the search API limit (30 requests/min). New repositories go through the
   existing ingestion (chunks, analysis, embeddings, search vector) with
   `discovery_source=search`.
2. `backfill_history` — GraphQL backfill (D4) into `repository_daily_stats` and
   `repository_releases`.
3. `refresh` — daily: metadata snapshot, new daily stats since last run, new releases.
4. `compute_feeds` — writes `discovery_feed_entries` from the signals below.
5. `generate_insights` — Gemini reports for repositories with a missing or stale report,
   throttled to the free-tier rate limit, resumable.
6. `export_snapshots` — writes `insights_snapshot/` and a history snapshot so a fresh
   database can be seeded offline; `seed_demo_data` loads them.

Feeds (all thresholds configurable; none uses one global star cut-off):

- **Trending** (attracting attention now): rank by stars gained in the period
  (day / 7d / 30d), tie-broken by forks gained, then commits in the period. `all` ranks
  by total stars and is labelled **popularity**, not growth. If history does not cover the
  period, the feed falls back to popularity + recent activity and is labelled
  `basis = popularity_activity` in the API and UI.
- **Rising** (sustained momentum): growth relative to size, `stars_30d / max(stars_30d_ago,
  floor)`, requiring activity in at least 3 of the last 4 weeks; boosted when the 7-day
  rate exceeds the 30-day average rate (acceleration). Excludes the top of Trending-all so it
  surfaces momentum rather than incumbents.
- **New & Recently Discovered**: created within 90 days, or first indexed within 14 days,
  or first release within 30 days; ordered by early traction normalised by age plus README
  completeness. Small repositories are welcome.
- **Hidden Gems**: stars below the category's 40th percentile (category-relative, so it
  works for both niche and huge categories), pushed within 90 days, license present, and a
  README completeness score (has usage/install sections, feature list, length band) above a
  threshold; ordered by completeness and recent activity.
- **Weekly**: up to 10 repositories from this week's Trending, Rising, New and Hidden Gems,
  at most 3 per feed, with category diversity.

Each feed entry stores the exact numbers that placed it (`signals`), and the card shows them
("+412 stars this week", "v2.0 released 9 days ago", "commits in 4 of the last 4 weeks").
Scores are internal ordering devices and are never shown as quality.

## 6. AI intelligence report (Gemini)

Input: up to ~12 README chunks (most informative first), GitHub facts (language, topics,
license, dates, releases), never the whole README. Prompt rules (spec §11.2): the content is
marked as untrusted reference material; instructions inside it are ignored; facts only; every
claim cites chunk ids; say "not established" when the sources are silent; no tools, no
secrets in the prompt.

Report schema (validated strictly; invalid output is retried once, then the report is not
saved):
- `what_is_it`: plain explanation for a newcomer + one-line summary for cards.
- `problem_solved`
- `why_interesting`: technical points that make it notable (each with citations). The
  *trending reason* is **not** generated: it is assembled from feed `signals`.
- `who_should_care`: audiences with reason and citations.
- `use_cases`: each with citations.
- `build_ideas`: 2 to 3 ideas: title, what you build, how this repository is used,
  complementary technologies (marked as suggestions), citations for the capability relied on.
- `technical`: frameworks/dependencies, key capabilities, integrations, prerequisites,
  architecture overview (null unless documented), each with citations.
- `limitations`: documented limitations and unknowns.
- `getting_started`: links that exist in the README (validated as http(s) URLs from the
  source text).

Grounding check after generation: every citation must point to a provided chunk; claims with
no valid citation are removed (or kept only in `limitations` as "not established"). The UI
labels the report "AI-generated with <model> on <date> from the README; not official
documentation" and shows the cited excerpts on demand.

On-demand:
- **What can I build with this?** returns the stored ideas; "Generate more" calls Gemini with
  the same grounding rules and caches by input hash.
- **Ask AI about this repository**: retrieve the repository's most relevant chunks for the
  question (keyword + vector, scoped to the repository), answer only from them with
  citations; "The documentation doesn't cover this" when nothing relevant is found. Cached
  by question hash; rate-limited per process (configurable, default 10 requests/minute).
  Suggested questions from the brief are shown as buttons.

## 7. API (existing conventions: `/api/v1`, error schema, pagination)

- `GET /discover/trending?period=day|week|month|all&category&language&page&page_size`
- `GET /discover/rising`, `/discover/new`, `/discover/hidden-gems`, `/discover/weekly`
  (same filters where applicable)
- `GET /discover/categories`: categories with counts and a few top entries each
- `GET /repositories/{owner}/{name}/insights`: stored report + feed signals + freshness
- `POST /repositories/{owner}/{name}/build-ideas` (body: optional `more: true`)
- `POST /repositories/{owner}/{name}/ask` (body: `question`, 3 to 500 chars)
- `POST /repositories/compare` (body: 2 to 4 `owner/name`): consistent dimensions from
  stored data and reports, "fits when..." per repository, no winner
- Feed items reuse `RepositoryCard` plus `labels`, `signals`, `basis`, `one_liner`,
  `why_explore`.

## 8. Frontend

- Nav gains **Discover** (Explore, Discover, Ask AI, Saved; Compare appears when the list is
  non-empty).
- `/discover`: sections for Trending (period tabs), Rising, New, Hidden Gems, Weekly, and a
  category tab row with a language filter; each section links to a full-feed view with
  pagination.
- Discover card: existing card plus label (Trending / Rising / New / Hidden gem, as text),
  the signal line, AI one-liner, "Why explore this?", and the actions Explore, Why is this
  interesting? (inline expand), What can I build? (inline expand), Save, Compare.
- Repository detail: the report sections (overview, problem, why interesting with signals,
  capabilities, use cases, build ideas, technical overview, dependencies/integrations,
  getting started, license and maintenance, strengths and limitations, alternatives from the
  index (nearest repositories in the same category, labelled as related, not "better"),
  evidence) and the Ask panel.
- `/compare`: side-by-side table on desktop, stacked on mobile.
- Same design system as M1 (tokens, gazetteer list style, plain-text rendering of all
  third-party and model text, visible status words not colour alone). Loading, empty and
  error states for every section; an empty feed explains why (for example "no history yet
  for this period").

## 9. Quality bar

- Unit tests for every ranking rule (fixtures with known histories), grounding validation,
  prompt construction (untrusted framing present, no secrets), Gemini client parsing,
  retries and rate-limit handling with a mock transport; DB tests for feeds and API; frontend
  tests for cards, actions and empty/basis labels. No test calls the real Gemini or GitHub
  APIs.
- Honesty checks in tests: a feed with no history must report `basis=popularity_activity`;
  a report claim without a valid citation must be dropped; capped star counts render as "≥".
- Docs: `docs/discover-ranking.md` (methodology and parameters), README updates (jobs,
  scheduling, env vars, demo behaviour).

## 10. Builder notes (settled during review; *my calls*)

- Work happens on a new branch `feat/discover` created from `feat/m1-foundation`; `main` is
  untouched until the user chooses how to integrate M1.
- GitHub GraphQL requires `GITHUB_TOKEN` (present in the repo-root `.env`). Without it, the
  backfill job skips and feeds report `basis=popularity_activity`.
- Gemini receives only public README excerpts and GitHub metadata; nothing user-entered
  except Ask questions.

## 11. Left to the builder

Exact Gemini model id (verified against the models list), prompt wording within §6 rules,
chunk selection heuristics, README completeness scoring details, page sizes, the GitHub
search queries per category, and visual details within the existing design system.

## 12. Risks

- **Gemini free-tier rate limits**: report generation is throttled and resumable; stored
  reports are committed so the UI never depends on live generation.
- **GraphQL cost for very popular repositories**: page caps with lower-bound labelling.
- **Search-discovered repositories may be low quality or spam**: minimum signals (README
  present, license present, not archived, not a fork) before ingestion; the curated list stays
  the core.
- **History starts thin**: backfill gives 35 days immediately; longer windows grow with daily
  refreshes, and periods without coverage are labelled honestly.
