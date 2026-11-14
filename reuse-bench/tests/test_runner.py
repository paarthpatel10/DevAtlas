import json
import shutil
import sys
from pathlib import Path

import pytest

from reuse_bench import cli
from reuse_bench.adapters.claude_code import ClaudeCodeAdapter
from reuse_bench.loading import load_cases, load_conditions
from reuse_bench.runner import (
    RUN_FILES,
    condition_order,
    is_finished,
    pilot_summary,
    plan_matrix,
    run_id_for,
    run_matrix,
)
from reuse_bench.schema import Limits, RunMeta
from tests.fakes import FakeAdapter

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def bench(tmp_path, project_root):
    root = tmp_path / "bench"
    shutil.copytree(project_root / "conditions", root / "conditions")
    shutil.copytree(project_root / "cases" / "examples", root / "cases" / "examples")
    (root / "workspaces").mkdir()
    return root


def _plan(bench, repeats=1, seed=7, pilot=False, condition_ids=("A", "B", "C")):
    cases = load_cases(bench / "cases")
    conditions = [c for c in load_conditions(bench / "conditions") if c[1].id in condition_ids]
    return plan_matrix(cases, conditions, repeats=repeats, seed=seed, pilot=pilot)


def _run(bench, adapter, planned, force=False):
    return run_matrix(planned, adapter, Limits(), bench, bench / "runs", REPO_ROOT, force=force)


def test_run_id_format():
    assert run_id_for("case-001", "B", 2) == "case-001--B--r2"
    assert run_id_for("case-001", "B", 1, pilot=True) == "pilot--case-001--B--r1"


def test_run_writes_complete_record(bench):
    planned = _plan(bench, condition_ids=("A",))[:1]
    adapter = FakeAdapter(edits={"app/retry.py": "def retry():\n    pass\n"})
    [meta] = _run(bench, adapter, planned)
    run_dir = bench / "runs" / meta.run_id
    for name in RUN_FILES:
        assert (run_dir / name).exists(), name
    saved = RunMeta.model_validate_json((run_dir / "meta.json").read_text(encoding="utf-8"))
    assert len(saved.case_hash) == 64 and len(saved.condition_hash) == 64
    assert saved.order_seed == 7 and saved.limits.max_turns == 30
    assert saved.example is True and saved.exit_status == "completed"
    assert "+def retry():" in (run_dir / "diff.patch").read_text(encoding="utf-8")
    assert (run_dir / "manifest_before" / "pyproject.toml").exists()
    assert adapter.calls[0]["prompt"] == planned[0].case.request.strip()


def test_order_is_seeded_and_recorded(bench):
    first = condition_order("case-001", 1, ["A", "B", "C"], seed=7)
    assert first == condition_order("case-001", 1, ["A", "B", "C"], seed=7)
    orders = {tuple(condition_order(f"case-{i:03d}", 1, ["A", "B", "C"], 7)) for i in range(30)}
    assert len(orders) > 1
    planned = _plan(bench)
    per_case: dict[str, list[str]] = {}
    for run in planned:
        per_case.setdefault(run.case.id, []).append(run.condition.id)
        assert run.order_seed == 7
    for case_id, ids in per_case.items():
        assert ids == condition_order(case_id, 1, ["A", "B", "C"], 7)


def test_matrix_is_case_major(bench):
    planned = _plan(bench, repeats=2)
    case_ids = [run.case.id for run in planned]
    assert case_ids == sorted(case_ids)
    assert len(planned) == 3 * 3 * 2


def test_resume_skips_finished_and_force_reruns(bench):
    planned = _plan(bench, condition_ids=("A",))[:1]
    adapter = FakeAdapter()
    _run(bench, adapter, planned)
    _run(bench, adapter, planned)
    assert len(adapter.calls) == 1
    _run(bench, adapter, planned, force=True)
    assert len(adapter.calls) == 2


def test_failed_run_is_not_repeated_without_force(bench):
    planned = _plan(bench, condition_ids=("A",))[:1]
    adapter = FakeAdapter(exit_status="failed", failure_reason="timeout")
    _run(bench, adapter, planned)
    _run(bench, adapter, planned)
    assert len(adapter.calls) == 1


