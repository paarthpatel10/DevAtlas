"""check-runs: verify run records after the owner's real runs (spec B2 acceptance).

Problems mean the run record cannot be trusted as is (incomplete, failed, agent never started,
condition C tool unavailable or denied). Notes are information for the owner. Run contents are
untrusted data: they are only read and counted.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from reuse_bench.runner import RUN_FILES, is_finished, load_meta
from reuse_bench.scoring import load_events, mcp_tool_calls

SKIP_DIRS = {"judging"}


@dataclass
class RunCheck:
    run_id: str
    problems: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def _denied_tools(denials: list[dict]) -> list[str]:
    return [str(d.get("tool_name") or d.get("name") or "unknown") for d in denials]


def check_run(run_dir: Path) -> RunCheck:
    result = RunCheck(run_id=run_dir.name)
    if not is_finished(run_dir):
        result.problems.append("incomplete: no valid meta.json (rerun it)")
        return result
    meta = load_meta(run_dir)
    result.problems += [f"missing {name}" for name in RUN_FILES if not (run_dir / name).exists()]
    if meta.exit_status == "failed":
        result.problems.append(f"failed: {meta.failure_reason or 'no reason recorded'}")
        return result
    if meta.exit_status == "truncated":
        result.notes.append(f"truncated (scored): {meta.failure_reason}")

    iso = meta.isolation
    if meta.agent == "claude_code" or "init_seen" in iso:
        if not iso.get("init_seen"):
            result.problems.append("agent did not start (no init event in the stream)")
    actual = iso.get("permission_mode")
    if actual and actual != meta.limits.permission_mode:
        result.problems.append(
            f"agent ran in permission mode '{actual}', expected '{meta.limits.permission_mode}'"
        )

    denied = _denied_tools(meta.permission_denials)
    if denied:
        counts = Counter(denied)
        result.notes.append(
            "denied tools: " + ", ".join(f"{name} x{n}" for name, n in sorted(counts.items()))
        )

    if meta.condition_id == "C":
        servers = list(iso.get("condition_mcp_servers") or [])
        status = {s.get("name"): s.get("status") for s in iso.get("mcp_servers") or []}
        for server in servers:
            if status.get(server) != "connected":
                result.problems.append(
                    f"condition C MCP server {server} is not connected "
                    f"(status: {status.get(server) or 'not listed'})"
                )
        prefixes = tuple(f"mcp__{s}__" for s in servers)
        blocked = sorted({name for name in denied if prefixes and name.startswith(prefixes)})
        if blocked:
            result.problems.append("condition C tool calls were denied: " + ", ".join(blocked))
        calls = mcp_tool_calls(load_events(run_dir), servers)
        result.notes.append(
            f"condition C tool called {calls} time(s)"
            if calls
            else "condition C tool was not called"
        )
    return result


def check_runs(runs_dir: Path, pilot_only: bool = False) -> list[RunCheck]:
    if not runs_dir.is_dir():
        return []
    dirs = sorted(p for p in runs_dir.iterdir() if p.is_dir() and p.name not in SKIP_DIRS)
    if pilot_only:
        dirs = [p for p in dirs if p.name.startswith("pilot--")]
    return [check_run(p) for p in dirs]
