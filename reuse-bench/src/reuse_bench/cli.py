"""Command-line entry point: `reuse-bench <command>`."""

from __future__ import annotations

import argparse
from pathlib import Path

from reuse_bench import __version__


def _cmd_validate(args: argparse.Namespace) -> int:
    from reuse_bench.validation import validate_all

    report = validate_all(args.root, allow_few=args.allow_few)
    for err in report.errors:
        print(f"ERROR: {err}")
    for warning in report.warnings:
        print(f"WARNING: {warning}")
    print(report.summary())
    return 1 if report.errors else 0


def _cmd_splits(args: argparse.Namespace) -> int:
    from reuse_bench.loading import load_cases
    from reuse_bench.splits import assign_splits

    cases = [case for _, case in load_cases(args.root / "cases")]
    splits = assign_splits(cases)
    if not splits:
        print("no real cases yet (example fixtures never get a split)")
        return 0
    for case in cases:
        if case.id in splits:
            print(f"{case.id}  {case.kind}  {splits[case.id]}")
    return 0


def make_adapter(name: str):
    if name == "claude_code":
        from reuse_bench.adapters.claude_code import ClaudeCodeAdapter

        return ClaudeCodeAdapter()
    raise ValueError(f"unknown agent '{name}'")


def _select_cases(args: argparse.Namespace, cases: list) -> list | None:
    selected = [c for c in cases if args.include_examples or not c[1].example]
    if args.cases:
        wanted = [i.strip() for i in args.cases.split(",") if i.strip()]
        known = {c[1].id for c in selected}
        unknown = [i for i in wanted if i not in known]
        if unknown:
            print(f"ERROR: unknown or excluded case ids: {', '.join(unknown)}")
            return None
        selected = [c for c in selected if c[1].id in wanted]
    return selected


def _cmd_run(args: argparse.Namespace, pilot: bool = False) -> int:
    from reuse_bench.loading import load_cases, load_conditions
    from reuse_bench.runner import find_repo_root, pilot_summary, plan_matrix, run_matrix
    from reuse_bench.schema import Limits
    from reuse_bench.validation import validate_all

    report = validate_all(args.root, allow_few=True)
    if report.errors:
        for err in report.errors:
            print(f"ERROR: {err}")
        print("Fix the errors above before running.")
        return 1

    all_cases = load_cases(args.root / "cases")
    cases = _select_cases(args, all_cases)
    if cases is None:
        return 1
    if not cases:
        print(
            "There are no real cases to run. Add cases, or pass --include-examples for a smoke run."
        )
        return 1
    if pilot and not args.cases:
        cases = cases[:3]

    conditions = load_conditions(args.root / "conditions")
    if args.conditions:
        wanted = {i.strip().upper() for i in args.conditions.split(",")}
        conditions = [c for c in conditions if c[1].id in wanted]
    repeats = 1 if pilot else args.repeats
    planned = plan_matrix(cases, conditions, repeats=repeats, seed=args.seed, pilot=pilot)
    limits = Limits(
        max_turns=args.max_turns,
        timeout_s=args.timeout,
        model=args.model,
        permission_mode=args.permission_mode,
    )
    print(f"Starting {len(planned)} agent runs. Each one uses your agent login and allowance.")
    metas = run_matrix(
        planned,
        make_adapter(args.agent),
        limits,
        args.root,
        args.root / "runs",
        find_repo_root(args.root),
        force=args.force,
    )
    failed = [m for m in metas if m.exit_status == "failed"]
    truncated = [m for m in metas if m.exit_status == "truncated"]
    print(
        f"{len(metas)} runs recorded under runs/; {len(truncated)} truncated (scored), "
        f"{len(failed)} failed (excluded)."
    )
    for meta in truncated:
        print(f"  truncated: {meta.run_id}: {meta.failure_reason}")
    for meta in failed:
        print(f"  failed: {meta.run_id}: {meta.failure_reason}")
    if pilot:
        real_cases = [c for c in all_cases if not c[1].example] or cases
        available = sum(1 for _, c in conditions if c.available)
        print(pilot_summary(metas, full_runs=len(real_cases) * available * 2))
    return 0


def _cases_by_id(root: Path) -> dict:
    from reuse_bench.loading import load_cases

    return {case.id: case for _, case in load_cases(root / "cases")}


def _cmd_score(args: argparse.Namespace) -> int:
    from collections import Counter

    from reuse_bench.runner import finished_run_dirs, load_meta
    from reuse_bench.scoring import score_run

    cases = _cases_by_id(args.root)
    counts: Counter[str] = Counter()
    for run_dir in finished_run_dirs(args.root / "runs"):
        case_id = load_meta(run_dir).case_id
        case = cases.get(case_id)
        if case is None:
            print(f"WARNING: {run_dir.name}: case '{case_id}' not found; skipped")
            continue
        score = score_run(run_dir, case, args.root)
        (run_dir / "auto_score.json").write_text(score.model_dump_json(indent=2), encoding="utf-8")
        counts[score.label] += 1
    for label in sorted(counts):
        print(f"{label}: {counts[label]}")
    print(f"{sum(counts.values())} runs scored.")
    return 0


def _cmd_export_judging(args: argparse.Namespace) -> int:
    from reuse_bench.judging import JudgingError, default_paths, export_judging

    out_csv, key_path, _ = default_paths(args.root)
    out_csv = args.out or out_csv
    try:
        n = export_judging(
            args.root, args.seed, out_csv, key_path, include_examples=args.include_examples
        )
    except JudgingError as exc:
        print(f"ERROR: {exc}")
        return 1
    if n == 0:
        print("Nothing to judge: no scored run needs human judging. No files were written.")
        return 0
    print(f"{n} rows written to {out_csv}. Give each judge a copy; keep {key_path} private.")
    return 0