def test_incomplete_dir_is_rerun(bench):
    planned = _plan(bench, condition_ids=("A",))[:1]
    run_dir = bench / "runs" / planned[0].run_id
    run_dir.mkdir(parents=True)
    (run_dir / "events.jsonl").write_text("{}\n", encoding="utf-8")
    assert not is_finished(run_dir)
    adapter = FakeAdapter()
    _run(bench, adapter, planned)
    assert len(adapter.calls) == 1
    assert is_finished(run_dir)


def test_adapter_exception_becomes_failed_run(bench):
    planned = _plan(bench, condition_ids=("A",))[:1]
    [meta] = _run(bench, FakeAdapter(raise_exc=RuntimeError("kaboom")), planned)
    assert meta.exit_status == "failed"
    assert meta.failure_reason.startswith("harness: RuntimeError")


def test_unavailable_condition_skipped_with_notice(bench, capsys):
    path = bench / "conditions" / "c_external_tool.yaml"
    text = path.read_text(encoding="utf-8").replace("available: true", "available: false")
    path.write_text(text, encoding="utf-8")
    planned = _plan(bench)
    assert {run.condition.id for run in planned} == {"A", "B"}
    assert "condition_unavailable" in capsys.readouterr().err


def test_pilot_projection_math(bench):
    planned = _plan(bench, condition_ids=("A",))[:2]
    metas = [
        _run(bench, FakeAdapter(cost_usd=0.10), planned[:1])[0],
        _run(bench, FakeAdapter(cost_usd=0.30), planned[1:])[0],
    ]
    metas[0] = metas[0].model_copy(
        update={"ended_at": metas[0].started_at + __import__("datetime").timedelta(seconds=10)}
    )
    metas[1] = metas[1].model_copy(
        update={"ended_at": metas[1].started_at + __import__("datetime").timedelta(seconds=30)}
    )
    summary = pilot_summary(metas, full_runs=60)
    assert "1200 s" in summary
    assert "$12.00" in summary
    no_cost = metas[0].model_copy(update={"cost_usd": None})
    assert "Not available" in pilot_summary([no_cost], full_runs=10)


def test_meta_contains_no_secret_values(bench, monkeypatch):
    """End to end through the real adapter class, with a stand-in executable that dumps its env."""
    secret = "sk-test-SECRET-VALUE-0123456789"
    monkeypatch.setenv("ANTHROPIC_API_KEY", secret)
    monkeypatch.setenv("GITHUB_TOKEN", secret + "gh")
    dump_env = (
        "import os, json; print(json.dumps({'type': 'assistant', 'message': {'content': "
        "[{'type': 'text', 'text': json.dumps(dict(os.environ))}]}}))"
    )
    adapter = ClaudeCodeAdapter(executable=sys.executable)
    monkeypatch.setattr(adapter, "build_command", lambda *a, **k: [sys.executable, "-c", dump_env])
    planned = _plan(bench, condition_ids=("A",))[:1]
    [meta] = _run(bench, adapter, planned)
    assert "ANTHROPIC_API_KEY" in meta.isolation["env_removed"]
    for path in (bench / "runs").rglob("*"):
        if path.is_file():
            assert secret not in path.read_text(encoding="utf-8", errors="replace"), path


def test_cli_run_refuses_examples_without_flag(bench, monkeypatch, capsys):
    monkeypatch.setattr(cli, "make_adapter", lambda name: FakeAdapter())
    assert cli.main(["run", "--root", str(bench)]) == 1
    assert "no real cases" in capsys.readouterr().out


def test_cli_run_with_examples_uses_fake_adapter(bench, monkeypatch):
    fake = FakeAdapter()
    monkeypatch.setattr(cli, "make_adapter", lambda name: fake)
    code = cli.main(
        ["run", "--root", str(bench), "--include-examples", "--repeats", "1", "--conditions", "A,B"]
    )
    assert code == 0
    assert len(fake.calls) == 3 * 2
    assert {c["condition"] for c in fake.calls} == {"A", "B"}


def test_cli_pilot_with_examples(bench, monkeypatch, capsys):
    fake = FakeAdapter()
    monkeypatch.setattr(cli, "make_adapter", lambda name: fake)
    assert cli.main(["pilot", "--root", str(bench), "--include-examples"]) == 0
    assert len(fake.calls) == 3 * 3
    out = capsys.readouterr().out
    assert "Projected full run" in out
    assert all(p.name.startswith("pilot--") for p in (bench / "runs").iterdir())


