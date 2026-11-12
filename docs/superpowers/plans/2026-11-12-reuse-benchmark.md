# Reuse Benchmark (`reuse-bench`) Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (owner asked for inline work, no subagents) to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `reuse-bench`, a self-contained harness that measures whether a coding agent surfaces an existing open-source tool before writing custom code. It covers milestones B0–B4 and stops there.

**Architecture:** `reuse-bench` is a separate uv package at the repo root. It does not import the DevAtlas backend and needs no database or keys. YAML cases and conditions are validated by Pydantic models. A runner executes the case × condition × repeat matrix through an `AgentAdapter`; the only real adapter is Claude Code, run headless in an isolated temp git workspace. Run records go to the git-ignored `runs/`. Scoring, blind judging and the report then read only `runs/`, `cases/` and `conditions/`.

**Tech Stack:** Python 3.12, uv 0.12.5 (`uv_build` backend), Pydantic v2, PyYAML, argparse, pytest, ruff, git 2.49, Claude Code CLI 2.1.322.

**Spec:** `docs/superpowers/specs/2026-11-12-reuse-benchmark-pivot.md` (copy of `docs/2026-11-12-reuse-benchmark-pivot-spec.md`). Background only: `docs/devatlas_brainstorming_brief.md`, `docs/open_source_engineering_intelligence_strategy.md`.

## Global Constraints

- Nothing fabricated. No real cases, ground truth, run results, judgments or results are written by Claude Code. Invented cases exist only as fixtures with `example: true` and are excluded from every count, rate and report.
- No secrets in the repo, in run records or in logs. The harness never reads `.env`.
- Never run the real agent in tests or CI. Tests use `FakeAdapter`, and real runs are started by the owner.
- Frozen, so don't touch: Discover feeds, Compare, repository detail pages, Ask AI pages, and roadmap M2–M7. No file under `backend/` or `frontend/` changes.
- Phase 2 (condition D, the DevAtlas MCP server) is not started.
- Condition B text, verbatim and never edited: `Before implementing any non-trivial feature, first check whether a maintained open-source library or tool already provides it. If one fits this project's stack and license, propose it and use it instead of writing custom code. If none fits, say so briefly and build it.`
- Defaults: 30 turns, 900 s timeout, 2 repeats. The pilot is 3 cases × available conditions × 1 repeat.
- Gate on the best of B and C surfaced rate: ≥ 0.80 is `STOP PRODUCT`, ≤ 0.50 is `CONTINUE`, anything else is `NARROW`. Control accuracy < 0.75 is flagged "over-recommending". Fewer than 10 cases is flagged "too few cases to read".
- Missing values render as `Not available`.
- Windows first: use `pathlib`, write all file IO with `encoding="utf-8"`, decode subprocess output as UTF-8 with `errors="replace"`, and never use `shell=True`. Use `$env:UV_NATIVE_TLS=1` for uv.
- Every milestone gets its own branch and its own PR. Each PR passes `uv run ruff check . && uv run ruff format --check . && uv run pytest -q` inside `reuse-bench/`.
- Code style: ruff line-length 100 with lint rules `E,F,I,B,UP`, matching `backend/pyproject.toml`.

## Decisions taken from research (2026-11-12)

- **CLI:** Claude Code 2.1.322. The flags were checked against the headless docs, the CLI reference and `claude --help`.
- **Isolation (probe P6, verified empirically):**
  - Flags on every run:
    ```
    claude -p <request> --output-format stream-json --verbose --max-turns <n> --no-session-persistence
      --permission-mode dontAsk --allowedTools <list>
      --setting-sources project --strict-mcp-config --mcp-config <file> --disable-slash-commands
      --settings {"claudeMdExcludes": ["<home>/.claude/CLAUDE.md", "<home>/.claude/rules/**"]}
    ```
  - Child env: `CLAUDE_CODE_DISABLE_AUTO_MEMORY=1`.
  - The probe confirmed:
    - the workspace `CLAUDE.md` loads;
    - user rules are excluded;
    - the `--mcp-config` server connects;
    - 0 hooks fire and there are 0 slash commands;
    - the owner's OAuth login still works.
  - Still active and not removable: 5 org-managed plugins (`cc-plugin-sec-default`, `cc-plugin-agents-md`, `cc-plugin-telemetry`, `cc-plugin-privacy`, `cc-plugin-plugin-authoring`). These are recorded per run from the `system/init` event.
  - Ruled out:
    - `--bare` needs `ANTHROPIC_API_KEY`, and the owner has no API budget.
    - `--safe-mode` ignores `--mcp-config`, so it breaks condition C.
- **Permission mode:** `dontAsk` plus an explicit allowlist. It is deterministic, and any denied action shows up in the result's `permission_denials`. The allowlist is identical across conditions. The only addition is condition C's own MCP tools, which are part of that condition.
- **Condition C order:** `mtb` is skipped because it needs Go, which isn't installed (owner's decision 2026-11-12). Try IndieStack next, then skills-but-for-dev. If neither works, set `available: false` with the reason, run A and B only, and have the report say so.
- **Child env scrubbing:** env vars whose names match `KEY|TOKEN|SECRET|PASSWORD|PWD|CREDENTIAL` or start with `neon_`/`gemini` (case-insensitive) are removed from the agent's env. Only their *names* go into the isolation notes. This also keeps a stray `ANTHROPIC_API_KEY` from billing the API.
- **Split:** within each `kind`, cases are sorted by `sha256(f"{SPLIT_SEED}:{case_id}")`. Even positions are `dev` and odd positions are `holdout`. `SPLIT_SEED = "reuse-bench-2026-11-12"`. Example cases are never assigned a split.
- **Run id:** `<case_id>--<condition_id>--r<repeat>`, with the prefix `pilot--` for pilot runs. The report ignores `pilot--` runs.
- **Merging:** PRs are stacked, B(n+1) on B(n). The owner merges them.

