import pytest

from reuse_bench.cli import main
from reuse_bench.loading import load_case
from reuse_bench.scoring import (
    first_edit_index,
    install_packages,
    manifest_packages,
    mentions_before_edit,
    new_imports,
    normalize_pkg,
    score_run,
)
from tests.runfactory import make_run, new_file_diff, text_event, tool_event

PYPROJECT = '[project]\nname = "app"\nrequires-python = ">=3.12"\ndependencies = [{deps}]\n'


@pytest.fixture
def retry(project_root):
    return load_case(project_root / "cases" / "examples" / "example-http-retries.yaml")


@pytest.fixture
def batches(project_root):
    return load_case(project_root / "cases" / "examples" / "example-list-batches.yaml")


def _pyproject(*deps: str) -> str:
    return PYPROJECT.format(deps=", ".join(f'"{d}"' for d in deps))


def _score(tmp_path, case, project_root, **kwargs):
    run_dir = make_run(tmp_path / "runs", case.id, **kwargs)
    return score_run(run_dir, case, project_root)


def test_label_adopted_accepted_via_pyproject(tmp_path, retry, project_root):
    score = _score(
        tmp_path,
        retry,
        project_root,
        before={"pyproject.toml": _pyproject("httpx")},
        after={"pyproject.toml": _pyproject("httpx", "tenacity>=9")},
    )
    assert score.label == "adopted_accepted"
    assert score.added_packages == ["tenacity"]
    assert score.needs_judging is False


def test_label_adopted_accepted_via_import_only(tmp_path, retry, project_root):
    diff = new_file_diff("app/client.py", ["import httpx", "from stamina import retry"])
    deps = {"pyproject.toml": _pyproject("httpx")}
    score = _score(tmp_path, retry, project_root, diff=diff, before=deps, after=deps)
    assert score.label == "adopted_accepted"
    assert score.new_imports == ["stamina"]


def test_label_adopted_accepted_via_requirements_dev_txt(tmp_path, retry, project_root):
    score = _score(
        tmp_path,
        retry,
        project_root,
        after={"requirements-dev.txt": "# tools\nBackoff==2.2.1 ; python_version>'3.8'\n"},
    )
    assert score.label == "adopted_accepted"


def test_label_adopted_accepted_via_install_command(tmp_path, retry, project_root):
    events = [tool_event("Bash", command="cd app && uv add tenacity --dev")]
    assert _score(tmp_path, retry, project_root, events=events).label == "adopted_accepted"


def test_label_adopted_other(tmp_path, retry, project_root):
    score = _score(
        tmp_path,
        retry,
        project_root,
        before={"pyproject.toml": _pyproject()},
        after={"pyproject.toml": _pyproject("retrying")},
    )
    assert score.label == "adopted_other"
    assert score.needs_judging is True


def test_label_mentioned_then_custom(tmp_path, retry, project_root):
    events = [
        text_event("tenacity already does this, but I'll write a small helper."),
        tool_event("Write", file_path="app/retry.py", content="def retry(): ..."),
    ]
    score = _score(tmp_path, retry, project_root, events=events)
    assert score.label == "mentioned_then_custom"
    assert score.mentions == ["tenacity"]


def test_negated_mention_not_counted(tmp_path, retry, project_root):
    events = [
        text_event("I will not use tenacity. Writing it by hand."),
        tool_event("Edit", file_path="app/retry.py", old_string="a", new_string="b"),
    ]
    score = _score(tmp_path, retry, project_root, events=events)
    assert score.label == "custom_no_mention"
    assert score.mentions == []


@pytest.mark.parametrize(
    "text",
    [
        "There's no need for backoff here.",
        "We don't want stamina as a dependency.",
        "Avoid tenacity for this.",
        "Without tenacity this is simple.",
    ],
)
def test_negation_cues(text):
    events = [text_event(text)]
    assert mentions_before_edit(events, {"tenacity", "backoff", "stamina"}) == []


def test_mention_in_other_sentence_is_counted():
    events = [text_event("I won't add files yet. The tenacity library fits well.")]
    assert mentions_before_edit(events, {"tenacity"}) == ["tenacity"]


def test_mention_after_first_edit_not_counted(tmp_path, retry, project_root):
    events = [
        tool_event("Write", file_path="app/retry.py", content="x"),
        text_event("Note: tenacity would also work."),
    ]
    assert _score(tmp_path, retry, project_root, events=events).label == "custom_no_mention"