def test_cli_run_stops_on_validation_errors(bench, monkeypatch, capsys):
    monkeypatch.setattr(cli, "make_adapter", lambda name: FakeAdapter())
    bad = bench / "cases" / "examples" / "example-nl-dates.yaml"
    bad.write_text(
        bad.read_text(encoding="utf-8").replace("everyday words", "dateparser words"),
        encoding="utf-8",
    )
    assert cli.main(["run", "--root", str(bench), "--include-examples"]) == 1
    assert "dateparser" in capsys.readouterr().out


def test_events_written_as_jsonl(bench):
    planned = _plan(bench, condition_ids=("A",))[:1]
    events = [{"type": "assistant", "message": {"content": [{"type": "text", "text": "hé ✓"}]}}]
    [meta] = _run(bench, FakeAdapter(events=events), planned)
    lines = (bench / "runs" / meta.run_id / "events.jsonl").read_text(encoding="utf-8").splitlines()
    assert json.loads(lines[0]) == events[0]


def test_diff_failure_keeps_agent_record(bench, monkeypatch):
    from reuse_bench import runner

    def broken_diff(_workspace):
        raise RuntimeError("git exploded")

    monkeypatch.setattr(runner, "final_diff", broken_diff)
    planned = _plan(bench, condition_ids=("A",))[:1]
    events = [{"type": "assistant", "message": {"content": [{"type": "text", "text": "hi"}]}}]
    [meta] = _run(bench, FakeAdapter(events=events, final_message="kept", cost_usd=0.5), planned)
    run_dir = bench / "runs" / meta.run_id
    assert meta.exit_status == "failed"
    assert "diff" in meta.failure_reason and "git exploded" in meta.failure_reason
    assert meta.cost_usd == 0.5
    assert (run_dir / "final_message.txt").read_text(encoding="utf-8") == "kept"
    assert (run_dir / "events.jsonl").read_text(encoding="utf-8").strip()


def test_truncated_run_is_recorded_as_truncated(bench):
    planned = _plan(bench, condition_ids=("A",))[:1]
    adapter = FakeAdapter(
        edits={"app/x.py": "x = 1\n"}, exit_status="truncated", failure_reason="max_turns"
    )
    [meta] = _run(bench, adapter, planned)
    assert (meta.exit_status, meta.failure_reason) == ("truncated", "max_turns")
    assert "+x = 1" in (bench / "runs" / meta.run_id / "diff.patch").read_text(encoding="utf-8")


def test_diff_failure_on_truncated_run_becomes_failed(bench, monkeypatch):
    from reuse_bench import runner

    monkeypatch.setattr(runner, "final_diff", lambda _ws: (_ for _ in ()).throw(OSError("x")))
    planned = _plan(bench, condition_ids=("A",))[:1]
    adapter = FakeAdapter(exit_status="truncated", failure_reason="timeout")
    [meta] = _run(bench, adapter, planned)
    assert meta.exit_status == "failed" and "diff failed" in meta.failure_reason


def test_cli_pilot_on_chosen_cases_including_examples(bench, monkeypatch, capsys):
    fake = FakeAdapter(exit_status="truncated", failure_reason="max_turns")
    monkeypatch.setattr(cli, "make_adapter", lambda name: fake)
    code = cli.main(
        [
            "pilot",
            "--root",
            str(bench),
            "--include-examples",
            "--cases",
            "example-nl-dates,example-list-batches",
        ]
    )
    assert code == 0
    assert len(fake.calls) == 2 * 3
    cases = {p.name.split("--")[1] for p in (bench / "runs").iterdir()}
    assert cases == {"example-nl-dates", "example-list-batches"}
    assert all(p.name.startswith("pilot--") for p in (bench / "runs").iterdir())
    out = capsys.readouterr().out
    assert "6 truncated (scored), 0 failed (excluded)" in out


def test_cli_pilot_rejects_unknown_case(bench, monkeypatch, capsys):
    monkeypatch.setattr(cli, "make_adapter", lambda name: FakeAdapter())
    assert cli.main(["pilot", "--root", str(bench), "--cases", "example-nl-dates"]) == 1
    assert "unknown or excluded case ids: example-nl-dates" in capsys.readouterr().out
