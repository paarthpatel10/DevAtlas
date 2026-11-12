"""Pydantic v2 models for cases, conditions, limits, runs, scores and judgments."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

# Condition B text, fixed before any results existed (spec section 6). Never edit.
B_INSTRUCTION = (
    "Before implementing any non-trivial feature, first check whether a maintained open-source "
    "library or tool already provides it. If one fits this project's stack and license, propose "
    "it and use it instead of writing custom code. If none fits, say so briefly and build it."
)

NOT_AVAILABLE = "Not available"

CaseId = Annotated[str, StringConstraints(pattern=r"^[a-z0-9][a-z0-9-]*$")]
NonEmpty = Annotated[str, StringConstraints(min_length=1)]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Stack(_Strict):
    language: NonEmpty
    python_version: str | None = None
    frameworks: list[str] = Field(default_factory=list)


class AcceptedTool(_Strict):
    name: NonEmpty
    packages: list[NonEmpty] = Field(min_length=1)
    import_names: list[NonEmpty] = Field(min_length=1)
    repo_url: Annotated[str, StringConstraints(pattern=r"^https://\S+$")]


class GroundTruth(_Strict):
    accepted_tools: list[AcceptedTool] = Field(default_factory=list)
    rationale: NonEmpty
    found_how: Literal["searched", "colleague", "docs", "assistant", "other"]


class Case(_Strict):
    id: CaseId
    title: NonEmpty
    kind: Literal["reuse", "control"]
    example: bool = False
    contributor: Annotated[str, StringConstraints(pattern=r"^c\d{2,}$")]
    consent_to_publish: bool
    date_observed: Annotated[str, StringConstraints(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")]
    stack: Stack
    context: NonEmpty
    request: NonEmpty
    workspace: str | None = None
    ground_truth: GroundTruth
    notes: str = ""

    @model_validator(mode="after")
    def _kind_matches_ground_truth(self) -> Case:
        tools = self.ground_truth.accepted_tools
        if self.kind == "reuse" and not tools:
            raise ValueError("a reuse case needs at least one accepted tool")
        if self.kind == "control" and tools:
            raise ValueError("a control case must have an empty accepted_tools list")
        return self


class ExternalTool(_Strict):
    name: NonEmpty
    version: NonEmpty
    install_method: NonEmpty
    source_url: NonEmpty


class Condition(_Strict):
    id: Literal["A", "B", "C"]
    name: NonEmpty
    description: str = ""
    project_instruction: str | None = None
    mcp_servers: dict[str, dict] = Field(default_factory=dict)
    extra_allowed_tools: list[str] = Field(default_factory=list)
    external_tool: ExternalTool | None = None
    available: bool = True
    unavailable_reason: str = ""


# Same allowlist for every condition, so web access and tooling are identical across A/B/C.
DEFAULT_ALLOWED_TOOLS: list[str] = [
    "Read",
    "Edit",
    "Write",
    "Glob",
    "Grep",
    "WebSearch",
    "WebFetch",
    "Bash(uv *)",
    "Bash(pip *)",
    "Bash(python *)",
    "Bash(pytest *)",
    "Bash(git status*)",
    "Bash(git diff*)",
]


class Limits(_Strict):
    max_turns: int = Field(default=30, ge=1)
    timeout_s: int = Field(default=900, ge=1)
    permission_mode: str = "dontAsk"
    allowed_tools: list[str] = Field(default_factory=lambda: list(DEFAULT_ALLOWED_TOOLS))
    model: str | None = None


RunStatus = Literal["completed", "failed"]


class RunRecord(_Strict):
    """What an adapter returns for one agent run."""

    agent: str
    agent_version: str | None
    model: str | None
    events: list[dict]
    final_message: str
    exit_status: RunStatus
    failure_reason: str | None
    cost_usd: float | None
    usage: dict | None
    num_turns: int | None
    permission_denials: list[dict]
    isolation: dict
    started_at: datetime
    ended_at: datetime


class RunMeta(_Strict):
    """Contents of runs/<run_id>/meta.json."""

    run_id: str
    case_id: str
    case_hash: str
    condition_id: str
    condition_hash: str
    repeat: int
    order_seed: int
    order_position: int
    limits: Limits
    harness_commit: str | None
    example: bool
    pilot: bool
    agent: str
    agent_version: str | None
    model: str | None
    exit_status: RunStatus
    failure_reason: str | None
    cost_usd: float | None
    usage: dict | None
    num_turns: int | None
    permission_denials: list[dict]
    isolation: dict
    started_at: datetime
    ended_at: datetime
