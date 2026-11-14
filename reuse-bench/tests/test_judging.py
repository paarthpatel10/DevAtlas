import csv
import json
import shutil

import pytest

from reuse_bench.cli import main
from reuse_bench.judging import (
    JUDGING_COLUMNS,
    JudgingError,
    blind_text,
    csv_safe,
    export_judging,
    import_judgments,
    load_judgments,
    resolve,
)
from reuse_bench.schema import B_INSTRUCTION, Judgment
from tests.runfactory import make_run, new_file_diff, text_event


@pytest.fixture
def bench(tmp_path, project_root):
    root = tmp_path / "bench"
    shutil.copytree(project_root / "conditions", root / "conditions")
    shutil.copytree(project_root / "cases" / "examples", root / "cases" / "examples")
    (root / "workspaces").mkdir()
    return root


def _scored_runs(bench):
    runs = bench / "runs"
    make_run(
        runs,
        "example-http-retries",
        "B",
        events=[text_event("Per CLAUDE.md: " + B_INSTRUCTION + " I'll write it myself.")],
        diff=new_file_diff("app/retry.py", ["def retry():", "    pass"]),
        final_message="Added a retry helper.",
    )
    make_run(
        runs,
        "example-http-retries",
        "C",
        events=[
            text_event("The skills-but-for-dev search via mcp__skills-but-for-dev__ping says.")
        ],
    )
    make_run(runs, "example-list-batches", "A")
    make_run(runs, "example-http-retries", "A", after={"requirements.txt": "tenacity\n"})
    make_run(runs, "example-nl-dates", "A", status="failed", failure_reason="timeout")
    make_run(runs, "example-nl-dates", "B", pilot=True)
    assert main(["score", "--root", str(bench)]) == 0
    return runs


def _export(bench, include_examples=True, seed=3):
    out = bench / "runs" / "judging" / "judging.csv"
    key = bench / "runs" / "judging" / "key.json"
    n = export_judging(bench, seed, out, key, include_examples=include_examples)
    with out.open(encoding="utf-8-sig", newline="") as fh:
        rows = list(csv.DictReader(fh))
    return n, rows, out, key


def _fill(rows, path, overrides=None):
    overrides = overrides or {}
    with path.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=JUDGING_COLUMNS, lineterminator="\r\n")
        writer.writeheader()
        for row in rows:
            row = dict(row)
            if row["case_kind"] == "reuse":
                row.update(suitable_tool_surfaced=" YES ", tool_adopted="no")
            else:
                row.update(unneeded_dependency="No")
            row.update(overrides.get(row["code"], {}))
            writer.writerow(row)
    return path


def test_export_hides_condition(bench):
    _scored_runs(bench)
    n, rows, out, _ = _export(bench)
    assert n == 3
    assert "condition" not in " ".join(rows[0].keys())
    assert "run_id" not in rows[0]
    text = out.read_text(encoding="utf-8-sig")
    for leak in (
        "--A--",
        "--B--",
        "--C--",
        "example-http-retries--",
        B_INSTRUCTION,
        "skills-but-for-dev",
        "mcp__",
        "CLAUDE.md",
    ):
        assert leak not in text, leak


def test_export_skips_adopted_accepted_failed_pilot_example(bench):
    _scored_runs(bench)
    assert _export(bench, include_examples=False)[0] == 0
    shutil.rmtree(bench / "runs" / "judging", ignore_errors=True)
    n, rows, _, key = _export(bench)
    run_ids = {v["run_id"] for v in json.loads(key.read_text(encoding="utf-8")).values()}
    assert run_ids == {
        "example-http-retries--B--r1",
        "example-http-retries--C--r1",
        "example-list-batches--A--r1",
    }


def test_export_order_is_shuffled_and_codes_opaque(bench):
    _scored_runs(bench)
    _, rows, _, key = _export(bench)
    codes = [row["code"] for row in rows]
    assert len(set(codes)) == 3
    assert all(code.startswith("R") and len(code) == 7 for code in codes)
    mapping = json.loads(key.read_text(encoding="utf-8"))
    assert set(mapping) == set(codes)


def test_export_refuses_to_overwrite_key(bench):
    _scored_runs(bench)
    _export(bench)
    with pytest.raises(JudgingError, match="already exists"):
        _export(bench)


def test_export_requires_scores(bench):
    make_run(bench / "runs", "example-list-batches", "A")
    with pytest.raises(JudgingError, match="score"):
        _export(bench)


def test_row_contents(bench):
    _scored_runs(bench)
    _, rows, _, _ = _export(bench)
    control = next(r for r in rows if r["case_kind"] == "control")
    assert control["suitable_tool_surfaced"] == "n/a" and control["tool_adopted"] == "n/a"
    assert control["unneeded_dependency"] == ""
    reuse = [r for r in rows if r["case_kind"] == "reuse"]
    assert all(r["unneeded_dependency"] == "n/a" for r in reuse)
    with_diff = next(r for r in reuse if "app/retry.py" in r["diff_summary"])
    assert "+2 -0" in with_diff["diff_summary"]
    assert "Added a retry helper." in with_diff["agent_proposal"]