## File Structure

```
reuse-bench/
  pyproject.toml  README.md  .gitignore (runs/, .pytest_tmp/)
  cases/_template.yaml
  cases/examples/example-http-retries.yaml  example-nl-dates.yaml  example-list-batches.yaml
  workspaces/.gitkeep
  conditions/a_baseline.yaml  b_instruction.yaml  c_external_tool.yaml
  results/.gitkeep
  src/reuse_bench/
    __init__.py
    logs.py         # JSON-lines logger to stderr
    schema.py       # all Pydantic models
    loading.py      # load cases/conditions, file hashes, minimal workspace generation
    validation.py   # leak checks, file-placement rules, summary counts
    splits.py       # dev/holdout assignment
    workspace.py    # temp workspace prep, git init/commit, diff, manifests, ancestor checks
    adapters/base.py  adapters/claude_code.py
    runner.py       # matrix, order, resume, pilot, run dir writing
    scoring.py      # auto labels
    judging.py      # export/import, agreement
    metrics.py      # per-case aggregation, rates, gate
    report.py       # markdown report
    cli.py          # argparse entry point `reuse-bench`
  tests/  (conftest.py, fakes.py, test_<module>.py)
```

---

## B0: Scaffold (branch `reuse-bench/b0-scaffold`)

### Task 1: Package scaffold, CI job, READMEs

**Files:**
- Create: `reuse-bench/pyproject.toml`, `reuse-bench/README.md`, `reuse-bench/.gitignore`, `reuse-bench/src/reuse_bench/__init__.py`, `reuse-bench/src/reuse_bench/cli.py`, `reuse-bench/tests/test_cli.py`, plus `.gitkeep` files in `cases/examples`, `workspaces`, `conditions` and `results`
- Modify: `.github/workflows/ci.yml` (add a `reuse-bench` job), `README.md` (pivot and freeze note under the title)
- Add: `docs/superpowers/specs/2026-11-12-reuse-benchmark-pivot.md`, and this plan

**Interfaces:**
- Produces: `reuse_bench.cli.main(argv: list[str] | None = None) -> int`, plus a console script `reuse-bench = "reuse_bench.cli:main"`. The subcommands are registered as tasks land; B0 has only `--version`.

- [ ] **Step 1:** Run `uv init --package --build-backend uv --name reuse-bench reuse-bench`, then `uv add pydantic pyyaml` and `uv add --dev pytest ruff`. Copy the ruff, pytest and `--basetemp=.pytest_tmp` settings from `backend/pyproject.toml`, and set `requires-python = ">=3.12"`.
- [ ] **Step 2:** Write the failing test `test_version_flag_prints_version`: `main(["--version"])` exits 0, and capsys shows `reuse-bench 0.1.0`.
- [ ] **Step 3:** Implement `main` with argparse and `version=f"reuse-bench {__version__}"`. Catch `SystemExit` so `--version` returns 0.
- [ ] **Step 4:** In `reuse-bench/`, run `uv run ruff check . && uv run ruff format --check . && uv run pytest -q`. Expected: 1 passed.
- [ ] **Step 5:** Write the README stub. It covers what the harness measures, the status (B0), how to run, privacy rules (`runs/` git-ignored, examples excluded) and the limitations list from spec §9.
- [ ] **Step 6:** Add the CI job `reuse-bench`. It mirrors the backend job with `working-directory: reuse-bench` and runs `uv sync --locked`, `ruff check`, `ruff format --check` and `pytest -q`. It has no secrets.
- [ ] **Step 7:** Add a short "Pivot (2026-11-12)" note to the root `README.md`. It says the website is frozen (Discover, Compare, repository pages, Ask AI, M2–M7), work moves to `reuse-bench/`, the trending tracker keeps running daily, and links the spec.
- [ ] **Step 8:** Run `git diff --stat main -- backend frontend`. Expected: empty. Commit, push, open the PR and check CI is green.

---

## B1: Cases, conditions, validation, splits (branch `reuse-bench/b1-cases`)

### Task 2: Schemas and loading

**Files:** Create `src/reuse_bench/schema.py`, `src/reuse_bench/loading.py`, `tests/test_schema.py`, `cases/_template.yaml`, `conditions/a_baseline.yaml`, `conditions/b_instruction.yaml`, `conditions/c_external_tool.yaml`

**Interfaces (produces):**
- `schema.py` (all models `extra="forbid"`):
  - `Stack(language: str, python_version: str | None = None, frameworks: list[str] = [])`
  - `AcceptedTool(name: str, packages: list[str], import_names: list[str], repo_url: str)`. `repo_url` must start with `https://`.
  - `GroundTruth(accepted_tools: list[AcceptedTool], rationale: str, found_how: Literal["searched","colleague","docs","assistant","other"])`
  - `Case`:
    - fields: `id`, `title`, `kind`, `example`, `contributor`, `consent_to_publish`, `date_observed`, `stack`, `context`, `request`, `workspace`, `ground_truth`, `notes`
    - `id`: `^[a-z0-9][a-z0-9-]*$`
    - `kind`: `Literal["reuse","control"]`
    - `contributor`: `^c\d{2,}$`
    - `date_observed`: `^\d{4}-(0[1-9]|1[0-2])$`
    - `workspace`: `str | None`
    - A model validator requires `reuse` cases to have at least one accepted tool and `control` cases to have none.
  - `ExternalTool(name: str, version: str, install_method: str, source_url: str)`
  - `Condition`:
    - fields: `id`, `name`, `description`, `project_instruction`, `mcp_servers`, `extra_allowed_tools`, `external_tool`, `available`, `unavailable_reason`
    - `id`: `Literal["A","B","C"]`
    - `project_instruction`: `str | None`
    - `mcp_servers`: `dict[str, dict]`
    - `extra_allowed_tools`: `list[str]`
    - `external_tool`: `ExternalTool | None`
    - `available`: `bool = True`
    - `unavailable_reason`: `str = ""`
  - `Limits`:
    - `max_turns: int = 30`
    - `timeout_s: int = 900`
    - `permission_mode: str = "dontAsk"`
    - `allowed_tools: list[str] = DEFAULT_ALLOWED_TOOLS`
    - `model: str | None = None`
  - `B_INSTRUCTION: str`, the verbatim condition B text.
  - Run, score and judgment models are added in Tasks 5, 8 and 9, all in this file.
