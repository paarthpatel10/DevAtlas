import json
import shutil

import pytest

from reuse_bench.cli import main
from reuse_bench.metrics import (
    Rate,
    RunOutcome,
    case_means,
    collect_outcomes,
    condition_rates,
    format_count,
    gate,
    over_recommending,
)
from tests.runfactory import make_run


def _o(case, cond, surfaced=None, *, kind="reuse", status="valid", repeat=1, ok=None, adopted=None):
    return RunOutcome(
        run_id=f"{case}--{cond}--r{repeat}",
        case_id=case,
        kind=kind,
        condition_id=cond,
        repeat=repeat,
        status=status,
        surfaced=surfaced,
        adopted=adopted if adopted is not None else surfaced,
        no_unneeded_dep=ok,
        date="2026-11-12",
    )


def _rate(value, cases=12):
    return Rate(numerator=value * cases, cases=cases, value=value, too_few=cases < 10)


def test_case_weighted_not_run_weighted():
    outcomes = [
        _o("c1", "A", True, repeat=1),
        _o("c1", "A", True, repeat=2),
        _o("c2", "A", False, repeat=1),
        _o("c2", "A", None, status="failed", repeat=2),
    ]
    assert case_means(outcomes, "surfaced") == {("A", "c1"): 1.0, ("A", "c2"): 0.0}
    rate = condition_rates(outcomes)["A"]["surfaced"]
    assert (rate.numerator, rate.cases, rate.value) == (1.0, 2, 0.5)


def test_half_case_mean():
    outcomes = [_o("c1", "B", True, repeat=1), _o("c1", "B", False, repeat=2)]
    rate = condition_rates(outcomes)["B"]["surfaced"]
    assert rate.numerator == 0.5 and rate.cases == 1


def test_failed_disputed_pending_excluded():
    outcomes = [
        _o("c1", "A", True),
        _o("c2", "A", None, status="failed"),
        _o("c3", "A", None, status="disputed"),
        _o("c4", "A", None, status="pending"),
    ]
    rate = condition_rates(outcomes)["A"]["surfaced"]
    assert (rate.cases, rate.value) == (1, 1.0)


def test_condition_with_only_failed_runs_is_not_available():
    rates = condition_rates([_o("c1", "C", None, status="failed")])
    assert rates["C"]["surfaced"].value is None
    assert format_count(rates["C"]["surfaced"]) == "Not available"


@pytest.mark.parametrize(
    ("b", "c", "expected"),
    [
        (0.80, 0.10, "STOP PRODUCT"),
        (0.50, 0.20, "CONTINUE"),
        (0.65, None, "NARROW"),
        (0.30, 0.81, "STOP PRODUCT"),
        (0.501, 0.0, "NARROW"),
        (0.7999, 0.0, "NARROW"),
    ],
)
def test_gate_boundaries(b, c, expected):
    rates = {"B": {"surfaced": _rate(b)}}
    if c is not None:
        rates["C"] = {"surfaced": _rate(c)}
    assert gate(rates)[0] == expected


def test_gate_not_available_without_b_or_c():
    assert gate({"A": {"surfaced": _rate(0.9)}}) == ("Not available", None, None)
    none_rate = Rate(numerator=0, cases=0, value=None, too_few=True)
    assert gate({"B": {"surfaced": none_rate}})[0] == "Not available"


def test_gate_uses_best_of_b_and_c_ignoring_a():
    rates = {
        "A": {"surfaced": _rate(0.95)},
        "B": {"surfaced": _rate(0.40)},
        "C": {"surfaced": _rate(0.60)},
    }
    assert gate(rates) == ("NARROW", "C", 0.60)


def test_control_accuracy_flag_below_075():
    rates = {
        "A": {"control_accuracy": _rate(0.75, cases=4)},
        "B": {"control_accuracy": _rate(0.74, cases=4)},
        "C": {"control_accuracy": Rate(numerator=0, cases=0, value=None, too_few=True)},
    }
    assert over_recommending(rates) == ["B"]


def test_control_accuracy_counts_no_unneeded_dependency():
    outcomes = [
        _o("k1", "A", kind="control", ok=True),
        _o("k2", "A", kind="control", ok=False),
    ]
    rate = condition_rates(outcomes)["A"]["control_accuracy"]
    assert (rate.numerator, rate.cases, rate.value) == (1.0, 2, 0.5)
    assert condition_rates(outcomes)["A"]["surfaced"].value is None


def test_too_few_cases_flag():
    nine = [_o(f"c{i}", "A", True) for i in range(9)]
    ten = [_o(f"c{i}", "A", True) for i in range(10)]
    assert condition_rates(nine)["A"]["surfaced"].too_few is True
    assert condition_rates(ten)["A"]["surfaced"].too_few is False


def test_format_count():
    assert format_count(Rate(numerator=11.5, cases=18, value=11.5 / 18, too_few=False)) == (
        "11.5 of 18 cases (64%)"
    )
    assert format_count(Rate(numerator=3, cases=4, value=0.75, too_few=True)) == (
        "3 of 4 cases (75%), too few cases to read"
    )


@pytest.fixture
def bench(tmp_path, project_root):
    root = tmp_path / "bench"
    shutil.copytree(project_root / "conditions", root / "conditions")
    shutil.copytree(project_root / "cases", root / "cases")
    (root / "workspaces").mkdir()
    return root


def test_collect_outcomes_from_runs_and_judgments(bench):
    runs = bench / "runs"
    make_run(runs, "example-http-retries", "A", after={"requirements.txt": "tenacity\n"})
    make_run(runs, "example-http-retries", "B")
    make_run(runs, "example-list-batches", "B")
    make_run(runs, "example-nl-dates", "C", status="failed", failure_reason="timeout")
    make_run(runs, "example-nl-dates", "A", pilot=True)
    assert main(["score", "--root", str(bench)]) == 0
    assert main(["export-judging", "--root", str(bench), "--include-examples"]) == 0
    key = json.loads((runs / "judging" / "key.json").read_text(encoding="utf-8"))
    store = runs / "judging" / "judgments"
    store.mkdir()
    for judge, surfaced in (("j01", True), ("j02", True)):
        rows = []
        for code, entry in key.items():
            reuse = entry["kind"] == "reuse"
            rows.append(
                {
                    "code": code,
                    "judge": judge,
                    "suitable_tool_surfaced": surfaced if reuse else None,
                    "tool_adopted": False if reuse else None,
                    "unneeded_dependency": None if reuse else False,
                    "comment": "",
                }
            )
        (store / f"{judge}.json").write_text(json.dumps(rows), encoding="utf-8")

    assert collect_outcomes(bench) == []  # examples excluded by default
    outcomes = {o.run_id: o for o in collect_outcomes(bench, include_examples=True)}
    assert set(outcomes) == {
        "example-http-retries--A--r1",
        "example-http-retries--B--r1",
        "example-list-batches--B--r1",
        "example-nl-dates--C--r1",
    }
    assert outcomes["example-http-retries--A--r1"].surfaced is True
    assert outcomes["example-http-retries--A--r1"].adopted is True
    assert outcomes["example-http-retries--B--r1"].surfaced is True
    assert outcomes["example-http-retries--B--r1"].adopted is False
    assert outcomes["example-list-batches--B--r1"].no_unneeded_dep is True
    assert outcomes["example-nl-dates--C--r1"].status == "failed"
