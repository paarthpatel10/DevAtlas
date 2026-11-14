# reuse-bench

A small benchmark harness that measures one thing:

> When a developer asks a coding agent to build a feature that a maintained open-source tool
> already provides, how often does the agent surface that tool before writing custom code?
> And do cheap fixes (one instruction line, or an existing MCP server) already close the gap?

Specification: [`docs/superpowers/specs/2026-11-12-reuse-benchmark-pivot.md`](../docs/superpowers/specs/2026-11-12-reuse-benchmark-pivot.md).
Implementation plan: [`docs/superpowers/plans/2026-11-12-reuse-benchmark.md`](../docs/superpowers/plans/2026-11-12-reuse-benchmark.md).

## Status

Phase 1 (milestones B0 to B4) is built: case format, validation, splits, runner, Claude Code
adapter, pilot, scoring, blind judging, report and gate. No real cases or results exist yet.

## Full workflow

```powershell
uv run reuse-bench validate                       # cases are well-formed and leak nothing
uv run reuse-bench pilot                          # 3 cases; approve the projected time and cost
uv run reuse-bench check-runs --pilot             # every run complete, condition C tool connected
uv run reuse-bench run                            # full matrix (cases x A/B/C x 2 repeats)
uv run reuse-bench check-runs                     # same checks for the full run
uv run reuse-bench score                          # automatic first-pass labels
uv run reuse-bench export-judging                 # runs/judging/judging.csv, condition hidden
uv run reuse-bench import-judgments j01.csv --judge j01
uv run reuse-bench import-judgments j02.csv --judge j02
uv run reuse-bench report                         # results/<date>-report.md with the gate
```

## Owner checklist (spec section 12)

1. Fill in `case-001` from your own incident (`cases/_template.yaml`).
2. Send the intake questions (spec section 12) to 5 to 10 colleagues; aim for 2 cases each.
3. Review every case for private information before committing it.
4. Run the pilot, approve the cost projection, then start the full run.
5. Find two judges. Give each a copy of `runs/judging/judging.csv` and import each filled copy
   with their own judge code (`j01`, `j02`). Keep `runs/judging/key.json` private.
6. Read the report and decide: stop, narrow or continue. The harness only prints the gate.

## Scoring, judging and the report

- `score` labels each run `adopted_accepted`, `adopted_other`, `mentioned_then_custom`,
  `custom_no_mention` or `failed`. It uses manifest changes, install commands, new third-party
  imports, and accepted-tool names in the agent's text before its first code edit. "I will not
  use X" and similar negated mentions are not counted. Every label except `adopted_accepted` and
  `failed` goes to human judging.
- `export-judging` shuffles the rows, replaces run ids with opaque codes, hides the condition,
  and masks text that would reveal it (the condition B instruction, `CLAUDE.md`, and the
  condition C tool, server and tool ids). Paraphrased references cannot be masked.
- Judges answer `suitable_tool_surfaced` and `tool_adopted` (reuse cases) or
  `unneeded_dependency` (control cases) with yes or no. Rows where the two judges differ are
  `disputed` and listed separately; the harness does not resolve them.
- `report` averages per case first, then across cases, prints counts next to every rate, and
  marks rates based on fewer than 10 cases as "too few cases to read". Gate on the best of B and
  C: 80% or more is STOP PRODUCT, 50% or less is CONTINUE, in between is NARROW. A condition
  whose control accuracy is below 75% is flagged as over-recommending.
- The report also shows completed, truncated and failed run counts per condition, and how many
  condition C runs actually called the condition C tool, with the total number of calls.

## Adding a case

1. Copy `cases/_template.yaml` to `cases/<id>.yaml` and fill it in. An optional starter project
   goes in `workspaces/<id>/`; without one, a minimal Python project is generated.
