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