- `loading.py`:
  - `file_sha256(path: Path) -> str`
  - `case_hash(case_path: Path, workspace_dir: Path | None) -> str`: sha256 over the YAML bytes plus the sorted relative paths and bytes of the workspace files.
  - `load_case(path: Path) -> Case`
  - `load_cases(cases_dir: Path) -> list[tuple[Path, Case]]`: recursive, skips names starting with `_`, sorted by id.
  - `load_conditions(dir: Path) -> list[tuple[Path, Condition]]`: sorted by id.
  - `minimal_workspace_files(case: Case) -> dict[str, str]`: returns `pyproject.toml` (name `app`, `requires-python = ">=<python_version or 3.12>"`, `dependencies = <frameworks>`) and `app/__init__.py` (empty).
  - `LoadError(Exception)`: the message names the file and the field.

- [ ] **Step 1:** Write the failing tests:
  - `test_reuse_case_requires_accepted_tool`
  - `test_control_case_rejects_accepted_tools`
  - `test_unknown_field_rejected`
  - `test_bad_date_observed_rejected` (`2026-13` and `2026-10-01` both fail)
  - `test_condition_b_text_is_verbatim`: loads `conditions/b_instruction.yaml` and asserts `project_instruction.strip() == B_INSTRUCTION`.
  - `test_case_hash_changes_when_workspace_file_changes`
  - `test_minimal_workspace_uses_stack`
- [ ] **Step 2:** Run `uv run pytest tests/test_schema.py -q`. Expected: FAIL on import.
- [ ] **Step 3:** Implement `schema.py` and `loading.py`. Write the YAML files:
  - `_template.yaml`: the spec §5 template with every field commented, and `date_observed` quoted.
  - A: no instruction, `mcp_servers: {}`.
  - B: `project_instruction` is `B_INSTRUCTION`, as a YAML block scalar.
  - C: `available: false`, `unavailable_reason: "Not yet selected; see Task 7"`.
- [ ] **Step 4:** Run `uv run pytest -q`. Expected: all pass.
- [ ] **Step 5:** Commit with `feat(reuse-bench): case and condition schemas`.

### Task 3: Validation (leaks, placement) and the `validate` command

**Files:** Create `src/reuse_bench/validation.py`, `tests/test_validation.py`, the three fixture YAMLs in `cases/examples/`. Modify `cli.py`.

**Interfaces:**
- Consumes: Task 2 loaders.
- Produces:
  - `leak_tokens(case: Case) -> set[str]`: the name, packages and import names, each also in `-`/`_`/`.`-swapped variants, lower-cased.
  - `find_leaks(case: Case, workspace_files: dict[str, str]) -> list[str]`:
    - Each message reads like `request mentions 'tenacity'` or `workspace file app/x.py mentions 'tenacity'`.
    - Matching is case-insensitive with token boundaries `(?<![A-Za-z0-9_])tok(?![A-Za-z0-9_])`.
  - `read_workspace_texts(dir: Path) -> tuple[dict[str, str], list[str]]`: returns the texts plus the skipped binary or undecodable files. It never crashes on binary files.
  - `validate_all(root: Path) -> ValidationReport(errors: list[str], warnings: list[str], real_reuse: int, real_control: int, examples: int)`.
  - Placement rules:
    - `example: true` only under `cases/examples/`, and a real case never there;
    - ids unique;
    - `workspace` path exists, relative, inside `workspaces/`.
  - CLI `reuse-bench validate [--root PATH]` prints `N real cases (X reuse, Y control); M example fixtures (excluded from counts)`. It exits 1 on any error.
  - Unless `--allow-few` is given, fewer than 15 real reuse or 4 real control cases is a warning, not an error.

- [ ] **Step 1:** Write the failing tests:
  - `test_examples_validate_clean`: `validate_all(project_root)` has no errors, `examples == 3`, `real_reuse == 0`.
  - `test_leak_in_request_fails`: a copy of the retry fixture whose request contains `Tenacity` gives an error naming `request` and `tenacity`.
  - `test_leak_variant_in_workspace_fails`: workspace file `import python_dateutil` against package `python-dateutil`.
  - `test_substring_is_not_a_leak`: the token `re` does not match `retry`.
  - `test_binary_workspace_file_skipped_not_crash`: a file with bytes `b"\x00\xff"` lands in the skipped list and causes no exception.
  - `test_example_outside_examples_dir_fails`
  - `test_cli_validate_exit_codes`: 0 on the repo, and 1 on a tmp root containing a leaked case.
- [ ] **Step 2:** Run the tests. Expected: FAIL.
- [ ] **Step 3:** Write the three fixtures. Each has `example: true`, `contributor: c00`, `consent_to_publish: false`, `notes: "Test fixture, not a benchmark case."`, and a generic request that names no library:
  - `example-http-retries` (reuse): candidates are tenacity, backoff and stamina.
  - `example-nl-dates` (reuse): candidates are dateparser and parsedatetime.
  - `example-list-batches` (control): stdlib `itertools.batched` on Python 3.12; `accepted_tools: []`.
  - **Before committing, verify each package and import name on PyPI, and each repo URL with an HTTP 200.** Record the verification in the PR body.
