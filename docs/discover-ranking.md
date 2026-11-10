# Discover: ranking methodology

The Discover page answers "what is worth my attention?" with five feeds. Every placement
stores the numbers that caused it, and the UI shows them. Scores only order items inside a
feed; they are never shown, and they do not measure quality or production readiness.

Parameters live in [`backend/data/discover_ranking.yaml`](../backend/data/discover_ranking.yaml);
the logic is in [`backend/app/services/discover_ranking.py`](../backend/app/services/discover_ranking.py)
and is unit-tested in `backend/tests/unit/test_discover_ranking.py`.

## Data behind the feeds

| Signal | Source | Notes |
|--------|--------|-------|
| Stars, forks, open issues, last push, license | GitHub REST metadata | Refreshed daily; each refresh stores a dated snapshot. |
| Stars gained per day | GitHub GraphQL stargazers (newest first) | Needs a token that may list stargazers. Fine-grained tokens are refused; a classic token with no scopes works. Without it, star growth comes from daily snapshots only. |
| Forks per day | GitHub GraphQL forks (newest first) | |
| Commits per day | GitHub REST `/stats/commit_activity` | GitHub computes it lazily; if it isn't ready, commits are unknown, not zero. |
| Releases | GitHub GraphQL releases (20 most recent) | First release is known only when fewer than 20 releases exist. |
| README completeness | Indexed README | 0–1: install section 0.25, usage/example section 0.25, feature list with 3+ bullets 0.2, ≥1,500 characters 0.15, a code block 0.15. |

### Growth windows (honest by construction)

`growth(metric, days)` returns a value only when it is measured:

1. **Events**: per-day counts cover the whole window (coverage start ≤ window start) → sum.
   If any day hit the page cap, the value is a lower bound and is shown as "≥".
2. **Snapshots**: otherwise, two metadata snapshots spanning the window (the older one taken
   on or one day before the window start) → difference.
3. Otherwise the value is **unknown** (`None`), never zero. Unknown values exclude a
   repository from growth-based ranking.

## Feeds

### Trending (today / this week / this month): from GitHub Trending
- Source: **github.com/trending**, GitHub's own daily ranking with its "stars today" count,
  recorded once a day by `scripts/track_github_trending.py` for the overall page and the
  language pages listed under `github_trending:` in the config.
- Only the daily view is fetched: github.com/robots.txt disallows `?since=` URLs (weekly and
  monthly views) for automated clients.
- **Today**: the latest recorded day, ordered by the stars GitHub reported that day (the
  highest value across the overall and language pages).
- **This week / this month**: our stored daily observations added up over 7 / 30 days:
  days on GitHub Trending and the stars GitHub reported on those days. Until the tracker has
  run for the whole window, the feed says how many days it is based on.
- Without any observations, Trending falls back to measured star growth when it exists;
  otherwise it is empty and says so. It never shows a "most starred" list.
- Repositories that appear on GitHub Trending and are not yet indexed are added through the
  GitHub API (README, report, category inferred from topics and description).

### Rising: repeatedly on GitHub Trending
Repositories on GitHub Trending on at least 2 different days in the last 7 (momentum rather
than a one-day spike), ordered by days on Trending, then stars reported. Needs at least 2
days of observations. Without GitHub Trending data, the star-growth rule below applies.

#### Star-growth rule (when history exists)
- Requires 30-day star growth; otherwise the feed reports `insufficient_history`.
- Growth ratio = stars gained in 30 days ÷ max(stars 30 days ago, 200).
- Eligible: ≥10 stars gained, commits in ≥3 of the last 4 weeks, and not among the 10 most
  starred repositories.
- ×1.25 when the 7-day daily rate beats the 30-day daily rate ("accelerating").

### New & recently discovered
Eligible if any of: created within 90 days; found by search discovery within 14 days
or on GitHub Trending (curated repositories never count as "newly discovered"); first release within 30 days.
Ordered by early traction (log-scaled stars per day of age, capped at 1) + README completeness,
so a small, well-documented project can outrank a large one.

### Hidden gems
Eligible when: stars below the 40th percentile **of the repository's own category** (linear
interpolation; no global star threshold), pushed within 90 days, a license, and README
completeness ≥ 0.6. Ordered by 0.6 × completeness + 0.4 × recency of the last push.

### This week's discoveries
Up to 10: at most 3 from each of Trending (growth-based only), Rising, New and Hidden gems,
at most 2 per category, no duplicates.

## Search discovery (`scripts/discover_new.py`)
GitHub search per category (topics in the `search:` config) for repositories created in the
last 120 days with ≥20 stars, then filtered: not a fork, not archived, has a license and a
description, not a profile README (`owner/owner`), ≤25,000 stars (very high counts on young
repositories are often star farming; real breakouts can be curated), and README completeness
≥ 0.5. At most 5 per category per run.

## What is and isn't AI-generated
- **Measured, never generated**: every feed placement, every "+N stars", release and activity
  line, and the "why it's trending" signals.
- **AI-generated (Gemini), grounded**: the repository report (what it is, problem, why it is
  notable, who should care, use cases, build ideas, technical overview, limitations). Every
  item must cite README/metadata excerpts that were in the prompt; uncited items are dropped.
  Reports name the model and date, and are flagged stale when the README changes.
- Repository text is treated as untrusted input: it is wrapped as quoted sources, escaped,
  and the model is told never to follow instructions inside it.

## Running it
Suggested daily order: `track_github_trending` → `refresh_repositories` → `compute_feeds` → `generate_insights`.
`discover_new` and `backfill_history` can run weekly. All jobs are idempotent and resumable.
