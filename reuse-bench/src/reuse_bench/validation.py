"""Case validation: schema, file placement, unique ids, workspaces, and answer leaks."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from reuse_bench.loading import (
    LoadError,
    case_files,
    load_case,
    load_conditions,
    minimal_workspace_files,
)
from reuse_bench.schema import Case

MIN_REAL_REUSE = 15
MIN_REAL_CONTROL = 4
_SEPARATORS = "-_."


@dataclass
class ValidationReport:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    real_reuse: int = 0
    real_control: int = 0
    examples: int = 0

    def summary(self) -> str:
        real = self.real_reuse + self.real_control
        return (
            f"{real} real cases ({self.real_reuse} reuse, {self.real_control} control); "
            f"{self.examples} example fixtures (excluded from counts)"
        )


def _variants(token: str) -> set[str]:
    token = token.strip().lower()
    out = {token}
    if any(sep in token for sep in _SEPARATORS):
        parts = re.split(r"[-_.]", token)
        out.update(sep.join(parts) for sep in _SEPARATORS)
    return out


def leak_tokens(case: Case) -> set[str]:
    """Every name that would give the answer away, in -/_/. variants, lower-cased."""
    tokens: set[str] = set()
    for tool in case.ground_truth.accepted_tools:
        for raw in [tool.name, *tool.packages, *tool.import_names]:
            tokens |= _variants(raw)
    return {t for t in tokens if t}


def _mentions(text: str, token: str) -> bool:
    pattern = rf"(?<![A-Za-z0-9_]){re.escape(token)}(?![A-Za-z0-9_])"
    return re.search(pattern, text, flags=re.IGNORECASE) is not None


def find_leaks(case: Case, workspace_files: dict[str, str]) -> list[str]:
    tokens = sorted(leak_tokens(case))
    sources = [("request", case.request), ("context", case.context)]
    sources += [(f"workspace file {name}", text) for name, text in sorted(workspace_files.items())]
    return [
        f"{label} mentions '{token}'"
        for label, text in sources
        for token in tokens
        if _mentions(text, token)
    ]


def read_workspace_texts(workspace_dir: Path) -> tuple[dict[str, str], list[str]]:
    """Text of every workspace file; binary or non-UTF-8 files are skipped and listed."""
    texts: dict[str, str] = {}
    skipped: list[str] = []
    for path in sorted(p for p in workspace_dir.rglob("*") if p.is_file()):
        rel = path.relative_to(workspace_dir).as_posix()
        data = path.read_bytes()
        try:
            if b"\x00" in data:
                raise UnicodeDecodeError("utf-8", data, 0, 1, "binary file")
            texts[rel] = data.decode("utf-8")
        except UnicodeDecodeError:
            skipped.append(rel)
    return texts, skipped


def resolve_workspace(root: Path, workspace: str) -> Path | None:
    """The workspace directory, or None if it is absolute, outside workspaces/ or missing."""
    if Path(workspace).is_absolute():
        return None
    base = (root / "workspaces").resolve()
    path = (root / workspace).resolve()
    if base not in path.parents or not path.is_dir():
        return None
    return path


def validate_all(root: Path, allow_few: bool = False) -> ValidationReport:
    report = ValidationReport()
    try:
        load_conditions(root / "conditions")
    except LoadError as exc:
        report.errors.append(str(exc))

    examples_dir = (root / "cases" / "examples").resolve()
    seen: dict[str, str] = {}
    for path in case_files(root / "cases"):
        rel = path.relative_to(root).as_posix()
        try:
            case = load_case(path)
        except LoadError as exc:
            report.errors.append(str(exc))
            continue

        in_examples = examples_dir in path.resolve().parents
        if case.example and not in_examples:
            report.errors.append(f"{rel}: example: true cases must live in cases/examples/")
        if not case.example and in_examples:
            report.errors.append(f"{rel}: real cases must not be placed in cases/examples/")
        if case.id in seen:
            report.errors.append(f"{rel}: duplicate case id '{case.id}' (also in {seen[case.id]})")
        seen.setdefault(case.id, rel)

        if case.workspace:
            ws = resolve_workspace(root, case.workspace)
            if ws is None:
                report.errors.append(
                    f"{rel}: workspace '{case.workspace}' must be an existing directory "
                    "inside workspaces/"
                )
                texts = {}
            else:
                texts, skipped = read_workspace_texts(ws)
                report.warnings += [f"{rel}: skipped binary workspace file {s}" for s in skipped]
        else:
            texts = minimal_workspace_files(case)
        report.errors += [f"{rel}: {leak}" for leak in find_leaks(case, texts)]

        if case.example:
            report.examples += 1
        elif case.kind == "reuse":
            report.real_reuse += 1
        else:
            report.real_control += 1

    if not allow_few and (
        report.real_reuse < MIN_REAL_REUSE or report.real_control < MIN_REAL_CONTROL
    ):
        report.warnings.append(
            f"the first full run targets at least {MIN_REAL_REUSE} reuse and "
            f"{MIN_REAL_CONTROL} control cases"
        )
    return report
