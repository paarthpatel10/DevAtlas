"""Command-line entry point: `reuse-bench <command>`."""

from __future__ import annotations

import argparse

from reuse_bench import __version__


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="reuse-bench",
        description="Measure whether a coding agent surfaces existing open-source tools "
        "before writing custom code.",
    )
    parser.add_argument("--version", action="version", version=f"reuse-bench {__version__}")
    parser.add_subparsers(dest="command")
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
    handler = getattr(args, "handler", None)
    if handler is None:
        parser.print_help()
        return 2
    return int(handler(args) or 0)
