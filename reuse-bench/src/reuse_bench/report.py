"""Markdown report: run environment, metrics with counts, per-case evidence, gate.

Every number links back to the run ids behind it. The harness prints the gate; the owner makes
the decision.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from reuse_bench.loading import load_conditions
from reuse_bench.metrics import (
    CONTINUE_AT,
    CONTROL_FLAG_BELOW,
    STOP_AT,
    RunOutcome,
    case_means,
    collect_outcomes,
    condition_rates,
    format_count,
    gate,
    over_recommending,
    run_counts,
)
from reuse_bench.runner import finished_run_dirs, load_meta
from reuse_bench.schema import NOT_AVAILABLE, RunMeta
from reuse_bench.scoring import load_events, mcp_tool_calls

LIMITATIONS = (
    "Small sample: rates are counts over few cases and make no claim of statistical significance.",
    "One agent (Claude Code) and one ecosystem (Python).",
    "Cases come from one social circle (the owner and colleagues).",
    "Judges know the owner.",
)
METRICS = (
    ("surfaced", "Surfaced (reuse)"),
    ("adopted", "Adopted (reuse)"),
    ("control_accuracy", "Control accuracy"),
)


def _included_metas(root: Path, include_examples: bool) -> list[RunMeta]:
    metas = [load_meta(d) for d in finished_run_dirs(root / "runs")]
    return [m for m in metas if not m.pilot and (include_examples or not m.example)]


def _join(values: set) -> str:
    cleaned = sorted(str(v) for v in values if v)
    return ", ".join(cleaned) if cleaned else NOT_AVAILABLE


def _environment(metas: list[RunMeta], root: Path) -> list[str]:
    lines = ["## Run environment", ""]
    costs = [m.cost_usd for m in metas if m.cost_usd is not None]
    cost = NOT_AVAILABLE if not costs else f"${sum(costs):.2f}"
    if costs and len(costs) < len(metas):
        cost += f" ({len(metas) - len(costs)} runs without a reported cost)"
    starts = sorted(m.started_at for m in metas)
    plugins = {p for m in metas for p in m.isolation.get("active_plugins", [])}
    removed = {p for m in metas for p in m.isolation.get("env_removed", [])}
    limits = {f"{m.limits.max_turns} turns, {m.limits.timeout_s} s" for m in metas}
    lines += [
        f"- Runs: {len(metas)}; cases: {len({m.case_id for m in metas})}",
        f"- Dates: {starts[0].date()} to {starts[-1].date()}",
        f"- Agent: {_join({m.agent for m in metas})}; versions: "
        f"{_join({m.agent_version for m in metas})}",
        f"- Models: {_join({m.model for m in metas})}",
        f"- Harness commits: {_join({m.harness_commit for m in metas})}",
        f"- Limits: {_join(limits)}",
        f"- Still active despite isolation (plugins): {_join(plugins)}",
        f"- Environment variables removed from the agent: {_join(removed)}",
        f"- Total reported cost: {cost}",
    ]
    for _, condition in load_conditions(root / "conditions"):
        if condition.id != "C":
            continue
        if condition.available and condition.external_tool:
            tool = condition.external_tool
            lines.append(f"- Condition C tool: {tool.name} {tool.version} ({tool.install_method})")
        else:
            lines.append(f"- Condition C not run: {condition.unavailable_reason or NOT_AVAILABLE}")
    return lines + [""]


def _metrics_table(rates, condition_ids: list[str], unavailable: dict[str, str]) -> list[str]:
    lines = ["## Metrics by condition", ""]
    lines.append("| Condition | " + " | ".join(label for _, label in METRICS) + " |")
    lines.append("|---" * (len(METRICS) + 1) + "|")
    for cond in condition_ids:
        if cond in unavailable and cond not in rates:
            lines.append(f"| {cond} | not run: {unavailable[cond]} |" + " |" * (len(METRICS) - 1))
            continue
        cells = [format_count(rates[cond][key]) if cond in rates else NOT_AVAILABLE
                 for key, _ in METRICS]  # fmt: skip
        lines.append(f"| {cond} | " + " | ".join(cells) + " |")
    flagged = over_recommending(rates)
    lines.append("")
    if flagged:
        lines.append(
            f"Flagged as over-recommending (control accuracy below "
            f"{CONTROL_FLAG_BELOW:.0%}): {', '.join(flagged)}."
        )
    lines.append(
        "Rates are averaged per case first (mean over repeats), then across cases. Truncated "
        "runs are included; failed, disputed and pending runs are excluded."
    )
    return lines + [""]


def _per_case(outcomes: list[RunOutcome], condition_ids: list[str]) -> list[str]:
    surfaced = case_means([o for o in outcomes if o.kind == "reuse"], "surfaced")
    accuracy = case_means([o for o in outcomes if o.kind == "control"], "no_unneeded_dep")
    lines = [
        "## Per case",
        "",
        "Reuse cases: share of valid runs that surfaced a suitable tool. Control cases: share of "
        "valid runs with no unneeded dependency. Run ids in brackets are the evidence.",
        "",
        "| Case | Kind | " + " | ".join(condition_ids) + " |",
        "|---|---" + "|---" * len(condition_ids) + "|",
    ]
    kinds = {o.case_id: o.kind for o in outcomes}
    for case_id in sorted(kinds):
        means = surfaced if kinds[case_id] == "reuse" else accuracy
        cells = []
        for cond in condition_ids:
            runs = sorted(
                o.run_id for o in outcomes if o.case_id == case_id and o.condition_id == cond
            )
            value = means.get((cond, case_id))
            shown = "-" if value is None else f"{value:.0%}"
            cells.append(f"{shown} ({', '.join(runs)})" if runs else "-")
        lines.append(f"| {case_id} | {kinds[case_id]} | " + " | ".join(cells) + " |")
    return lines + [""]


def _run_counts_table(outcomes: list[RunOutcome], condition_ids: list[str]) -> list[str]:
    counts = run_counts(outcomes)
    lines = [
        "## Runs by condition",
        "",
        "Truncated runs stopped at the turn cap or time limit but left a usable transcript; they "
        "are scored and counted in the rates. Failed runs (crash, login error, no result) are "
        "excluded.",
        "",
        "| Condition | Runs | Completed | Truncated | Failed |",
        "|---|---|---|---|---|",
    ]
    for cond in condition_ids:
        row = counts.get(cond, {"runs": 0, "completed": 0, "truncated": 0, "failed": 0})
        lines.append(
            f"| {cond} | {row['runs']} | {row['completed']} | {row['truncated']} | "
            f"{row['failed']} |"
        )
    return lines + [""]


def _condition_c_tool_use(metas: list[RunMeta], root: Path) -> list[str]:
    lines = ["## Condition C tool use", ""]
    c_metas = [m for m in metas if m.condition_id == "C"]
    if not c_metas:
        return lines + ["No condition C runs.", ""]
    configured = []
    for _, condition in load_conditions(root / "conditions"):
        if condition.id == "C":
            configured = list(condition.mcp_servers)
    called = total_calls = 0
    for meta in c_metas:
        servers = meta.isolation.get("condition_mcp_servers") or configured
        calls = mcp_tool_calls(load_events(root / "runs" / meta.run_id), servers)
        total_calls += calls
        called += 1 if calls else 0
    return lines + [
        f"{called} of {len(c_metas)} condition C runs called the condition C tool "
        f"({total_calls} calls in total). Failed and truncated runs are included in the count.",
        "",
    ]


def _run_list(title: str, selected: list[RunOutcome]) -> list[str]:
    lines = [f"## {title}", ""]
    if not selected:
        return lines + ["None.", ""]
    for o in selected:
        # Reasons can hold multi-line stderr tails; keep each run on one bullet.
        reason = f": {' '.join(o.failure_reason.split())}" if o.failure_reason else ""
        lines.append(f"- `{o.run_id}`{reason}")
    return lines + [""]


def _split_days(outcomes: list[RunOutcome]) -> list[str]:
    days: dict[str, set[str]] = {}
    for o in outcomes:
        days.setdefault(o.case_id, set()).add(o.date)
    split = {case: d for case, d in days.items() if len(d) > 1}
    lines = ["## Cases run on more than one day", ""]
    if not split:
        return lines + ["None.", ""]
    return lines + [f"- {case}: {', '.join(sorted(d))}" for case, d in sorted(split.items())] + [""]


def _gate_lines(rates) -> list[str]:
    verdict, cond, value = gate(rates)
    lines = ["## Gate", ""]
    if verdict == "Not available":
        lines.append("Gate: Not available (no surfaced rate for condition B or C).")
    else:
        lines.append(f"Gate: {verdict} (best of B and C: {cond}, {value:.0%}).")
        if rates[cond]["surfaced"].too_few:
            lines.append("That rate is based on too few cases to read.")
    lines += [
        "",
        f"Thresholds, set before any results existed: {STOP_AT:.0%} or more = STOP PRODUCT; "
        f"{CONTINUE_AT:.0%} or less = CONTINUE; in between = NARROW.",
        "The harness prints the gate; the owner decides.",
    ]
    return lines + [""]


def build_report(root: Path, today: date, include_examples: bool = False) -> str:
    lines = [f"# Reuse benchmark report ({today.isoformat()})", ""]
    if include_examples:
        lines += ["> **EXAMPLE DATA - NOT A BENCHMARK RESULT.** Built from test fixtures.", ""]
    metas = _included_metas(root, include_examples)
    outcomes = collect_outcomes(root, include_examples=include_examples)
    conditions = [c for _, c in load_conditions(root / "conditions")]
    unavailable = {
        c.id: c.unavailable_reason or NOT_AVAILABLE for c in conditions if not c.available
    }
    condition_ids = sorted({c.id for c in conditions} | {o.condition_id for o in outcomes})
    rates = condition_rates(outcomes)

    if not metas:
        lines += ["No runs found.", ""]
    else:
        lines += _environment(metas, root)
        lines += _metrics_table(rates, condition_ids, unavailable)
        lines += _per_case(outcomes, condition_ids)
        lines += _run_counts_table(outcomes, condition_ids)
        lines += _condition_c_tool_use(metas, root)
        lines += _run_list("Disputed runs", [o for o in outcomes if o.status == "disputed"])
        lines += _run_list(
            "Truncated runs (scored; stopped at the turn cap or time limit)",
            [o for o in outcomes if o.truncated and o.status != "failed"],
        )
        lines += _run_list("Failed runs", [o for o in outcomes if o.status == "failed"])
        lines += _run_list(
            "Pending runs (not yet judged by two judges)",
            [o for o in outcomes if o.status == "pending"],
        )
        lines += _split_days(outcomes)
    lines += ["## Limitations", ""] + [f"- {item}" for item in LIMITATIONS] + [""]
    lines += _gate_lines(rates)
    return "\n".join(lines)