- [ ] **Step 4:** Implement `validation.py` and the CLI subcommand. Generated minimal workspaces are leak-checked too.
- [ ] **Step 5:** Run `uv run pytest -q` and `uv run reuse-bench validate`. Expected: all pass, and the CLI prints `0 real cases (0 reuse, 0 control); 3 example fixtures (excluded from counts)` plus the too-few warning.
- [ ] **Step 6:** Commit with `feat(reuse-bench): case validation with leak detection and fixtures`.

### Task 4: Split assignment

**Files:** Create `src/reuse_bench/splits.py`, `tests/test_splits.py`. Modify `cli.py`.

**Interfaces (produces):**
- `SPLIT_SEED = "reuse-bench-2026-11-12"`
- `assign_splits(cases: list[Case], seed: str = SPLIT_SEED) -> dict[str, Literal["dev","holdout"]]`: skips `example` cases and uses the algorithm under Decisions.
- CLI `reuse-bench splits` prints `id  kind  split`.

- [ ] **Step 1:** Write the failing tests, using `Case` objects built in-test with `example=True`:
  - `test_split_is_deterministic`
  - `test_split_is_stratified`: 6 reuse and 4 control give exactly 3/3 and 2/2.
  - `test_examples_get_no_split`: this calls the internal `_assign(ids_by_kind)`, so the fixtures stay examples.
  - `test_split_independent_of_input_order`
- [ ] **Step 2:** Run. Expected: FAIL. **Step 3:** Implement. **Step 4:** Run `uv run pytest -q`. Expected: PASS.
- [ ] **Step 5:** Commit, push, open the B1 PR and check CI is green.

---

## B2: Runner, adapter, isolation, pilot (branch `reuse-bench/b2-runner`)

### Task 5: Run models and adapter protocol

**Files:** Modify `schema.py`. Create `src/reuse_bench/adapters/__init__.py`, `adapters/base.py`, `tests/fakes.py`, `tests/test_adapter_base.py`.

**Interfaces (produces):**
- `schema.py`:
  - `RunStatus = Literal["completed","failed"]`
  - `RunRecord`, which the adapter returns:
    - `agent: str`
    - `agent_version: str | None`
    - `model: str | None`
    - `events: list[dict]`
    - `final_message: str`
    - `exit_status: RunStatus`
    - `failure_reason: str | None`
    - `cost_usd: float | None`
    - `usage: dict | None`
    - `num_turns: int | None`
    - `permission_denials: list[dict]`
    - `isolation: dict`
    - `started_at: datetime`
    - `ended_at: datetime`
  - `RunMeta`, written to `meta.json`. It holds every `RunRecord` field except `events` and `final_message`, plus:
    - `run_id`, `case_id`, `case_hash`, `condition_id`, `condition_hash`, `repeat`
    - `order_seed: int`, `order_position: int`
    - `limits: Limits`
    - `harness_commit: str | None`, `example: bool`, `pilot: bool`
- `adapters/base.py`:
  - `class AgentAdapter(Protocol)`:
    - `name: str`
    - `instruction_filename: str`
    - `def run(self, workspace_dir: Path, prompt: str, condition: Condition, limits: Limits) -> RunRecord`
- `tests/fakes.py`: `FakeAdapter(edits: dict[str,str] | Callable[[Path],None], events: list[dict], final_message="done", exit_status="completed", raise_exc: Exception | None = None)`. It records the `calls` it receives and writes the edits into the workspace.

- [ ] Steps: write the failing test `test_fake_adapter_satisfies_protocol` (`isinstance` check via `runtime_checkable`); run it and see it FAIL; implement; run it and see it PASS; commit.

### Task 6: Isolated workspace

**Files:** Create `src/reuse_bench/workspace.py`, `tests/test_workspace.py`.

**Interfaces (produces):**
- `MANIFEST_GLOBS = ("pyproject.toml", "requirements*.txt")`, at the workspace root only.
- `DIFF_EXCLUDES = (".venv/", "__pycache__/", "*.pyc", ".pytest_cache/", "uv.lock")`. These are written to `.git/info/exclude`, so they are invisible to the agent.
- `prepare_workspace(case: Case, case_root: Path, condition: Condition, instruction_filename: str, repo_root: Path) -> Path`:
  - creates `tempfile.mkdtemp(prefix="rb-")`;
  - raises `IsolationError` if the result is inside `repo_root`;
  - copies the case workspace, or writes `minimal_workspace_files`;
  - writes `condition.project_instruction` to `instruction_filename` when set;
  - runs `git init`, with local config `user.name=reuse-bench`, `user.email=reuse-bench@localhost`, `commit.gpgsign=false` and `core.autocrlf=false`;
  - stages and commits `start`;
  - never copies case YAML or ground truth.
- `ancestor_instruction_files(workspace: Path) -> list[str]`: any `CLAUDE.md`/`CLAUDE.local.md` found directly in an ancestor directory.
- `snapshot_manifests(workspace: Path, dest: Path) -> None`
- `final_diff(workspace: Path) -> str`: `git add -A` then `git diff --cached HEAD`.
- `remove_workspace(path: Path) -> None`: rmtree with a read-only handler for Windows `.git` files.

