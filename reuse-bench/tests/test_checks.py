"""check-runs: verifies run records after a real run (synthetic run directories only)."""

import shutil

import pytest

from reuse_bench.checks import check_run, check_runs
from reuse_bench.cli import main
from tests.runfactory import make_run


def _iso(c_status="connected", init_seen=True):
    return {
        "init_seen": init_seen,
        "active_plugins": ["cc-plugin-sec-default"],
        "condition_mcp_servers": ["skills-but-for-dev"],
        "mcp_servers": [{"name": "skills-but-for-dev", "status": c_status}],
    }


def _tool(name):
    return {"type": "assistant", "message": {"content": [{"type": "tool_use", "name": name}]}}


@pytest.fixture
def runs(tmp_path):
    return tmp_path / "runs"


def test_complete_run_is_ok(runs):
    run = make_run(runs, "example-http-retries", "A", pilot=True, isolation={"init_seen": True})
    result = check_run(run)
    assert result.problems == []


def test_missing_artifact_is_a_problem(runs):
    run = make_run(runs, "example-http-retries", "A", isolation={"init_seen": True})
    (run / "diff.patch").unlink()
    shutil.rmtree(run / "manifest_after")
    problems = check_run(run).problems
    assert "missing diff.patch" in problems and "missing manifest_after" in problems


def test_incomplete_run_without_meta(runs):
    run = runs / "pilot--case-002--A--r1"
    run.mkdir(parents=True)
    (run / "events.jsonl").write_text("{}\n", encoding="utf-8")
    assert check_run(run).problems == ["incomplete: no valid meta.json (rerun it)"]


def test_failed_run_reports_reason(runs):
    run = make_run(runs, "example-http-retries", "B", status="failed",
                   failure_reason="no_result (exit 1): auth error")  # fmt: skip
    assert check_run(run).problems == ["failed: no_result (exit 1): auth error"]


def test_agent_that_never_started_is_a_problem(runs):
    run = make_run(runs, "example-http-retries", "A", isolation={"init_seen": False})
    run_meta = check_run(run)
    assert "agent did not start (no init event in the stream)" in run_meta.problems


def test_condition_c_server_not_connected(runs):
    run = make_run(runs, "example-http-retries", "C", isolation=_iso(c_status="failed"))
    assert check_run(run).problems == [
        "condition C MCP server skills-but-for-dev is not connected (status: failed)"
    ]


def test_condition_c_server_missing_from_init(runs):
    iso = _iso()
    iso["mcp_servers"] = []
    run = make_run(runs, "example-http-retries", "C", isolation=iso)
    assert check_run(run).problems == [
        "condition C MCP server skills-but-for-dev is not connected (status: not listed)"
    ]


def test_denied_condition_c_tool_calls_are_a_problem(runs):
    denials = [
        {"tool_name": "mcp__skills-but-for-dev__search_github_repos"},
        {"tool_name": "Bash"},
        {"tool_name": "Bash"},
    ]
    run = make_run(runs, "example-http-retries", "C", isolation=_iso(), permission_denials=denials)
    result = check_run(run)
    assert result.problems == [
        "condition C tool calls were denied: mcp__skills-but-for-dev__search_github_repos"
    ]
    assert "denied tools: Bash x2, mcp__skills-but-for-dev__search_github_repos x1" in result.notes


def test_notes_for_truncated_and_c_tool_calls(runs):
    run = make_run(runs, "example-http-retries", "C", status="truncated",
                   failure_reason="max_turns", isolation=_iso(),
                   events=[_tool("mcp__skills-but-for-dev__ping"), _tool("Read")])  # fmt: skip
    result = check_run(run)
    assert result.problems == []
    assert "truncated (scored): max_turns" in result.notes
    assert "condition C tool called 1 time(s)" in result.notes


def test_condition_c_run_without_tool_call_gets_a_note(runs):
    run = make_run(runs, "example-http-retries", "C", isolation=_iso())
    assert "condition C tool was not called" in check_run(run).notes


def test_check_runs_pilot_only_and_skips_judging_dir(runs):
    make_run(runs, "example-http-retries", "A", pilot=True, isolation={"init_seen": True})
    make_run(runs, "example-http-retries", "B", isolation={"init_seen": True})
    (runs / "judging").mkdir()
    assert [r.run_id for r in check_runs(runs, pilot_only=True)] == [
        "pilot--example-http-retries--A--r1"
    ]
    assert len(check_runs(runs)) == 2


def test_cli_check_runs_exit_codes(tmp_path, capsys):
    root = tmp_path / "bench"
    make_run(root / "runs", "example-http-retries", "A", pilot=True, isolation={"init_seen": True})
    assert main(["check-runs", "--root", str(root), "--pilot"]) == 0
    assert "1 runs checked; 0 with problems" in capsys.readouterr().out
    make_run(root / "runs", "example-nl-dates", "B", pilot=True, status="failed",
             failure_reason="timeout")  # fmt: skip
    assert main(["check-runs", "--root", str(root), "--pilot"]) == 1
    out = capsys.readouterr().out
    assert "PROBLEM pilot--example-nl-dates--B--r1: failed: timeout" in out


def test_cli_check_runs_without_runs(tmp_path, capsys):
    assert main(["check-runs", "--root", str(tmp_path)]) == 1
    assert "No runs found" in capsys.readouterr().out


def test_permission_mode_mismatch_is_a_problem(runs):
    iso = {"init_seen": True, "permission_mode": "default"}
    run = make_run(runs, "example-http-retries", "A", isolation=iso)
    assert check_run(run).problems == ["agent ran in permission mode 'default', expected 'auto'"]


def test_matching_permission_mode_is_ok(runs):
    iso = {"init_seen": True, "permission_mode": "auto"}
    assert check_run(make_run(runs, "example-http-retries", "A", isolation=iso)).problems == []
