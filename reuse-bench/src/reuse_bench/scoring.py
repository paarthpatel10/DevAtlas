"""Automatic first-pass labels from the diff, manifests and event stream.

Labels are provisional. Text matches are hints only, so every label except `adopted_accepted`
(and `failed`) goes to blind human judging. Run contents are untrusted data: they are parsed
with regular expressions and never executed.
"""

from __future__ import annotations

import json
import re
import shlex
import sys
import tomllib
from pathlib import Path

from reuse_bench.loading import minimal_workspace_files
from reuse_bench.runner import load_meta
from reuse_bench.schema import AutoScore, Case
from reuse_bench.validation import leak_tokens, resolve_workspace

EDIT_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit"}
SHELL_TOOLS = {"Bash", "PowerShell"}
NEGATION_CUES = (r"\bnot\b", r"n't\b", r"\bno\b", r"\bnever\b", r"\bwithout\b", r"\bavoid\b")
_INSTALL = re.compile(
    r"^\s*(?:uv\s+add|uv\s+pip\s+install|pip3?\s+install|python3?\s+-m\s+pip\s+install"
    r"|py\s+-m\s+pip\s+install|poetry\s+add)\b(.*)$",
    re.IGNORECASE,
)
_VALUE_OPTIONS = {
    "-r", "--requirement", "-c", "--constraint", "-i", "--index-url", "--extra-index-url",
    "--group", "--optional", "-e", "--editable", "--python", "-p",
}  # fmt: skip
_PKG = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._-]*)")
_IMPORT = re.compile(r"^\s*import\s+(.+)$")
_FROM = re.compile(r"^\s*from\s+([A-Za-z_][\w.]*)\s+import\b")