- [ ] **Step 1:** Write the failing tests:
  - `test_workspace_outside_repo_and_git_committed`
  - `test_case_yaml_and_ground_truth_never_copied`: no file in the workspace contains the accepted tool name or the string `ground_truth`.
  - `test_condition_b_writes_instruction_file_and_commits_it`: the diff after prepare is empty.
  - `test_condition_a_and_b_workspaces_differ_only_by_instruction_file`
  - `test_diff_includes_new_untracked_file_and_excludes_venv`
  - `test_manifest_snapshot_copies_requirements_variants`
  - `test_workspace_inside_repo_raises`: monkeypatch `tempfile.mkdtemp` so it returns a path inside `repo_root`.
- [ ] **Step 2:** Run and see FAIL. **Step 3:** Implement with `subprocess.run([...], check=True)` and no shell. **Step 4:** Run and see PASS. **Step 5:** Commit.

### Task 7: Claude Code adapter and condition C selection

**Files:** Create `src/reuse_bench/adapters/claude_code.py`, `tests/test_claude_code_adapter.py`, `tests/data/stream_ok.jsonl`, `tests/data/stream_truncated.jsonl`. Modify `conditions/c_external_tool.yaml`.

**Interfaces (produces):**
- `class ClaudeCodeAdapter`:
  - `name = "claude_code"`
  - `instruction_filename = "CLAUDE.md"`
  - `__init__(self, executable: str | None = None)`, which resolves `shutil.which("claude")` or `~/.local/bin/claude.exe`
  - `build_command(self, prompt: str, mcp_config_path: Path, limits: Limits, condition: Condition) -> list[str]`: the exact flags under Decisions. `--allowedTools` gets `limits.allowed_tools + condition.extra_allowed_tools`, and `--model` is added only when `limits.model` is set.
  - `child_env(self, base: Mapping[str,str]) -> tuple[dict[str,str], list[str]]`: returns the scrubbed env and the removed names.
  - `run(...)`:
    - writes the MCP config `{"mcpServers": condition.mcp_servers}` to a sibling temp file outside the workspace;
    - starts `Popen` with `cwd=workspace_dir`;
    - calls `communicate(timeout=limits.timeout_s)`;
    - on timeout, kills the process tree (`taskkill /T /F /PID` on win32, `os.killpg` elsewhere), collects partial output and sets `failure_reason="timeout"`.
- `parse_stream(stdout: str) -> ParsedStream(events, init, result)`. It skips non-JSON or truncated lines.
- `record_from_stream(...) -> RunRecord`:
  - `completed` only if the result subtype is `success` and `is_error` is false;
  - otherwise `failed`, with reason `max_turns`, `timeout`, `no_result: <stderr tail redacted, 300 chars>` or the result subtype;
  - `isolation` carries the flags used, `env_set`, `env_removed`, `active_plugins`, `mcp_servers`, the tool count, the slash command count, `claude_md_excludes` and `ancestor_instruction_files`.
- `agent_version()`: `claude --version`, or `None` on error.
- `DEFAULT_ALLOWED_TOOLS` (in `schema.py`): `Read, Edit, Write, Glob, Grep, WebSearch, WebFetch, Bash(uv *), Bash(pip *), Bash(python *), Bash(pytest *), Bash(git status*), Bash(git diff*)`. **Before finalizing, confirm the Bash rule syntax against the current permissions docs (Context7 or code.claude.com).**

- [ ] **Step 1:** Write the failing tests. The `claude` binary is never executed:
  - `test_build_command_has_isolation_flags`: asserts every Decisions flag, `dontAsk`, the turn cap and the `claudeMdExcludes` JSON.
  - `test_command_identical_for_a_and_b`: the same argv apart from the mcp-config path.
  - `test_child_env_scrubs_secrets`: `GITHUB_TOKEN`, `neon_db`, `gemini` and `ANTHROPIC_API_KEY` are removed; `PATH` stays; the auto-memory var is set; only names are returned.
  - `test_parse_stream_ok`: model, cost, turns, plugins and final message come from `stream_ok.jsonl`.
  - `test_truncated_stream_is_failed_not_crash`: a last line cut mid-JSON with no result event gives `failed`/`no_result`.
  - `test_max_turns_is_failed`
  - `test_missing_cost_is_none`
  - `test_run_timeout_kills_and_fails`: the executable is `sys.executable` running a sleep script via `executable` and `build_command` monkeypatched; `timeout_s=1` gives `failed` and `timeout`.
  - The fixture JSONL files are hand-written synthetic events in the documented stream-json shape. They aren't real transcripts.
