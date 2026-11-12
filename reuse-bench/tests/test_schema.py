import pytest
from pydantic import ValidationError

from reuse_bench.loading import (
    case_hash,
    load_conditions,
    minimal_workspace_files,
)
from reuse_bench.schema import B_INSTRUCTION, Case, Condition
from tests.conftest import case_dict, write_yaml


def test_reuse_case_requires_accepted_tool():
    data = case_dict()
    data["ground_truth"]["accepted_tools"] = []
    with pytest.raises(ValidationError, match="reuse case"):
        Case.model_validate(data)


def test_control_case_rejects_accepted_tools():
    with pytest.raises(ValidationError, match="control case"):
        Case.model_validate(case_dict(kind="control"))


def test_unknown_field_rejected():
    with pytest.raises(ValidationError):
        Case.model_validate(case_dict(split="dev"))


@pytest.mark.parametrize("value", ["2026-13", "2026-10-01", "Oct 2026"])
def test_bad_date_observed_rejected(value):
    with pytest.raises(ValidationError):
        Case.model_validate(case_dict(date_observed=value))


def test_valid_case_parses():
    case = Case.model_validate(case_dict())
    assert case.kind == "reuse"
    assert case.ground_truth.accepted_tools[0].packages == ["toolkit-lib"]


def test_condition_b_text_is_verbatim(project_root):
    conditions = dict((c.id, c) for _, c in load_conditions(project_root / "conditions"))
    assert set(conditions) == {"A", "B", "C"}
    assert conditions["B"].project_instruction.strip() == B_INSTRUCTION
    assert conditions["A"].project_instruction is None
    assert conditions["A"].mcp_servers == {}
    assert B_INSTRUCTION == (
        "Before implementing any non-trivial feature, first check whether a maintained "
        "open-source library or tool already provides it. If one fits this project's stack and "
        "license, propose it and use it instead of writing custom code. If none fits, say so "
        "briefly and build it."
    )


def test_condition_rejects_unknown_id():
    with pytest.raises(ValidationError):
        Condition.model_validate({"id": "D", "name": "DevAtlas", "description": "Phase 2"})


def test_case_hash_changes_when_workspace_file_changes(tmp_path):
    case_path = write_yaml(tmp_path / "case.yaml", case_dict())
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "main.py").write_text("print('a')\n", encoding="utf-8")
    first = case_hash(case_path, ws)
    assert case_hash(case_path, ws) == first
    (ws / "main.py").write_text("print('b')\n", encoding="utf-8")
    assert case_hash(case_path, ws) != first
    assert case_hash(case_path, None) != first


def test_minimal_workspace_uses_stack():
    case = Case.model_validate(
        case_dict(stack={"language": "python", "python_version": "3.11", "frameworks": ["fastapi"]})
    )
    files = minimal_workspace_files(case)
    assert set(files) == {"pyproject.toml", "app/__init__.py"}
    assert 'requires-python = ">=3.11"' in files["pyproject.toml"]
    assert '"fastapi"' in files["pyproject.toml"]
