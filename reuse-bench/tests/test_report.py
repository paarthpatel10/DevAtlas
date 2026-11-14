import json
import shutil
from datetime import date

import pytest

from reuse_bench.cli import main
from reuse_bench.report import LIMITATIONS, build_report
from tests.runfactory import make_run

TODAY = date(2026, 11, 12)


@pytest.fixture
def bench(tmp_path, project_root):
    root = tmp_path / "bench"
    shutil.copytree(project_root / "conditions", root / "conditions")
    shutil.copytree(project_root / "cases" / "examples", root / "cases" / "examples")
    (root / "workspaces").mkdir()
    return root


def _judge(bench, answers):
    """answers(run_id, kind, judge) -> (surfaced, adopted, unneeded). Synthetic test data only."""
    runs = bench / "runs"
    key = json.loads((runs / "judging" / "key.json").read_text(encoding="utf-8"))
    store = runs / "judging" / "judgments"
    store.mkdir(parents=True, exist_ok=True)
    for judge in ("j01", "j02"):
        rows = []
        for code, entry in key.items():
            surfaced, adopted, unneeded = answers(entry["run_id"], entry["kind"], judge)
            rows.append(
                {
                    "code": code,
                    "judge": judge,
                    "suitable_tool_surfaced": surfaced,
                    "tool_adopted": adopted,
                    "unneeded_dependency": unneeded,
                    "comment": "",
                }
            )
        (store / f"{judge}.json").write_text(json.dumps(rows), encoding="utf-8")


def _fixture_data(bench):
    runs = bench / "runs"
    make_run(runs, "example-http-retries", "A")
    make_run(runs, "example-http-retries", "B", after={"requirements.txt": "tenacity\n"})
    make_run(runs, "example-http-retries", "C")
    make_run(runs, "example-nl-dates", "A")
    make_run(runs, "example-nl-dates", "B")
    make_run(
        runs, "example-nl-dates", "C", status="failed", failure_reason="timeout", cost_usd=None
    )
    make_run(runs, "example-list-batches", "A")
    make_run(runs, "example-list-batches", "B")
    make_run(
        runs,
        "example-list-batches",
        "C",
        started_at=__import__("datetime").datetime(
            2026, 11, 13, 9, 0, tzinfo=__import__("datetime").UTC
        ),
    )
    assert main(["score", "--root", str(bench)]) == 0
    assert main(["export-judging", "--root", str(bench), "--include-examples"]) == 0

    def answers(run_id, kind, judge):
        if kind == "control":
            return None, None, run_id.endswith("--C--r1")
        if run_id == "example-http-retries--C--r1":
            return (judge == "j01"), False, None  # judges disagree -> disputed
        return run_id.startswith("example-nl-dates--B"), False, None

    _judge(bench, answers)


def test_report_from_fixture_data_shows_counts_flags_and_gate(bench):
    _fixture_data(bench)
    text = build_report(bench, TODAY, include_examples=True)
    assert "EXAMPLE DATA - NOT A BENCHMARK RESULT" in text
    assert "2 of 2 cases (100%), too few cases to read" in text  # B surfaced
    assert "too few cases to read" in text
    assert "Gate: STOP PRODUCT (best of B and C: B, 100%)" in text
    assert "The harness prints the gate; the owner decides." in text
    assert "over-recommending" in text and "C" in text
    for limitation in LIMITATIONS:
        assert limitation in text


def test_report_lists_disputed_failed_and_split_days(bench):
    _fixture_data(bench)
    text = build_report(bench, TODAY, include_examples=True)
    disputed = text.split("## Disputed runs")[1].split("##")[0]
    assert "example-http-retries--C--r1" in disputed
    failed = text.split("## Failed runs")[1].split("##")[0]
    assert "example-nl-dates--C--r1" in failed and "timeout" in failed
    days = text.split("## Cases run on more than one day")[1].split("##")[0]
    assert "example-list-batches" in days


def test_report_per_case_table_links_runs(bench):
    _fixture_data(bench)
    text = build_report(bench, TODAY, include_examples=True)
    table = text.split("## Per case")[1].split("## ")[0]
    assert "example-nl-dates" in table
    assert "example-nl-dates--B--r1" in table


def test_report_shows_not_available_for_missing_cost_and_c_unavailable(bench):
    path = bench / "conditions" / "c_external_tool.yaml"
    path.write_text(
        path.read_text(encoding="utf-8")
        .replace("available: true", "available: false")
        .replace('unavailable_reason: ""', 'unavailable_reason: "No candidate ran cleanly."'),
        encoding="utf-8",
    )
    make_run(bench / "runs", "example-list-batches", "A", cost_usd=None)
    text = build_report(bench, TODAY, include_examples=True)
    assert "Total reported cost: Not available" in text
    assert "No candidate ran cleanly." in text


def test_report_excludes_examples_by_default(bench):
    _fixture_data(bench)
    text = build_report(bench, TODAY)
    assert "EXAMPLE DATA" not in text
    assert "No runs found." in text
    assert "Gate: Not available" in text


def test_report_without_runs_says_no_runs(bench):
    text = build_report(bench, TODAY)
    assert "No runs found." in text
    assert "Gate: Not available" in text


def test_report_refuses_examples_into_results_dir(bench, capsys):
    (bench / "results").mkdir()
    assert main(["report", "--root", str(bench), "--include-examples"]) == 1
    assert "--out" in capsys.readouterr().out
    assert not any((bench / "results").iterdir())
    out = bench / "example-report.md"
    assert main(["report", "--root", str(bench), "--include-examples", "--out", str(out)]) == 0
    assert out.exists()


def test_cli_report_default_path(bench, capsys):
    assert main(["report", "--root", str(bench)]) == 0
    written = list((bench / "results").glob("*-report.md"))
    assert len(written) == 1


def test_multiline_failure_reason_stays_on_one_bullet(bench):
    reason = "no_result (exit 1): Traceback\n  File x\nError: auth | failed"
    make_run(bench / "runs", "example-list-batches", "A", status="failed", failure_reason=reason)
    text = build_report(bench, TODAY, include_examples=True)
    failed = text.split("## Failed runs")[1].split("##")[0].strip().splitlines()
    assert failed == [
        "- `example-list-batches--A--r1`: no_result (exit 1): Traceback File x Error: auth | failed"
    ]