- [ ] **Step 2:** Run and see FAIL. **Step 3:** Implement. **Step 4:** Run and see PASS. **Step 5:** Commit.
- [ ] **Step 6 (condition C, manual, on the owner's machine):**
  - Install IndieStack exactly as its README says. If it runs cleanly as an MCP server, fill in `c_external_tool.yaml`:
    - `mcp_servers` with the README's config translated to `--mcp-config` JSON;
    - `extra_allowed_tools: ["mcp__<server>"]`;
    - `external_tool` with the name, version, install method and source URL;
    - `available: true`.
  - Otherwise, try skills-but-for-dev the same way.
  - If neither works, keep `available: false`, record both failure reasons, and **tell the owner** before continuing.
  - Confirm the result with one probe: `system/init` shows the server `connected`. A probe is an agent run, so it needs the owner's approval, and it's a tool check, not a benchmark run.

### Task 8: Runner (matrix, order, resume) and pilot

**Files:** Create `src/reuse_bench/runner.py`, `src/reuse_bench/logs.py`, `tests/test_runner.py`. Modify `cli.py`.

**Interfaces:**
- Consumes: Tasks 2, 5, 6 and 7.
- Produces:
  - `logs.log(event: str, **fields) -> None`: writes one JSON line (`ts`, `event`, plus the fields) to stderr. The runner logs `run_start`, `run_skip`, `run_end` and `condition_unavailable`.
  - `run_id_for(case_id: str, condition_id: str, repeat: int, pilot: bool = False) -> str`
  - `condition_order(case_id: str, repeat: int, condition_ids: list[str], seed: int) -> list[str]`: `random.Random(f"{seed}:{case_id}:{repeat}").shuffle`.
  - `plan_matrix(cases, conditions, repeats: int, seed: int, pilot: bool) -> list[PlannedRun]`. It is case-major, then repeat, then shuffled conditions, and skips unavailable conditions with a logged notice.
  - `is_finished(run_dir: Path) -> bool`: true when `meta.json` exists and parses. A dir without `meta.json` is incomplete; it gets deleted and rerun.
  - `execute_run(planned, adapter, limits, root: Path, runs_dir: Path) -> RunMeta`. This:
    - prepares the workspace;
    - snapshots `manifest_before`;
    - calls `adapter.run`; any exception becomes `failed` with `failure_reason="harness: <type>"`;
    - writes `events.jsonl`, `final_message.txt`, `diff.patch` and `manifest_after`;
    - writes `meta.json` last, atomically (temp file then `replace`);
    - removes the workspace.
  - `run_matrix(..., force: bool) -> list[RunMeta]`
  - `pilot_summary(metas: list[RunMeta], full_runs: int) -> str`:
    - one row per run with the duration in seconds, the cost (or `Not available`) and the turns;
    - the mean duration and mean cost, each multiplied by `full_runs`;
    - a note that `total_cost_usd` is the CLI's API-equivalent figure, which may not match the owner's plan usage.
  - `harness_commit(root) -> str | None`: adds `+dirty` when the tree is dirty.
- CLI:
  - `reuse-bench run [--cases IDS] [--conditions A,B,C] [--repeats 2] [--seed 20261112] [--max-turns 30] [--timeout 900] [--model M] [--force] [--include-examples]`
  - `reuse-bench pilot [--cases IDS]`: the default is the first 3 real cases by id, with 1 repeat and `pilot--` ids. It prints `pilot_summary`, and `full_runs` = real cases × available conditions × 2.
  - Both refuse to start if `validate` has errors. Both refuse example cases unless `--include-examples` is given; those runs get `example: true`.

- [ ] **Step 1:** Write the failing tests, all using `FakeAdapter` and fixture cases with `--include-examples` semantics:
  - `test_run_writes_complete_record`: all 6 artifacts exist; the meta has both hashes, the seed, the position, the limits and the isolation; `diff.patch` contains the fake edit.
  - `test_order_is_seeded_and_recorded`
  - `test_resume_skips_finished_and_force_reruns`: FakeAdapter is called once, then 0 times, then once again with `force=True`.
  - `test_incomplete_dir_is_rerun`: a run dir with `events.jsonl` and no `meta.json` gets rerun.
  - `test_adapter_exception_becomes_failed_run`
  - `test_unavailable_condition_skipped_with_notice`
  - `test_pilot_projection_math`: two runs of 10 s/$0.10 and 30 s/$0.30 with `full_runs=60` project 1200 s and $12.00; a `None` cost prints `Not available`.
  - `test_meta_contains_no_secret_values`: a secret value set in env doesn't appear anywhere under `runs/`.
  - `test_no_examples_without_flag`
- [ ] **Step 2:** Run and see FAIL. **Step 3:** Implement. **Step 4:** Run `uv run pytest -q` and see PASS.
- [ ] **Step 5:** Update the README with the run and pilot commands and the isolation method (flags, scrubbed env, what stays active, the ancestor check). Commit, push, open the B2 PR and check CI is green.
- [ ] **Step 6 (owner):** Once real cases exist, the owner runs `uv run reuse-bench pilot` and approves the projection. Claude Code does not run it.

---

## B3: Scoring and judging (branch `reuse-bench/b3-scoring`)

### Task 9: Automatic first-pass labels

**Files:** Create `src/reuse_bench/scoring.py`, `tests/test_scoring.py`. Modify `schema.py` and `cli.py`.

**Interfaces (produces):**
- `AutoLabel = Literal["adopted_accepted","adopted_other","mentioned_then_custom","custom_no_mention","failed"]`
- `AutoScore(run_id, label: AutoLabel, added_packages: list[str], new_imports: list[str], install_commands: list[str], mentions: list[str], needs_judging: bool)`
- `normalize_pkg(name: str) -> str`: PEP 503, so lowercase with runs of `-_.` collapsed to `-`.
- `manifest_packages(dir: Path) -> set[str]`: reads `[project].dependencies`, `optional-dependencies` and `[dependency-groups]` (via `tomllib`) plus `requirements*.txt` lines. It strips version specifiers, extras, markers and comments.
- `install_packages(events) -> tuple[list[str], set[str]]`: Bash `tool_use` commands matching `uv add`, `uv pip install`, `pip install`, `pip3 install`, `python -m pip install` or `poetry add`.
- `new_imports(diff: str, local_names: set[str]) -> set[str]`: top-level modules from added `import`/`from` lines in `.py` files, minus `sys.stdlib_module_names` and the workspace's local modules.
- `first_edit_index(events) -> int | None`: the first `Edit`/`Write`/`MultiEdit`/`NotebookEdit` `tool_use` whose path isn't a manifest.
- `mentions_before_edit(events, tokens: set[str]) -> list[str]`:
  - It searches assistant text blocks before that index.
  - A mention is negated, and so not counted, when a cue in `NEGATION_CUES = (r"\bnot\b", r"n't\b", r"\bno\b", r"\bnever\b", r"\bwithout\b", r"\bavoid\b")` appears earlier in the same sentence. Sentences split on `[.!?\n]`.
- `score_run(run_dir: Path, case: Case) -> AutoScore`:
  - `failed` if the meta says so;
  - then accepted overlap gives `adopted_accepted`;
  - then any added third-party package or import gives `adopted_other`;
  - then a mention gives `mentioned_then_custom`;
  - else `custom_no_mention`.
  - `needs_judging = label not in {"adopted_accepted","failed"}`. Control cases are therefore always judged.
- CLI `reuse-bench score` writes `auto_score.json` per run. It is idempotent.

- [ ] **Step 1:** Write the failing tests. Each uses a synthetic run dir built in `tmp_path` from a fixture case:
  - `test_label_adopted_accepted_via_pyproject`
  - `test_label_adopted_accepted_via_import_only`
  - `test_label_adopted_accepted_via_requirements_dev_txt`
  - `test_label_adopted_other`
  - `test_label_mentioned_then_custom`: "tenacity already does this, but I'll write a small helper."
  - `test_negated_mention_not_counted`: "I will not use tenacity." gives `custom_no_mention`.
  - `test_mention_after_first_edit_not_counted`
  - `test_stdlib_and_local_imports_ignored`: `itertools` and the local `app` are ignored.
  - `test_pkg_name_normalization`: `Python_DateUtil` equals `python-dateutil`.
  - `test_failed_run_label`
  - `test_control_case_always_needs_judging`
- [ ] **Step 2:** Run and see FAIL. **Step 3:** Implement. **Step 4:** Run and see PASS. **Step 5:** Commit.

### Task 10: Blind judging export and import

**Files:** Create `src/reuse_bench/judging.py`, `tests/test_judging.py`. Modify `schema.py` and `cli.py`.

**Interfaces (produces):**
- `Judgment(code: str, judge: str, suitable_tool_surfaced: bool | None, tool_adopted: bool | None, unneeded_dependency: bool | None, comment: str)`. `judge` must match `^j\d{2,}$`.
- `JUDGING_COLUMNS`:
  - visible: `code`, `case_kind`, `context`, `request`, `rationale`, `agent_proposal`, `diff_summary`
  - for judges to fill: `suitable_tool_surfaced`, `tool_adopted`, `unneeded_dependency`, `comment`
- `export_judging(root: Path, seed: int, out_csv: Path, key_path: Path) -> int`:
  - It covers runs with `needs_judging`, excluding pilot and example runs.
  - Order is shuffled with the seed. Codes are `R` plus 6 random hex characters (`secrets.token_hex(3)`), unique.
  - `agent_proposal` is the pre-edit assistant text plus the final message, each capped at 1500 characters.
  - `diff_summary` lists files with +/- counts, added packages and new imports.
  - Fields that don't apply are pre-filled `n/a`. For a reuse case that's `unneeded_dependency`; for a control case it's `suitable_tool_surfaced` and `tool_adopted`.
  - `blind_text(text, condition_terms) -> str` replaces condition C's tool name, MCP server names and `mcp__` identifiers with `[tool]`. It is case-insensitive.
  - `csv_safe(cell) -> str` prefixes `'` when a cell starts with `= + - @`.
  - The CSV is written UTF-8 with a BOM, for Excel. The key file is `runs/judging/key.json` (`code → run_id`) and is git-ignored, since it lives under `runs/`.
- `import_judgments(csv_path: Path, judge: str, key_path: Path, store_dir: Path) -> int`:
  - It accepts a BOM, CRLF, and case or whitespace variants of `yes`/`no`.
  - Fields that apply are required to be yes or no. Fields that don't apply must be `n/a` or empty.
  - Unknown codes are an error.
  - It writes `store_dir/<judge>.json` and replaces any previous import by the same judge.
  - A third distinct judge is an error.
- `resolve(judgments_by_code) -> dict[str, Literal["agreed","disputed","pending"]]` plus the agreed values. Any field the two judges answer differently makes the row `disputed`.
- CLI:
  - `reuse-bench export-judging [--seed N] [--out runs/judging/judging.csv]`
  - `reuse-bench import-judgments CSV --judge j01`

- [ ] **Step 1:** Write the failing tests:
  - `test_export_hides_condition`: no column is named condition or run_id; no cell contains a run id, `--A--`, the B instruction text, or condition C's tool or server name.
  - `test_export_skips_adopted_accepted_failed_pilot_example`
  - `test_export_order_is_shuffled_and_codes_opaque`
  - `test_csv_injection_escaped`
  - `test_import_tolerates_bom_crlf_case`: `" YES "` parses as true.
  - `test_import_rejects_missing_required_and_unknown_code`
  - `test_reimport_same_judge_replaces`
  - `test_third_judge_rejected`
  - `test_disagreement_marked_disputed`
  - `test_single_judge_pending`
  - Real judgments are never fabricated: the tests write synthetic CSVs in `tmp_path` only.
- [ ] **Step 2:** Run and see FAIL. **Step 3:** Implement. **Step 4:** Run and see PASS. **Step 5:** Commit, push, open the B3 PR and check CI is green.

---

## B4: Metrics, report, gate (branch `reuse-bench/b4-report`)

### Task 11: Metrics and gate

**Files:** Create `src/reuse_bench/metrics.py`, `tests/test_metrics.py`.

**Interfaces (produces):**
- `RunOutcome(run_id, case_id, kind, condition_id, repeat, status: Literal["valid","failed","disputed","pending"], surfaced: bool | None, adopted: bool | None, no_unneeded_dep: bool | None, date: str)`:
  - `surfaced` is true for `adopted_accepted`, or when the agreed judgment is `suitable_tool_surfaced`.
  - `adopted` is true for `adopted_accepted`, or when the agreed judgment is `tool_adopted`.
  - `no_unneeded_dep` is the agreed `not unneeded_dependency`.
- `collect_outcomes(root: Path, include_examples: bool = False) -> list[RunOutcome]`: excludes pilot runs, and excludes examples unless the flag is set.
- `Rate(numerator: float, cases: int, value: float | None, too_few: bool)`, where `too_few = cases < 10`.
- `case_means(outcomes, field) -> dict[(condition_id, case_id), float]`: the mean over valid runs only.
- `condition_rates(outcomes) -> dict[str, dict[str, Rate]]`: for each condition, `surfaced` and `adopted` over reuse cases and `control_accuracy` over control cases. Cases are equally weighted.
- `Gate = Literal["STOP PRODUCT","CONTINUE","NARROW","Not available"]`
- `gate(rates) -> tuple[Gate, str | None, float | None]`: the best of B and C with a non-None surfaced rate. `value >= 0.80` is STOP, `value <= 0.50` is CONTINUE, anything else is NARROW. When neither B nor C has a value, it returns `Not available`.
- `over_recommending(rates) -> list[str]`: the conditions with control accuracy below 0.75.
- `format_count(rate: Rate) -> str`, for example `11.5 of 18 cases (64%)`, with the suffix `, too few cases to read` when appropriate. A missing value formats as `Not available`.

- [ ] **Step 1:** Write the failing tests:
  - `test_case_weighted_not_run_weighted`: case 1 has 2/2 surfaced and case 2 has 0/1 valid, so the rate is 0.5.
  - `test_failed_disputed_pending_excluded`
  - `test_gate_boundaries`: 0.80 gives STOP, 0.50 gives CONTINUE, 0.65 gives NARROW, and both missing gives Not available.
  - `test_gate_uses_best_of_b_and_c_ignoring_a`
  - `test_control_accuracy_flag_below_075`: 0.75 isn't flagged and 0.74 is.
  - `test_too_few_cases_flag`: 9 cases are flagged and 10 aren't.
  - `test_examples_excluded_by_default`
- [ ] **Step 2:** Run and see FAIL. **Step 3:** Implement. **Step 4:** Run and see PASS. **Step 5:** Commit.

### Task 12: Report

**Files:** Create `src/reuse_bench/report.py`, `tests/test_report.py`. Modify `cli.py` and `README.md`.

**Interfaces (produces):**
- `build_report(root: Path, today: date, include_examples: bool = False) -> str`. The sections, in order:
  1. Title.
  2. When `include_examples` is set, a banner: `EXAMPLE DATA - NOT A BENCHMARK RESULT`.
  3. **Run environment:**
     - distinct agent versions, models and harness commits;
     - the date range;
     - the isolation summary, including the union of active plugins and the scrubbed env names;
     - the condition C tool, or why it is unavailable.
  4. **Metrics by condition:** one row per condition with `format_count` for each of the three metrics, plus the over-recommending flags.
  5. **Per-case table:** one row per case with the surfaced fraction under each condition, and the run ids behind each cell. Run ids serve as evidence links (`runs/<id>`).
  6. **Disputed runs.**
  7. **Failed runs** with their reasons.
  8. **Pending runs.**
  9. **Cases whose conditions ran on different days.**
  10. **Limitations:** the fixed list from spec §9.
  11. **Gate:** for example `Gate: NARROW (best of B and C: C, 64%). The harness prints the gate; the owner decides.`
- CLI `reuse-bench report [--include-examples] [--out PATH]`:
  - The default output is `results/<YYYY-MM-DD>-report.md`.
  - With `--include-examples` it refuses to write into `results/` unless `--out` is given.

- [ ] **Step 1:** Write the failing tests. They build fixture runs in `tmp_path` from the example cases, with synthetic metas, auto scores and judgments:
  - `test_report_from_fixture_data_shows_counts_flags_and_gate`: the output contains `of 2 cases`, `too few cases to read`, `Gate:`, and the example banner.
  - `test_report_lists_disputed_and_failed`
  - `test_report_shows_not_available_for_missing_cost_and_c_unavailable`
  - `test_report_refuses_examples_into_results_dir`
  - `test_report_without_runs_says_no_runs`: an empty `runs/` doesn't crash, and the gate shows Not available.
- [ ] **Step 2:** Run and see FAIL. **Step 3:** Implement. **Step 4:** Run `uv run pytest -q`, `uv run ruff check .` and `uv run ruff format --check .`. Expected: all clean.
- [ ] **Step 5:** Update the README with the full workflow (validate → pilot → run → score → export-judging → import-judgments ×2 → report) and the owner checklist from spec §12. Commit, push, open the B4 PR and check CI is green.
- [ ] **Step 6:** Stop. Hand back to the owner with the PR links and the owner tasks from spec §12.

## Review Focus

1. **Binary or non-UTF-8 workspace files** (images, `.pyc`) in a case workspace. Validation should skip them with a warning, not crash. The test is in Task 3.
2. **A timed-out or crashed agent run with a truncated stream-json line.** The run should be recorded as `failed` with a reason, and `meta.json` should still be written. Tests are in Tasks 7 and 8.
3. **A harness interrupted mid-run (Ctrl+C or a reboot).** The half-written run dir should be redone on resume, not counted as finished. The test is `test_incomplete_dir_is_rerun`.
4. **A judge CSV round-tripped through Excel** (BOM, CRLF, `Yes`/`YES`, formula cells). It should import cleanly, and exported cells shouldn't execute as formulas. Tests are in Task 10.
5. **Secrets in the environment** (`GITHUB_TOKEN`, `neon_db`, `gemini`, `ANTHROPIC_API_KEY`). They should never reach the agent or any file under `runs/`. Tests are `test_child_env_scrubs_secrets` and `test_meta_contains_no_secret_values`.
