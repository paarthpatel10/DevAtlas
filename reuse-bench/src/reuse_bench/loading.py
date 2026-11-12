"""Load cases and conditions from YAML, hash them, and generate minimal workspaces."""

from __future__ import annotations

import hashlib
from pathlib import Path

import yaml
from pydantic import ValidationError

from reuse_bench.schema import Case, Condition


class LoadError(Exception):
    """A case or condition file could not be read or did not match the schema."""


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _workspace_files(workspace_dir: Path) -> list[Path]:
    return sorted(
        (p for p in workspace_dir.rglob("*") if p.is_file()),
        key=lambda p: p.relative_to(workspace_dir).as_posix(),
    )


def case_hash(case_path: Path, workspace_dir: Path | None) -> str:
    """sha256 over the case YAML bytes plus every workspace file's relative path and bytes."""
    digest = hashlib.sha256()
    digest.update(case_path.read_bytes())
    if workspace_dir is not None:
        for path in _workspace_files(workspace_dir):
            digest.update(
                b"\0" + path.relative_to(workspace_dir).as_posix().encode("utf-8") + b"\0"
            )
            digest.update(path.read_bytes())
    return digest.hexdigest()


def _read_yaml(path: Path) -> dict:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, yaml.YAMLError) as exc:
        raise LoadError(f"{path}: cannot read YAML ({exc})") from exc
    if not isinstance(data, dict):
        raise LoadError(f"{path}: expected a mapping at the top level")
    return data


def _format_errors(path: Path, exc: ValidationError) -> str:
    parts = []
    for err in exc.errors():
        field = ".".join(str(loc) for loc in err["loc"]) or "(case)"
        parts.append(f"{field}: {err['msg']}")
    return f"{path}: " + "; ".join(parts)


def load_case(path: Path) -> Case:
    try:
        return Case.model_validate(_read_yaml(path))
    except ValidationError as exc:
        raise LoadError(_format_errors(path, exc)) from exc


def case_files(cases_dir: Path) -> list[Path]:
    """All case YAML files under cases_dir, skipping templates (names starting with '_')."""
    return sorted(p for p in cases_dir.rglob("*.yaml") if not p.name.startswith("_"))


def load_cases(cases_dir: Path) -> list[tuple[Path, Case]]:
    loaded = [(path, load_case(path)) for path in case_files(cases_dir)]
    return sorted(loaded, key=lambda item: item[1].id)


def load_conditions(conditions_dir: Path) -> list[tuple[Path, Condition]]:
    loaded = []
    for path in sorted(conditions_dir.glob("*.yaml")):
        try:
            loaded.append((path, Condition.model_validate(_read_yaml(path))))
        except ValidationError as exc:
            raise LoadError(_format_errors(path, exc)) from exc
    return sorted(loaded, key=lambda item: item[1].id)


def minimal_workspace_files(case: Case) -> dict[str, str]:
    """The starter project used when a case has no workspace of its own."""
    python_version = case.stack.python_version or "3.12"
    deps = ", ".join(f'"{name}"' for name in case.stack.frameworks)
    pyproject = (
        "[project]\n"
        'name = "app"\n'
        'version = "0.1.0"\n'
        f'requires-python = ">={python_version}"\n'
        f"dependencies = [{deps}]\n"
    )
    return {"pyproject.toml": pyproject, "app/__init__.py": ""}