def test_csv_injection_escaped():
    assert csv_safe("=HYPERLINK(1)") == "'=HYPERLINK(1)"
    assert csv_safe("+1") == "'+1" and csv_safe("@x") == "'@x" and csv_safe("-2") == "'-2"
    assert csv_safe("plain") == "plain"


def test_blind_text_case_insensitive():
    assert blind_text("Used Skills-But-For-Dev here", ["skills-but-for-dev"]) == "Used [tool] here"


def test_import_tolerates_bom_crlf_case(bench):
    _scored_runs(bench)
    _, rows, _, key = _export(bench)
    filled = _fill(rows, bench / "j01.csv")
    store = bench / "runs" / "judging" / "judgments"
    assert import_judgments(filled, "j01", key, store) == 3
    stored = load_judgments(store)
    reuse_code = next(r["code"] for r in rows if r["case_kind"] == "reuse")
    [judgment] = stored[reuse_code]
    assert judgment.suitable_tool_surfaced is True and judgment.tool_adopted is False


def test_import_rejects_missing_required_and_unknown_code(bench):
    _scored_runs(bench)
    _, rows, _, key = _export(bench)
    reuse_code = next(r["code"] for r in rows if r["case_kind"] == "reuse")
    bad = _fill(rows, bench / "bad.csv", {reuse_code: {"tool_adopted": "maybe"}})
    store = bench / "runs" / "judging" / "judgments"
    with pytest.raises(JudgingError, match="tool_adopted"):
        import_judgments(bad, "j01", key, store)
    rows.append(dict(rows[0], code="RZZZZZZ"))
    unknown = _fill(rows, bench / "unknown.csv")
    with pytest.raises(JudgingError, match="RZZZZZZ"):
        import_judgments(unknown, "j01", key, store)
    assert not store.exists() or not any(store.iterdir())


def test_import_rejects_bad_judge_code(bench):
    _scored_runs(bench)
    _, rows, _, key = _export(bench)
    with pytest.raises(JudgingError, match="judge"):
        import_judgments(_fill(rows, bench / "x.csv"), "alice", key, bench / "store")


def test_reimport_same_judge_replaces(bench):
    _scored_runs(bench)
    _, rows, _, key = _export(bench)
    store = bench / "store"
    import_judgments(_fill(rows, bench / "a.csv"), "j01", key, store)
    import_judgments(_fill(rows, bench / "b.csv"), "j01", key, store)
    assert all(len(v) == 1 for v in load_judgments(store).values())


def test_third_judge_rejected(bench):
    _scored_runs(bench)
    _, rows, _, key = _export(bench)
    store = bench / "store"
    import_judgments(_fill(rows, bench / "a.csv"), "j01", key, store)
    import_judgments(_fill(rows, bench / "b.csv"), "j02", key, store)
    with pytest.raises(JudgingError, match="two judges"):
        import_judgments(_fill(rows, bench / "c.csv"), "j03", key, store)


def _j(judge, surfaced, code="R000001"):
    return Judgment(
        code=code,
        judge=judge,
        suitable_tool_surfaced=surfaced,
        tool_adopted=False,
        unneeded_dependency=None,
        comment="",
    )


def test_disagreement_marked_disputed():
    result = resolve({"R000001": [_j("j01", True), _j("j02", False)]})
    assert result["R000001"].status == "disputed"


def test_agreement_resolved_with_values():
    result = resolve({"R000001": [_j("j01", True), _j("j02", True)]})
    assert result["R000001"].status == "agreed"
    assert result["R000001"].suitable_tool_surfaced is True


def test_comment_difference_is_not_a_dispute():
    a, b = _j("j01", True), _j("j02", True).model_copy(update={"comment": "different"})
    assert resolve({"R000001": [a, b]})["R000001"].status == "agreed"


def test_single_judge_pending():
    assert resolve({"R000001": [_j("j01", True)]})["R000001"].status == "pending"


def test_cli_export_and_import(bench, capsys):
    _scored_runs(bench)
    assert main(["export-judging", "--root", str(bench), "--include-examples"]) == 0
    out = bench / "runs" / "judging" / "judging.csv"
    with out.open(encoding="utf-8-sig", newline="") as fh:
        rows = list(csv.DictReader(fh))
    filled = _fill(rows, bench / "j01.csv")
    assert main(["import-judgments", str(filled), "--judge", "j01", "--root", str(bench)]) == 0
    assert main(["import-judgments", str(filled), "--judge", "bob", "--root", str(bench)]) == 1
