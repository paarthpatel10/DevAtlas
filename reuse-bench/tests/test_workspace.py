import subprocess
from pathlib import Path

import pytest

from reuse_bench import workspace as ws_mod
from reuse_bench.loading import load_case, load_conditions
from reuse_bench.schema import Case
from reuse_bench.workspace import (
    IsolationError,
    ancestor_instruction_files,
    final_diff,
    prepare_workspace,
    remove_workspace,
    snapshot_manifests,
)
from tests.conftest import case_dict

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def conditions(project_root):
    return {c.id: c for _, c in load_conditions(project_root / "conditions")}


@pytest.fixture
def retry_case(project_root):
    return load_case(project_root / "cases" / "examples" / "example-http-retries.yaml")


@pytest.fixture
def made():
    created: list[Path] = []
    yield created
    for path in created:
        remove_workspace(path)


def _files(root: Path) -> set[str]:
    return {
        p.relative_to(root).as_posix()
        for p in root.rglob("*")
        if p.is_file() and ".git" not in p.relative_to(root).parts
    }


def _git(ws: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=ws, capture_output=True, text=True, check=True).stdout


def test_workspace_outside_repo_and_git_committed(retry_case, conditions, project_root, made):
    ws = prepare_workspace(retry_case, project_root, conditions["A"], "CLAUDE.md", REPO_ROOT)
    made.append(ws)
    assert REPO_ROOT.resolve() not in ws.resolve().parents
    assert _files(ws) == {"pyproject.toml", "app/__init__.py"}
    assert _git(ws, "status", "--porcelain") == ""
    assert _git(ws, "log", "--format=%s") == "start\n"
    assert _git(ws, "rev-parse", "--show-toplevel").strip() == ws.resolve().as_posix()


def test_case_yaml_and_ground_truth_never_copied(retry_case, conditions, project_root, made):
    ws = prepare_workspace(retry_case, project_root, conditions["B"], "CLAUDE.md", REPO_ROOT)
    made.append(ws)
    for rel in _files(ws):
        text = (ws / rel).read_text(encoding="utf-8").lower()
        assert "ground_truth" not in text
        for token in ("tenacity", "backoff", "stamina"):
            assert token not in text


def test_condition_b_writes_instruction_file_and_commits_it(
    retry_case, conditions, project_root, made
):
    ws = prepare_workspace(retry_case, project_root, conditions["B"], "CLAUDE.md", REPO_ROOT)
    made.append(ws)
    assert "maintained open-source" in (ws / "CLAUDE.md").read_text(encoding="utf-8")
    assert final_diff(ws) == ""


def test_condition_a_and_b_workspaces_differ_only_by_instruction_file(
    retry_case, conditions, project_root, made
):
    a = prepare_workspace(retry_case, project_root, conditions["A"], "CLAUDE.md", REPO_ROOT)
    b = prepare_workspace(retry_case, project_root, conditions["B"], "CLAUDE.md", REPO_ROOT)
    made += [a, b]
    assert _files(b) - _files(a) == {"CLAUDE.md"}
    for rel in _files(a):
        assert (a / rel).read_bytes() == (b / rel).read_bytes()


def test_case_workspace_is_copied(tmp_path, conditions, made):
    bench = tmp_path / "bench"
    src = bench / "workspaces" / "example-ws"
    (src / "pkg").mkdir(parents=True)
    (src / "pkg" / "mod.py").write_bytes(b"x = 1\n")
    (src / "requirements.txt").write_bytes(b"httpx\n")
    case = Case.model_validate(case_dict(workspace="workspaces/example-ws"))
    ws = prepare_workspace(case, bench, conditions["A"], "CLAUDE.md", REPO_ROOT)
    made.append(ws)
    assert _files(ws) == {"pkg/mod.py", "requirements.txt"}


def test_diff_includes_new_untracked_file_and_excludes_venv(
    retry_case, conditions, project_root, made
):
    ws = prepare_workspace(retry_case, project_root, conditions["A"], "CLAUDE.md", REPO_ROOT)
    made.append(ws)
    (ws / "app" / "retry.py").write_text("def retry():\n    pass\n", encoding="utf-8")
    (ws / ".venv" / "lib").mkdir(parents=True)
    (ws / ".venv" / "lib" / "junk.py").write_text("junk = 1\n", encoding="utf-8")
    (ws / "uv.lock").write_text("lock\n", encoding="utf-8")
    diff = final_diff(ws)
    assert "app/retry.py" in diff
    assert "+def retry():" in diff
    assert ".venv" not in diff
    assert "uv.lock" not in diff


def test_manifest_snapshot_copies_requirements_variants(tmp_path):
    ws = tmp_path / "ws"
    ws.mkdir()
    for name in ("pyproject.toml", "requirements.txt", "requirements-dev.txt", "setup.cfg"):
        (ws / name).write_text(name, encoding="utf-8")
    dest = tmp_path / "manifest_before"
    snapshot_manifests(ws, dest)
    assert {p.name for p in dest.iterdir()} == {
        "pyproject.toml",
        "requirements.txt",
        "requirements-dev.txt",
    }


def test_workspace_inside_repo_raises(tmp_path, retry_case, conditions, project_root, monkeypatch):
    repo = tmp_path / "repo"
    inside = repo / "rb-inside"
    monkeypatch.setattr(
        ws_mod.tempfile, "mkdtemp", lambda prefix="": str(inside.mkdir(parents=True) or inside)
    )
    with pytest.raises(IsolationError, match="inside"):
        prepare_workspace(retry_case, project_root, conditions["A"], "CLAUDE.md", repo)
    assert not inside.exists()


def test_ancestor_instruction_files_detected(tmp_path):
    (tmp_path / "CLAUDE.md").write_text("x", encoding="utf-8")
    nested = tmp_path / "a" / "b"
    nested.mkdir(parents=True)
    found = ancestor_instruction_files(nested)
    assert (tmp_path / "CLAUDE.md").as_posix() in found
