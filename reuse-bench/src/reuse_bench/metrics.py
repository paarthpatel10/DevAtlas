"""Metrics and the decision gate.

Rates are aggregated per case first (mean over that case's valid repeats), then across cases,
so every case weighs the same. Failed, disputed and pending runs are excluded and listed
separately in the report. Example fixtures are excluded unless explicitly included.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from reuse_bench.judging import resolutions_by_run
from reuse_bench.loading import load_cases
from reuse_bench.runner import finished_run_dirs, load_meta
from reuse_bench.schema import NOT_AVAILABLE, AutoScore

MIN_CASES = 10
STOP_AT = 0.80
CONTINUE_AT = 0.50
CONTROL_FLAG_BELOW = 0.75
GATE_CONDITIONS = ("B", "C")

Gate = Literal["STOP PRODUCT", "CONTINUE", "NARROW", "Not available"]
OutcomeStatus = Literal["valid", "failed", "disputed", "pending"]


@dataclass(frozen=True)
class RunOutcome:
    run_id: str
    case_id: str
    kind: str
    condition_id: str
    repeat: int
    status: OutcomeStatus
    surfaced: bool | None
    adopted: bool | None
    no_unneeded_dep: bool | None
    date: str
    failure_reason: str | None = None
    truncated: bool = False  # stopped at the turn cap or time limit; scored and counted normally


@dataclass(frozen=True)
class Rate:
    numerator: float
    cases: int
    value: float | None
    too_few: bool


def collect_outcomes(root: Path, include_examples: bool = False) -> list[RunOutcome]:
    cases = {case.id: case for _, case in load_cases(root / "cases")}
    resolutions = resolutions_by_run(root)
    outcomes = []
    for run_dir in finished_run_dirs(root / "runs"):
        meta = load_meta(run_dir)
        case = cases.get(meta.case_id)
        if meta.pilot or case is None or (meta.example and not include_examples):
            continue
        base = dict(
            run_id=meta.run_id,
            case_id=meta.case_id,
            kind=case.kind,
            condition_id=meta.condition_id,
            repeat=meta.repeat,
            date=meta.started_at.date().isoformat(),
            truncated=meta.exit_status == "truncated",
        )
        empty = dict(surfaced=None, adopted=None, no_unneeded_dep=None)
        if meta.exit_status == "failed":
            outcomes.append(
                RunOutcome(**base, **empty, status="failed", failure_reason=meta.failure_reason)
            )
            continue
        if meta.exit_status == "truncated":
            base["failure_reason"] = meta.failure_reason  # timeout or max_turns
        score_path = run_dir / "auto_score.json"
        score = (
            AutoScore.model_validate_json(score_path.read_text(encoding="utf-8"))
            if score_path.exists()
            else None
        )
        if score is not None and score.label == "adopted_accepted":
            outcomes.append(
                RunOutcome(
                    **base, status="valid", surfaced=True, adopted=True, no_unneeded_dep=None
                )
            )
            continue
        resolution = resolutions.get(meta.run_id)
        if resolution is None or resolution.status == "pending":
            outcomes.append(RunOutcome(**base, **empty, status="pending"))
        elif resolution.status == "disputed":
            outcomes.append(RunOutcome(**base, **empty, status="disputed"))
        elif case.kind == "reuse":
            outcomes.append(
                RunOutcome(
                    **base,
                    status="valid",
                    surfaced=resolution.suitable_tool_surfaced,
                    adopted=resolution.tool_adopted,
                    no_unneeded_dep=None,
                )
            )
        else:
            unneeded = resolution.unneeded_dependency
            outcomes.append(
                RunOutcome(
                    **base,
                    status="valid",
                    surfaced=None,
                    adopted=None,
                    no_unneeded_dep=None if unneeded is None else not unneeded,
                )
            )
    return outcomes


def run_counts(outcomes: list[RunOutcome]) -> dict[str, dict[str, int]]:
    """Runs per condition, split into completed, truncated and failed."""
    counts: dict[str, dict[str, int]] = {}
    for o in outcomes:
        row = counts.setdefault(
            o.condition_id, {"runs": 0, "completed": 0, "truncated": 0, "failed": 0}
        )
        row["runs"] += 1
        if o.status == "failed":
            row["failed"] += 1
        elif o.truncated:
            row["truncated"] += 1
        else:
            row["completed"] += 1
    return counts


def case_means(outcomes: list[RunOutcome], field: str) -> dict[tuple[str, str], float]:
    values: dict[tuple[str, str], list[bool]] = {}
    for outcome in outcomes:
        value = getattr(outcome, field)
        if outcome.status == "valid" and value is not None:
            values.setdefault((outcome.condition_id, outcome.case_id), []).append(bool(value))
    return {key: sum(v) / len(v) for key, v in values.items()}


def _rate(means: dict[tuple[str, str], float], condition_id: str) -> Rate:
    per_case = [m for (cond, _), m in means.items() if cond == condition_id]
    if not per_case:
        return Rate(numerator=0.0, cases=0, value=None, too_few=True)
    total = sum(per_case)
    return Rate(
        numerator=total,
        cases=len(per_case),
        value=total / len(per_case),
        too_few=len(per_case) < MIN_CASES,
    )


def condition_rates(outcomes: list[RunOutcome]) -> dict[str, dict[str, Rate]]:
    reuse = [o for o in outcomes if o.kind == "reuse"]
    control = [o for o in outcomes if o.kind == "control"]
    surfaced = case_means(reuse, "surfaced")
    adopted = case_means(reuse, "adopted")
    accuracy = case_means(control, "no_unneeded_dep")
    return {
        cond: {
            "surfaced": _rate(surfaced, cond),
            "adopted": _rate(adopted, cond),
            "control_accuracy": _rate(accuracy, cond),
        }
        for cond in sorted({o.condition_id for o in outcomes})
    }


def gate(rates: dict[str, dict[str, Rate]]) -> tuple[Gate, str | None, float | None]:
    candidates = [
        (cond, rates[cond]["surfaced"].value)
        for cond in GATE_CONDITIONS
        if cond in rates and "surfaced" in rates[cond] and rates[cond]["surfaced"].value is not None
    ]
    if not candidates:
        return "Not available", None, None
    best_cond, best = max(candidates, key=lambda item: item[1])
    value = round(best, 10)  # avoid float noise at the thresholds
    if value >= STOP_AT:
        return "STOP PRODUCT", best_cond, best
    if value <= CONTINUE_AT:
        return "CONTINUE", best_cond, best
    return "NARROW", best_cond, best


def over_recommending(rates: dict[str, dict[str, Rate]]) -> list[str]:
    return sorted(
        cond
        for cond, by_metric in rates.items()
        if (acc := by_metric.get("control_accuracy")) is not None
        and acc.value is not None
        and round(acc.value, 10) < CONTROL_FLAG_BELOW
    )


def _number(value: float) -> str:
    return str(int(value)) if float(value).is_integer() else f"{value:.1f}"


def format_count(rate: Rate) -> str:
    if rate.value is None:
        return NOT_AVAILABLE
    text = f"{_number(rate.numerator)} of {rate.cases} cases ({round(rate.value * 100)}%)"
    return text + (", too few cases to read" if rate.too_few else "")