def _cmd_import_judgments(args: argparse.Namespace) -> int:
    from reuse_bench.judging import JudgingError, default_paths, import_judgments

    _, key_path, store_dir = default_paths(args.root)
    if not key_path.exists():
        print(f"ERROR: {key_path} not found; run export-judging first")
        return 1
    try:
        n = import_judgments(args.csv, args.judge, key_path, store_dir)
    except JudgingError as exc:
        print(f"ERROR: {exc}")
        return 1
    print(f"{n} judgments stored for {args.judge}.")
    return 0


def _cmd_report(args: argparse.Namespace) -> int:
    from datetime import date

    from reuse_bench.report import build_report

    if args.include_examples and args.out is None:
        print("ERROR: example data never goes to results/; pass --out PATH for a smoke report")
        return 1
    today = date.today()
    out = args.out or args.root / "results" / f"{today.isoformat()}-report.md"
    text = build_report(args.root, today, include_examples=args.include_examples)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")
    gate_line = next((line for line in text.splitlines() if line.startswith("Gate:")), "")
    print(f"Report written to {out}")
    print(gate_line)
    return 0


def _cmd_check_runs(args: argparse.Namespace) -> int:
    from reuse_bench.checks import check_runs

    results = check_runs(args.root / "runs", pilot_only=args.pilot)
    if not results:
        print("No runs found under runs/.")
        return 1
    for result in results:
        if result.problems:
            for problem in result.problems:
                print(f"PROBLEM {result.run_id}: {problem}")
        else:
            print(f"OK      {result.run_id}")
        for note in result.notes:
            print(f"        {note}")
    bad = sum(1 for r in results if r.problems)
    print(f"{len(results)} runs checked; {bad} with problems.")
    return 1 if bad else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="reuse-bench",
        description="Measure whether a coding agent surfaces existing open-source tools "
        "before writing custom code.",
    )
    parser.add_argument("--version", action="version", version=f"reuse-bench {__version__}")
    sub = parser.add_subparsers(dest="command")

    root_opts = argparse.ArgumentParser(add_help=False)
    root_opts.add_argument(
        "--root", type=Path, default=Path.cwd(), help="reuse-bench directory (default: cwd)"
    )

    validate = sub.add_parser("validate", parents=[root_opts], help="validate cases")
    validate.add_argument(
        "--allow-few", action="store_true", help="no warning below the target case counts"
    )
    validate.set_defaults(handler=_cmd_validate)

    splits = sub.add_parser("splits", parents=[root_opts], help="show dev/holdout assignment")
    splits.set_defaults(handler=_cmd_splits)

    from reuse_bench.runner import DEFAULT_REPEATS, DEFAULT_SEED

    run_opts = argparse.ArgumentParser(add_help=False)
    run_opts.add_argument("--cases", help="comma-separated case ids (default: all real cases)")
    run_opts.add_argument("--conditions", help="comma-separated condition ids (default: all)")
    run_opts.add_argument("--seed", type=int, default=DEFAULT_SEED, help="condition order seed")
    run_opts.add_argument("--max-turns", type=int, default=30)
    run_opts.add_argument("--timeout", type=int, default=900, help="seconds per run")
    run_opts.add_argument("--model", default=None, help="agent model (default: agent default)")
    run_opts.add_argument("--agent", default="claude_code")
    run_opts.add_argument(
        "--permission-mode",
        default="auto",
        choices=["auto", "dontAsk", "acceptEdits", "default"],
        help="agent permission mode, the same for every condition (default: auto)",
    )
    run_opts.add_argument("--force", action="store_true", help="repeat finished runs")
    run_opts.add_argument(
        "--include-examples", action="store_true", help="also run example fixtures (smoke test)"
    )

    run = sub.add_parser("run", parents=[root_opts, run_opts], help="run the full matrix")
    run.add_argument("--repeats", type=int, default=DEFAULT_REPEATS)
    run.set_defaults(handler=_cmd_run)

    pilot = sub.add_parser(
        "pilot", parents=[root_opts, run_opts], help="3 cases x conditions x 1 repeat, with cost"
    )
    pilot.set_defaults(handler=lambda args: _cmd_run(args, pilot=True))

    score = sub.add_parser("score", parents=[root_opts], help="automatic first-pass labels")
    score.set_defaults(handler=_cmd_score)

    export = sub.add_parser(
        "export-judging", parents=[root_opts], help="blind CSV of runs for human judging"
    )
    export.add_argument("--seed", type=int, default=DEFAULT_SEED, help="row order seed")
    export.add_argument("--out", type=Path, default=None, help="CSV path")
    export.add_argument("--include-examples", action="store_true", help="smoke test only")
    export.set_defaults(handler=_cmd_export_judging)

    imp = sub.add_parser(
        "import-judgments", parents=[root_opts], help="validate and store one judge's CSV"
    )
    imp.add_argument("csv", type=Path)
    imp.add_argument("--judge", required=True, help="judge code, e.g. j01")
    imp.set_defaults(handler=_cmd_import_judgments)

    report = sub.add_parser("report", parents=[root_opts], help="write the report and gate")
    report.add_argument("--out", type=Path, default=None, help="default: results/<date>-report.md")
    report.add_argument(
        "--include-examples", action="store_true", help="smoke test only; requires --out"
    )
    report.set_defaults(handler=_cmd_report)

    check = sub.add_parser(
        "check-runs", parents=[root_opts], help="verify run records after a real run"
    )
    check.add_argument("--pilot", action="store_true", help="only check pilot runs")
    check.set_defaults(handler=_cmd_check_runs)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:  # argparse exits for --help / --version / usage errors
        return int(exc.code or 0)
    if args.command is None:
        parser.print_help()
        return 0
    return int(args.handler(args) or 0)
