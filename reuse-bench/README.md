# reuse-bench

A small benchmark harness that measures one thing:

> When a developer asks a coding agent to build a feature that a maintained open-source tool
> already provides, how often does the agent surface that tool before writing custom code?
> And do cheap fixes (one instruction line, or an existing MCP server) already close the gap?

Specification: [`docs/superpowers/specs/2026-11-12-reuse-benchmark-pivot.md`](../docs/superpowers/specs/2026-11-12-reuse-benchmark-pivot.md).
Implementation plan: [`docs/superpowers/plans/2026-11-12-reuse-benchmark.md`](../docs/superpowers/plans/2026-11-12-reuse-benchmark.md).

## Status

Milestone B1: case and condition format, validation and splits. Runner, scoring and report land
in B2 to B4.

## Adding a case

1. Copy `cases/_template.yaml` to `cases/<id>.yaml` and fill it in. An optional starter project
   goes in `workspaces/<id>/`; without one, a minimal Python project is generated.
2. Run `uv run reuse-bench validate`. It fails when:
   - the YAML does not match the schema (a reuse case needs an accepted tool, a control case
     must have none);
   - an example fixture is outside `cases/examples/`, or a real case is inside it;
   - an id is duplicated, or the workspace is missing or outside `workspaces/`;
   - the `request`, the `context` or any workspace file names an accepted tool, package or import
     name (case-insensitive, also with `-`, `_` and `.` swapped).
3. `uv run reuse-bench splits` shows the dev/holdout split. It is assigned deterministically from
   the case id and a fixed seed, stratified by kind, and never set by hand.

## How it works (planned)

1. **Cases** (`cases/*.yaml`): real "should have reused" situations plus control cases where
   custom code is the right answer. Cases come from the owner and colleagues; nothing is invented.
   Files under `cases/examples/` are test fixtures (`example: true`) and are excluded from every
   count, rate and report.
2. **Conditions** (`conditions/*.yaml`): A baseline, B one fixed instruction line, C an existing
   "check before you build" MCP server.
3. **Runner**: runs every case under every condition in an isolated temporary git workspace and
   stores a complete run record under `runs/` (git-ignored).
4. **Scoring**: automatic first-pass labels, then blind judging by two people.
5. **Report**: counts and rates per condition, and the decision gate.

## Run it

```powershell
cd reuse-bench
$env:UV_SYSTEM_CERTS = "1"   # only on networks that intercept TLS
uv sync
uv run reuse-bench --version
uv run ruff check . ; uv run pytest -q
```

Needs no database, no API keys and no DevAtlas backend.

## Privacy

- Cases must not contain proprietary code, company names or people's names.
- Contributors are identified by code (`c01`); the name mapping is kept outside the repository.
- Raw transcripts, diffs and run metadata live in `runs/`, which is git-ignored.
  Only sanitized summaries and reports go to `results/`.
- CI and tests never run a real agent. Real runs are started by the owner.

## Limitations

Small sample, one agent (Claude Code), one ecosystem (Python), cases from one social circle,
and judges who know the owner. Rates are reported with counts and make no claim of
statistical significance.