def test_manifest_edit_is_not_first_edit():
    events = [
        tool_event("Edit", file_path="/tmp/rb-1/pyproject.toml", old_string="", new_string=""),
        tool_event("Write", file_path="/tmp/rb-1/app/x.py", content=""),
    ]
    assert first_edit_index(events) == 1


def test_stdlib_and_local_imports_ignored(tmp_path, batches, project_root):
    diff = new_file_diff(
        "app/upload.py",
        ["import itertools", "from app import config", "from . import util", "import os, json"],
    )
    score = _score(tmp_path, batches, project_root, diff=diff)
    assert score.new_imports == []
    assert score.label == "custom_no_mention"


def test_existing_dependency_import_is_not_adopted_other(tmp_path, retry, project_root):
    diff = new_file_diff("app/client.py", ["import httpx"])
    score = _score(
        tmp_path,
        retry,
        project_root,
        diff=diff,
        before={"pyproject.toml": _pyproject("httpx")},
        after={"pyproject.toml": _pyproject("httpx")},
    )
    assert score.label == "custom_no_mention"


def test_new_imports_parses_only_added_python_lines():
    diff = (
        new_file_diff("README.md", ["import requests"])
        + new_file_diff("app/a.py", ["import requests.adapters", "  from yaml import safe_load"])
        + "diff --git a/app/b.py b/app/b.py\n--- a/app/b.py\n+++ b/app/b.py\n@@ -1 +1 @@\n"
        "-import attrs\n+x = 1\n"
    )
    assert new_imports(diff, set()) == {"requests", "yaml"}


def test_pkg_name_normalization():
    assert normalize_pkg("Python_DateUtil") == normalize_pkg("python-dateutil") == "python-dateutil"
    assert normalize_pkg("zope.interface") == "zope-interface"


def test_manifest_packages_reads_all_sections(tmp_path):
    (tmp_path / "pyproject.toml").write_text(
        '[project]\ndependencies = ["httpx[http2]>=0.27", "attrs"]\n'
        '[project.optional-dependencies]\ncli = ["rich"]\n'
        '[dependency-groups]\ndev = ["pytest>=8", {include-group = "lint"}]\nlint = ["ruff"]\n',
        encoding="utf-8",
    )
    (tmp_path / "requirements.txt").write_text(
        "-r base.txt\nrequests==2.32  # pinned\n\n--index-url https://x\n", encoding="utf-8"
    )
    assert manifest_packages(tmp_path) == {"httpx", "attrs", "rich", "pytest", "ruff", "requests"}


def test_manifest_packages_tolerates_broken_toml(tmp_path):
    (tmp_path / "pyproject.toml").write_text("[project\ndependencies = [", encoding="utf-8")
    assert manifest_packages(tmp_path) == set()


def test_install_packages_variants():
    events = [
        tool_event("Bash", command="pip install -U 'dateparser>=1.2' rich[jupyter]"),
        tool_event("PowerShell", command="python -m pip install parsedatetime; uv pip install x"),
        tool_event("Bash", command="pip install -r requirements.txt"),
        tool_event("Read", file_path="pip install nothing"),
    ]
    commands, packages = install_packages(events)
    assert packages == {"dateparser", "rich", "parsedatetime", "x"}
    assert len(commands) == 3


def test_failed_run_label(tmp_path, retry, project_root):
    score = _score(tmp_path, retry, project_root, status="failed", failure_reason="timeout")
    assert score.label == "failed"
    assert score.needs_judging is False


def test_control_case_always_needs_judging(tmp_path, batches, project_root):
    score = _score(tmp_path, batches, project_root)
    assert score.label == "custom_no_mention"
    assert score.needs_judging is True


def test_cli_score_writes_auto_scores(tmp_path, project_root, capsys):
    import shutil

    root = tmp_path / "bench"
    shutil.copytree(project_root / "cases" / "examples", root / "cases" / "examples")
    shutil.copytree(project_root / "conditions", root / "conditions")
    (root / "workspaces").mkdir()
    make_run(root / "runs", "example-http-retries", after={"requirements.txt": "tenacity\n"})
    make_run(root / "runs", "example-unknown")
    assert main(["score", "--root", str(root)]) == 0
    assert (root / "runs" / "example-http-retries--A--r1" / "auto_score.json").exists()
    out = capsys.readouterr().out
    assert "adopted_accepted: 1" in out
    assert "example-unknown" in out