def normalize_pkg(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _requirement_name(spec: str) -> str | None:
    match = _PKG.match(spec.strip())
    return normalize_pkg(match.group(1)) if match else None


def is_manifest(path: str) -> bool:
    name = Path(path.replace("\\", "/")).name
    return name == "pyproject.toml" or (name.startswith("requirements") and name.endswith(".txt"))


def manifest_packages(directory: Path) -> set[str]:
    """Dependency names (normalized) declared in pyproject.toml and requirements*.txt."""
    specs: list[str] = []
    pyproject = directory / "pyproject.toml"
    if pyproject.is_file():
        try:
            data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
        except (tomllib.TOMLDecodeError, UnicodeDecodeError):
            data = {}
        project = data.get("project") or {}
        specs += project.get("dependencies") or []
        for group in (project.get("optional-dependencies") or {}).values():
            specs += group
        for group in (data.get("dependency-groups") or {}).values():
            specs += [item for item in group if isinstance(item, str)]
        poetry = ((data.get("tool") or {}).get("poetry") or {}).get("dependencies") or {}
        specs += [name for name in poetry if name.lower() != "python"]
    for req in sorted(directory.glob("requirements*.txt")):
        for line in req.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.split("#", 1)[0].strip()
            if line and not line.startswith("-"):
                specs.append(line)
    return {name for spec in specs if isinstance(spec, str) and (name := _requirement_name(spec))}


def load_events(run_dir: Path) -> list[dict]:
    events = []
    path = run_dir / "events.jsonl"
    if not path.exists():
        return events
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(event, dict):
            events.append(event)
    return events


def _blocks(event: dict) -> list[dict]:
    if event.get("type") != "assistant":
        return []
    content = (event.get("message") or {}).get("content") or []
    return [b for b in content if isinstance(b, dict)]


def _install_args(rest: str) -> set[str]:
    try:
        args = shlex.split(rest)
    except ValueError:
        args = rest.split()
    packages, skip_next = set(), False
    for arg in args:
        if skip_next:
            skip_next = False
            continue
        if arg in _VALUE_OPTIONS:
            skip_next = True
            continue
        if arg.startswith("-") or "/" in arg or "\\" in arg or arg.endswith(".whl"):
            continue
        if name := _requirement_name(arg):
            packages.add(name)
    return packages


def install_packages(events: list[dict]) -> tuple[list[str], set[str]]:
    """Install commands found in shell tool calls, and the package names they install."""
    commands: list[str] = []
    packages: set[str] = set()
    for event in events:
        for block in _blocks(event):
            if block.get("type") != "tool_use" or block.get("name") not in SHELL_TOOLS:
                continue
            command = str((block.get("input") or {}).get("command") or "")
            found = False
            for segment in re.split(r"&&|\|\||;|\||\n", command):
                match = _INSTALL.match(segment)
                if match:
                    found = True
                    packages |= _install_args(match.group(1))
            if found:
                commands.append(command)
    return commands, packages


def new_imports(diff: str, local_names: set[str]) -> set[str]:
    """Top-level third-party modules imported on added lines of changed Python files."""
    found: set[str] = set()
    current: str | None = None
    for line in diff.splitlines():
        if line.startswith("+++ "):
            target = line[4:].strip()
            current = target[2:] if target.startswith("b/") else None
            continue
        if not line.startswith("+") or current is None or not current.endswith(".py"):
            continue
        code = line[1:]
        names: list[str] = []
        if match := _FROM.match(code):
            names = [match.group(1)]
        elif match := _IMPORT.match(code):
            names = [part.strip().split()[0] for part in match.group(1).split(",") if part.strip()]
        for name in names:
            top = name.split(".")[0]
            if top and top not in sys.stdlib_module_names and top != "__future__":
                found.add(top)
    return {name for name in found if name not in local_names}


def _server_key(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "_", name.lower())


def mcp_tool_calls(events: list[dict], servers: list[str]) -> int:
    """Calls to the given MCP servers; tool names look like mcp__<server>__<tool>."""
    wanted = {_server_key(s) for s in servers}
    calls = 0
    for event in events:
        for block in _blocks(event):
            name = str(block.get("name") or "")
            if block.get("type") == "tool_use" and name.startswith("mcp__"):
                if _server_key(name[5:].split("__", 1)[0]) in wanted:
                    calls += 1
    return calls


def first_edit_index(events: list[dict]) -> int | None:
    """Index of the first event that edits a non-manifest file."""
    for index, event in enumerate(events):
        for block in _blocks(event):
            if block.get("type") == "tool_use" and block.get("name") in EDIT_TOOLS:
                inputs = block.get("input") or {}
                path = str(inputs.get("file_path") or inputs.get("notebook_path") or "")
                if not is_manifest(path):
                    return index
    return None


def _is_negated(prefix: str) -> bool:
    return any(re.search(cue, prefix, flags=re.IGNORECASE) for cue in NEGATION_CUES)


def mentions_before_edit(events: list[dict], tokens: set[str]) -> list[str]:
    """Tokens named in assistant text before the first source edit, ignoring negated mentions."""
    stop = first_edit_index(events)
    upto = events if stop is None else events[:stop]
    found: set[str] = set()
    for event in upto:
        for block in _blocks(event):
            if block.get("type") != "text":
                continue
            for sentence in re.split(r"(?<=[.!?])\s+|\n", str(block.get("text") or "")):
                for token in tokens:
                    pattern = rf"(?<![A-Za-z0-9_]){re.escape(token)}(?![A-Za-z0-9_])"
                    for match in re.finditer(pattern, sentence, flags=re.IGNORECASE):
                        if not _is_negated(sentence[: match.start()]):
                            found.add(token)
    return sorted(found)


def local_module_names(case: Case, bench_root: Path, diff: str) -> set[str]:
    names: set[str] = set()
    if case.workspace and (source := resolve_workspace(bench_root, case.workspace)):
        names |= {p.stem if p.suffix == ".py" else p.name for p in source.iterdir()}
    else:
        names |= {Path(rel).parts[0].removesuffix(".py") for rel in minimal_workspace_files(case)}
    for line in diff.splitlines():
        if line.startswith("+++ b/"):
            names.add(Path(line[6:].strip()).parts[0].removesuffix(".py"))
    return names


def score_run(run_dir: Path, case: Case, bench_root: Path) -> AutoScore:
    meta = load_meta(run_dir)
    if meta.exit_status == "failed":
        return AutoScore(run_id=meta.run_id, label="failed", needs_judging=False)

    events = load_events(run_dir)
    diff = (run_dir / "diff.patch").read_text(encoding="utf-8", errors="replace")
    before = manifest_packages(run_dir / "manifest_before")
    after = manifest_packages(run_dir / "manifest_after")
    commands, installed = install_packages(events)
    added = sorted((after - before) | (installed - before))
    imports = sorted(
        name
        for name in new_imports(diff, local_module_names(case, bench_root, diff))
        if normalize_pkg(name) not in before
    )
    accepted_pkgs = {normalize_pkg(p) for t in case.ground_truth.accepted_tools for p in t.packages}
    accepted_imports = {i.lower() for t in case.ground_truth.accepted_tools for i in t.import_names}
    mentions = mentions_before_edit(events, leak_tokens(case))

    if set(added) & accepted_pkgs or {i.lower() for i in imports} & accepted_imports:
        label = "adopted_accepted"
    elif added or imports:
        label = "adopted_other"
    elif mentions:
        label = "mentioned_then_custom"
    else:
        label = "custom_no_mention"
    return AutoScore(
        run_id=meta.run_id,
        label=label,
        added_packages=added,
        new_imports=imports,
        install_commands=commands,
        mentions=mentions,
        needs_judging=label not in ("adopted_accepted", "failed"),
    )
