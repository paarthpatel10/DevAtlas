"""A fake agent adapter for tests. Real agents never run in tests or CI."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from reuse_bench.schema import Condition, Limits, RunRecord


class FakeAdapter:
    name = "fake"
    instruction_filename = "CLAUDE.md"

    def __init__(
        self,
        edits: dict[str, str] | Callable[[Path], None] | None = None,
        events: list[dict] | None = None,
        final_message: str = "done",
        exit_status: str = "completed",
        failure_reason: str | None = None,
        cost_usd: float | None = 0.01,
        raise_exc: Exception | None = None,
    ) -> None:
        self.edits = edits or {}
        self.events = events or []
        self.final_message = final_message
        self.exit_status = exit_status
        self.failure_reason = failure_reason
        self.cost_usd = cost_usd
        self.raise_exc = raise_exc
        self.calls: list[dict] = []

    def run(
        self, workspace_dir: Path, prompt: str, condition: Condition, limits: Limits
    ) -> RunRecord:
        self.calls.append(
            {
                "workspace": workspace_dir,
                "prompt": prompt,
                "condition": condition.id,
                "permission_mode": limits.permission_mode,
                "files": sorted(
                    p.relative_to(workspace_dir).as_posix()
                    for p in workspace_dir.rglob("*")
                    if p.is_file() and ".git" not in p.parts
                ),
            }
        )
        started = datetime.now(UTC)
        if self.raise_exc is not None:
            raise self.raise_exc
        if callable(self.edits):
            self.edits(workspace_dir)
        else:
            for rel, text in self.edits.items():
                path = workspace_dir / rel
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(text, encoding="utf-8")
        return RunRecord(
            agent=self.name,
            agent_version="fake-1.0",
            model="fake-model",
            events=self.events,
            final_message=self.final_message,
            exit_status=self.exit_status,
            failure_reason=self.failure_reason,
            cost_usd=self.cost_usd,
            usage=None,
            num_turns=1,
            permission_denials=[],
            isolation={"fake": True},
            started_at=started,
            ended_at=datetime.now(UTC),
        )