2. Run `uv run reuse-bench validate`. It fails when:
   - the YAML does not match the schema (a reuse case needs an accepted tool, a control case
     must have none);
   - an example fixture is outside `cases/examples/`, or a real case is inside it;
   - an id is duplicated, or the workspace is missing or outside `workspaces/`;
   - the `request`, the `context` or any workspace file names an accepted tool, package or import
     name (case-insensitive, also with `-`, `_` and `.` swapped);
   - the `request` starts with `-` (the agent's command line would read it as an option).
4. After a real run, `uv run reuse-bench check-runs` reports per run: problems (incomplete or
   failed run, missing files, agent never started, condition C server not connected, condition
   C tool calls denied) and notes (truncated, other denied tools, condition C tool calls).
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

## Running the agent (owner only)

Real runs use your Claude Code login and usage allowance. Tests and CI never start them.

```powershell
uv run reuse-bench pilot            # 3 real cases x every available condition x 1 repeat
uv run reuse-bench run              # full matrix, 2 repeats (default)
uv run reuse-bench run --cases case-001 --conditions A,B --repeats 1
uv run reuse-bench pilot --include-examples   # smoke test on the fixtures (never counted)
```

- `pilot` prints time, cost and turns per run, plus the projected total for the full matrix.
  Approve that projection before starting `run`. The cost figure is the CLI's API-equivalent
  `total_cost_usd`, which does not map one-to-one to a subscription allowance.
- Runs are resumable. A run with a `meta.json` is never repeated unless you pass `--force`;
  a half-written run directory (interrupted harness) is redone. Neither kind of run below is
  repeated automatically:
  - **truncated**: the run hit the turn cap or the time limit but left a usable transcript (at
    least one assistant message with text or a tool call). It is scored and counted like a
    completed run.
  - **failed**: crashes, login or API errors, no result, or a turn cap or time limit with no
    usable transcript. Failed runs are excluded from the rates.
- Pick cases with `--cases`. Example fixtures need `--include-examples` as well; their runs are
  never counted in the report. Example:
  `uv run reuse-bench pilot --include-examples --cases case-002,example-http-retries,example-nl-dates`
- Condition order is shuffled per case and repeat with a recorded seed (`--seed`, default
  20261112). All conditions of a case run back to back.
- Defaults: 30 turns and 900 seconds per run (`--max-turns`, `--timeout`).

Each run writes `runs/<run_id>/` (`<case>--<condition>--r<repeat>`, with the prefix `pilot--` for
pilot runs): `meta.json` (case and condition hashes, repeat, seed and position, agent version,
model, times, limits, exit status, isolation notes, cost, harness commit), `events.jsonl`,
`final_message.txt`, `diff.patch`, `manifest_before/` and `manifest_after/`.

### Isolation (Claude Code 2.1.322)

Each run happens in a fresh temporary git repository outside this repository, containing only the
case workspace (or a generated minimal project). Case files and ground truth are never copied in.
For condition B, the fixed instruction is written to the workspace `CLAUDE.md` and committed
before the run, so the diff shows only the agent's changes.

The agent runs as:

```
claude -p <request> --output-format stream-json --verbose --max-turns 30 --no-session-persistence
  --permission-mode auto --allowedTools <same list for every condition>
  --setting-sources project --strict-mcp-config --mcp-config <condition MCP servers>
  --disable-slash-commands --settings {"claudeMdExcludes": ["~/.claude/CLAUDE.md", "~/.claude/rules/**"]}
env: CLAUDE_CODE_DISABLE_AUTO_MEMORY=1; variables whose names look secret (KEY, TOKEN, SECRET,
     PASSWORD, PWD, CREDENTIAL, neon_*, gemini*) and every CLAUDE* variable of a parent session
     or IDE terminal (IDE connection port, session ids, effort) are removed, except
     CLAUDE_CODE_OAUTH_TOKEN
```

This keeps your login but skips user-level settings, hooks, MCP servers, skills and slash
commands, personal CLAUDE.md files and rules, and auto memory. It was verified empirically on
2026-11-12. `--bare` was rejected because it needs an API key, and `--safe-mode` because it
ignores `--mcp-config`. What stays active is recorded in every `meta.json` under `isolation`:
org-managed plugins (on the owner's machine: `cc-plugin-sec-default`, `cc-plugin-agents-md`,
`cc-plugin-telemetry`, `cc-plugin-privacy`, `cc-plugin-plugin-authoring`), the tool list, the
connected MCP servers, and any `CLAUDE.md` found in a parent directory of the temp workspace.

Permissions are the same for every condition. Runs use auto mode (`--permission-mode auto`,
overridable with `--permission-mode`). The allowlist pre-approves Read, Edit, Write, Glob, Grep,
WebSearch, WebFetch, and Bash/PowerShell commands starting with uv, pip, pip3, python, python3,
py, pytest, git status and git diff. Anything else goes to auto mode's classifier, which approves
safe actions (installing packages, running tests, reading files) and blocks risky ones; the run
carries on after a block. Condition C adds only its own MCP tools. Blocked actions are recorded in
`meta.json` (`permission_denials`), and `check-runs` flags any run whose actual permission mode
differs from the requested one (for example if auto mode is not available on the account).
Auto mode was chosen after a smoke run in `dontAsk` mode blocked package installs and tests that
a developer would normally approve.

### Condition C tool

`skills-but-for-dev` 0.2.0 (Apache-2.0), run with `uvx skills-but-for-dev`, exactly as its README
configures it. It was the first candidate that ran cleanly on the owner's Windows machine:
`mtb` needs Go (not installed), and IndieStack 1.20.0 fails to start as its README instructs
(its unpinned `mcp` dependency now resolves to 2.x). On a network that intercepts TLS, set
`$env:UV_SYSTEM_CERTS = "1"` before running so `uvx` can download it. The tool may use your
GitHub CLI login (`gh auth token`) for GitHub rate limits.

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
