"""The AgentAdapter protocol every agent integration implements."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable

from reuse_bench.schema import Condition, Limits, RunRecord


@runtime_checkable
class AgentAdapter(Protocol):
    name: str
    # File the agent reads as project instructions (condition B writes its text there).
    instruction_filename: str

    def run(
        self, workspace_dir: Path, prompt: str, condition: Condition, limits: Limits
    ) -> RunRecord: ...
