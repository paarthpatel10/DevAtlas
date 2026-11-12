"""Isolated temporary workspaces: one fresh git repository per run, outside the DevAtlas repo.

Only the case workspace (or a generated minimal project) and, for condition B, the project
instruction file are placed in it. Case YAML files and ground truth are never copied.
"""

from __future__ import annotations

import os
import shutil
import stat
import subprocess
import tempfile
from pathlib import Path

from reuse_bench.loading import minimal_workspace_files
from reuse_bench.schema import Case, Condition
from reuse_bench.validation import resolve_workspace

MANIFEST_GLOBS = ("pyproject.toml", "requirements*.txt")
DIFF_EXCLUDES = (".venv/", "__pycache__/", "*.pyc", ".pytest_cache/", "uv.lock")
INSTRUCTION_FILE_NAMES = ("CLAUDE.md", "CLAUDE.local.md")

# Local config for the scratch repository only. Hooks are pointed at an empty directory so a
# global git hook cannot modify the workspace; this is part of run isolation.
_GIT_CONFIG = {
    "user.name": "reuse-bench",
    "user.email": "reuse-bench@localhost",
    "commit.gpgsign": "false",
    "core.autocrlf": "false",
    "core.safecrlf": "false",
}


class IsolationError(Exception):
    """The workspace could not be isolated from the repository or the answer."""


def _git_env() -> dict[str, str]:
    return {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}


def _git(workspace: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=workspace,
        capture_output=True,
        env=_git_env(),
        check=True,
    )
    return result.stdout.decode("utf-8", errors="replace")


def _write_files(dest: Path, files: dict[str, str]) -> None:
    for rel, text in files.items():
        path = dest / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(text.encode("utf-8"))


def prepare_workspace(
    case: Case,
    bench_root: Path,
    condition: Condition,
    instruction_filename: str,
    repo_root: Path,
) -> Path:
    """Create and commit the starting state of one run's workspace; return its path."""
    workspace = Path(tempfile.mkdtemp(prefix="rb-")).resolve()
    try:
        repo = repo_root.resolve()
        if workspace == repo or repo in workspace.parents:
            raise IsolationError(f"temporary workspace {workspace} is inside the repository {repo}")

        if case.workspace:
            source = resolve_workspace(bench_root, case.workspace)
            if source is None:
                raise IsolationError(f"case {case.id}: workspace '{case.workspace}' not found")
            shutil.copytree(source, workspace, dirs_exist_ok=True)
        else:
            _write_files(workspace, minimal_workspace_files(case))
        if condition.project_instruction:
            _write_files(workspace, {instruction_filename: condition.project_instruction.strip()})

        _git(workspace, "init", "-q", "-b", "main")
        for key, value in _GIT_CONFIG.items():
            _git(workspace, "config", key, value)
        hooks = workspace / ".git" / "no-hooks"
        hooks.mkdir()
        _git(workspace, "config", "core.hooksPath", hooks.as_posix())
        exclude = workspace / ".git" / "info" / "exclude"
        exclude.parent.mkdir(parents=True, exist_ok=True)
        exclude.write_text("\n".join(DIFF_EXCLUDES) + "\n", encoding="utf-8")
        _git(workspace, "add", "-A")
        _git(workspace, "commit", "-q", "--allow-empty", "-m", "start")
    except BaseException:
        remove_workspace(workspace)
        raise
    return workspace


def ancestor_instruction_files(workspace: Path) -> list[str]:
    """Instruction files in parent directories that an agent might load as project context."""
    found = []
    for parent in workspace.resolve().parents:
        for name in INSTRUCTION_FILE_NAMES:
            candidate = parent / name
            if candidate.is_file():
                found.append(candidate.as_posix())
    return found


def manifest_paths(workspace: Path) -> list[Path]:
    paths: set[Path] = set()
    for pattern in MANIFEST_GLOBS:
        paths.update(p for p in workspace.glob(pattern) if p.is_file())
    return sorted(paths)


def snapshot_manifests(workspace: Path, dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    for path in manifest_paths(workspace):
        shutil.copy2(path, dest / path.name)


def final_diff(workspace: Path) -> str:
    """Everything the agent changed since the start commit, including new files."""
    _git(workspace, "add", "-A")
    return _git(workspace, "diff", "--cached", "HEAD")


def _force_remove(func, path, _exc) -> None:
    os.chmod(path, stat.S_IWRITE)
    func(path)


def remove_workspace(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path, onexc=_force_remove)
