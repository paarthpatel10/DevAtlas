"""Builds synthetic run directories for scoring, judging and report tests.

Everything here is synthetic test data tied to example fixtures. It is never a real result.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from reuse_bench.schema import Limits, RunMeta


def text_event(text: str) -> dict:
    return {"type": "assistant", "message": {"content": [{"type": "text", "text": text}]}}


def tool_event(name: str, **inputs) -> dict:
    block = {"type": "tool_use", "id": "t", "name": name, "input": inputs}
    return {"type": "assistant", "message": {"content": [block]}}


def new_file_diff(path: str, lines: list[str]) -> str:
    body = "".join(f"+{line}\n" for line in lines)
    return (
        f"diff --git a/{path} b/{path}\nnew file mode 100644\n--- /dev/null\n+++ b/{path}\n"
        f"@@ -0,0 +1,{len(lines)} @@\n{body}"
    )


def make_run(
    runs_dir: Path,
    case_id: str,
    condition_id: str = "A",
    repeat: int = 1,
    *,
    events: list[dict] | None = None,
    diff: str = "",
    before: dict[str, str] | None = None,
    after: dict[str, str] | None = None,
    status: str = "completed",
    failure_reason: str | None = None,
    final_message: str = "Done.",
    example: bool = True,
    pilot: bool = False,
    cost_usd: float | None = 0.05,
    started_at: datetime | None = None,
    isolation: dict | None = None,
    permission_denials: list[dict] | None = None,
) -> Path:
    run_id = f"{'pilot--' if pilot else ''}{case_id}--{condition_id}--r{repeat}"
    run_dir = runs_dir / run_id
    for name, files in (("manifest_before", before or {}), ("manifest_after", after or {})):
        (run_dir / name).mkdir(parents=True, exist_ok=True)
        for fname, text in files.items():
            (run_dir / name / fname).write_text(text, encoding="utf-8")
    (run_dir / "events.jsonl").write_text(
        "".join(json.dumps(e) + "\n" for e in events or []), encoding="utf-8"
    )
    (run_dir / "final_message.txt").write_text(final_message, encoding="utf-8")
    (run_dir / "diff.patch").write_text(diff, encoding="utf-8")
    start = started_at or datetime(2026, 11, 12, 10, 0, tzinfo=UTC)
    meta = RunMeta(
        run_id=run_id,
        case_id=case_id,
        case_hash="0" * 64,
        condition_id=condition_id,
        condition_hash="1" * 64,
        repeat=repeat,
        order_seed=1,
        order_position=0,
        limits=Limits(),
        harness_commit="abc123",
        example=example,
        pilot=pilot,
        agent="claude_code",
        agent_version="2.1.322 (Claude Code)",
        model="claude-test-model",
        exit_status=status,
        failure_reason=failure_reason,
        cost_usd=cost_usd,
        usage=None,
        num_turns=3,
        permission_denials=permission_denials or [],
        isolation=isolation
        or {"active_plugins": ["cc-plugin-sec-default"], "env_removed": ["GITHUB_TOKEN"]},
        started_at=start,
        ended_at=start + timedelta(seconds=60),
    )
    (run_dir / "meta.json").write_text(meta.model_dump_json(indent=2), encoding="utf-8")
    return run_dir
