"""Matrix execution: cases x conditions x repeats, seeded order, isolation, resume, pilot."""

from __future__ import annotations

import json
import os
import random
import shutil
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from reuse_bench.adapters.base import AgentAdapter
from reuse_bench.loading import case_hash, file_sha256
from reuse_bench.logs import log
from reuse_bench.schema import NOT_AVAILABLE, Case, Condition, Limits, RunMeta, RunRecord
from reuse_bench.validation import resolve_workspace
from reuse_bench.workspace import (
    final_diff,
    prepare_workspace,
    remove_workspace,
    snapshot_manifests,
)

RUN_FILES = (
    "meta.json",
    "events.jsonl",
    "final_message.txt",
    "diff.patch",
    "manifest_before",
    "manifest_after",
)
DEFAULT_SEED = 20261112
DEFAULT_REPEATS = 2


@dataclass(frozen=True)
class PlannedRun:
    case_path: Path
    case: Case
    condition_path: Path
    condition: Condition
    repeat: int
    run_id: str
    order_seed: int
    order_position: int
    pilot: bool


def run_id_for(case_id: str, condition_id: str, repeat: int, pilot: bool = False) -> str:
    run_id = f"{case_id}--{condition_id}--r{repeat}"
    return f"pilot--{run_id}" if pilot else run_id


def condition_order(case_id: str, repeat: int, condition_ids: list[str], seed: int) -> list[str]:
    order = sorted(condition_ids)
    random.Random(f"{seed}:{case_id}:{repeat}").shuffle(order)
    return order


def plan_matrix(
    cases: list[tuple[Path, Case]],
    conditions: list[tuple[Path, Condition]],
    repeats: int,
    seed: int,
    pilot: bool,
) -> list[PlannedRun]:
    """Case-major plan, so all conditions of a case run back to back (the same day)."""
    available = {}
    for path, condition in conditions:
        if condition.available:
            available[condition.id] = (path, condition)
        else:
            log(
                "condition_unavailable",
                condition=condition.id,
                reason=condition.unavailable_reason or NOT_AVAILABLE,
            )
    planned = []
    for case_path, case in sorted(cases, key=lambda item: item[1].id):
        for repeat in range(1, repeats + 1):
            order = condition_order(case.id, repeat, list(available), seed)
            for position, condition_id in enumerate(order):
                condition_path, condition = available[condition_id]
                planned.append(
                    PlannedRun(
                        case_path=case_path,
                        case=case,
                        condition_path=condition_path,
                        condition=condition,
                        repeat=repeat,
                        run_id=run_id_for(case.id, condition_id, repeat, pilot),
                        order_seed=seed,
                        order_position=position,
                        pilot=pilot,
                    )
                )
    return planned


def is_finished(run_dir: Path) -> bool:
    try:
        RunMeta.model_validate_json((run_dir / "meta.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return True


def load_meta(run_dir: Path) -> RunMeta:
    return RunMeta.model_validate_json((run_dir / "meta.json").read_text(encoding="utf-8"))


def harness_commit(root: Path) -> str | None:
    try:
        head = (
            subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, check=True)
            .stdout.decode()
            .strip()
        )
        dirty = subprocess.run(
            ["git", "status", "--porcelain", "--", "."], cwd=root, capture_output=True, check=True
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None
    return f"{head}+dirty" if dirty else head


def _failed_record(adapter: AgentAdapter, started: datetime, reason: str) -> RunRecord:
    return RunRecord(
        agent=getattr(adapter, "name", "unknown"),
        agent_version=None,
        model=None,
        events=[],
        final_message="",
        exit_status="failed",
        failure_reason=reason,
        cost_usd=None,
        usage=None,
        num_turns=None,
        permission_denials=[],
        isolation={},
        started_at=started,
        ended_at=datetime.now(UTC),
    )


def _write_atomic(path: Path, text: str) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def execute_run(
    planned: PlannedRun,
    adapter: AgentAdapter,
    limits: Limits,
    bench_root: Path,
    runs_dir: Path,
    repo_root: Path,
    commit: str | None = None,
) -> RunMeta:
    run_dir = runs_dir / planned.run_id
    if run_dir.exists():
        shutil.rmtree(run_dir)
    run_dir.mkdir(parents=True)
    case, condition = planned.case, planned.condition
    source_ws = resolve_workspace(bench_root, case.workspace) if case.workspace else None
    log("run_start", run_id=planned.run_id)

    started = datetime.now(UTC)
    workspace: Path | None = None
    diff = ""
    try:
        workspace = prepare_workspace(
            case, bench_root, condition, adapter.instruction_filename, repo_root
        )
        snapshot_manifests(workspace, run_dir / "manifest_before")
        try:
            record = adapter.run(workspace, case.request.strip(), condition, limits)
        except Exception as exc:  # the run fails; the matrix continues
            record = _failed_record(adapter, started, f"harness: {type(exc).__name__}: {exc}")
        try:
            diff = final_diff(workspace)
            snapshot_manifests(workspace, run_dir / "manifest_after")
        except Exception as exc:
            # Keep the agent's transcript and cost; without a diff the run cannot be scored.
            if record.exit_status == "completed":
                record = record.model_copy(
                    update={
                        "exit_status": "failed",
                        "failure_reason": f"harness: diff failed: {type(exc).__name__}: {exc}",
                    }
                )
    except Exception as exc:
        record = _failed_record(adapter, started, f"harness: {type(exc).__name__}: {exc}")
    finally:
        if workspace is not None:
            remove_workspace(workspace)
    for name in ("manifest_before", "manifest_after"):
        (run_dir / name).mkdir(exist_ok=True)

    (run_dir / "events.jsonl").write_text(
        "".join(json.dumps(e, ensure_ascii=False) + "\n" for e in record.events), encoding="utf-8"
    )
    (run_dir / "final_message.txt").write_text(record.final_message, encoding="utf-8")
    (run_dir / "diff.patch").write_text(diff, encoding="utf-8")

    fields = record.model_dump(exclude={"events", "final_message"})
    meta = RunMeta(
        run_id=planned.run_id,
        case_id=case.id,
        case_hash=case_hash(planned.case_path, source_ws),
        condition_id=condition.id,
        condition_hash=file_sha256(planned.condition_path),
        repeat=planned.repeat,
        order_seed=planned.order_seed,
        order_position=planned.order_position,
        limits=limits,
        harness_commit=commit,
        example=case.example,
        pilot=planned.pilot,
        **fields,
    )
    _write_atomic(run_dir / "meta.json", meta.model_dump_json(indent=2))  # written last
    log("run_end", run_id=planned.run_id, status=meta.exit_status, reason=meta.failure_reason)
    return meta


def run_matrix(
    planned_runs: list[PlannedRun],
    adapter: AgentAdapter,
    limits: Limits,
    bench_root: Path,
    runs_dir: Path,
    repo_root: Path,
    force: bool = False,
) -> list[RunMeta]:
    commit = harness_commit(bench_root)
    metas = []
    for planned in planned_runs:
        run_dir = runs_dir / planned.run_id
        if not force and is_finished(run_dir):
            log("run_skip", run_id=planned.run_id, reason="finished; use --force to repeat")
            metas.append(load_meta(run_dir))
            continue
        metas.append(execute_run(planned, adapter, limits, bench_root, runs_dir, repo_root, commit))
    return metas


def _money(value: float | None) -> str:
    return NOT_AVAILABLE if value is None else f"${value:.2f}"


def pilot_summary(metas: list[RunMeta], full_runs: int) -> str:
    lines = ["run_id | status | duration | cost | turns"]
    durations, costs = [], []
    for meta in metas:
        seconds = (meta.ended_at - meta.started_at).total_seconds()
        durations.append(seconds)
        if meta.cost_usd is not None:
            costs.append(meta.cost_usd)
        turns = NOT_AVAILABLE if meta.num_turns is None else str(meta.num_turns)
        lines.append(
            f"{meta.run_id} | {meta.exit_status} | {seconds:.0f} s | "
            f"{_money(meta.cost_usd)} | {turns}"
        )
    if not metas:
        return "No pilot runs."
    mean_s = sum(durations) / len(durations)
    projected_cost = sum(costs) / len(costs) * full_runs if costs else None
    lines += [
        "",
        f"Projected full run ({full_runs} runs): {mean_s * full_runs:.0f} s "
        f"({mean_s * full_runs / 3600:.1f} h), cost {_money(projected_cost)}",
        "Cost is the CLI's reported total_cost_usd (API-equivalent). On a subscription it does "
        "not map directly to your usage allowance; check your plan's usage before approving.",
    ]
    return "\n".join(lines)


def find_repo_root(bench_root: Path) -> Path:
    try:
        out = (
            subprocess.run(
                ["git", "rev-parse", "--show-toplevel"],
                cwd=bench_root,
                capture_output=True,
                check=True,
            )
            .stdout.decode()
            .strip()
        )
        return Path(out)
    except (OSError, subprocess.CalledProcessError):
        return bench_root


def finished_run_dirs(runs_dir: Path) -> list[Path]:
    """Every run directory with a valid meta.json, sorted by run id."""
    if not runs_dir.is_dir():
        return []
    return sorted(p for p in runs_dir.iterdir() if p.is_dir() and is_finished(p))
