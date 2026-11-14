import shutil

from reuse_bench.cli import main
from reuse_bench.schema import Case
from reuse_bench.validation import (
    find_leaks,
    leak_tokens,
    read_workspace_texts,
    validate_all,
)
from tests.conftest import case_dict, write_yaml


def _make_root(tmp_path, project_root):
    """A minimal project root with the real conditions and no cases."""
    root = tmp_path / "root"
    shutil.copytree(project_root / "conditions", root / "conditions")
    (root / "cases" / "examples").mkdir(parents=True)
    (root / "workspaces").mkdir()
    return root


def _examples_root(tmp_path, project_root):
    """Project root with the real conditions and only the example fixtures (no real cases)."""
    root = _make_root(tmp_path, project_root)
    shutil.copytree(
        project_root / "cases" / "examples", root / "cases" / "examples", dirs_exist_ok=True
    )
    return root


def test_examples_validate_clean(tmp_path, project_root):
    report = validate_all(_examples_root(tmp_path, project_root))
    assert report.errors == []
    assert report.examples == 3
    assert report.real_reuse == 0
    assert report.real_control == 0


def test_repo_cases_validate(project_root):
    """The real cases committed in the repository must always validate (no leaks)."""
    assert validate_all(project_root).errors == []


def test_leak_tokens_include_separator_variants():
    case = Case.model_validate(case_dict())
    tokens = leak_tokens(case)
    assert {"toolkitlib", "toolkit-lib", "toolkit_lib", "toolkit.lib"} <= tokens


def test_leak_in_request_fails():
    case = Case.model_validate(case_dict(request="Use Toolkit-Lib to retry the calls."))
    leaks = find_leaks(case, {})
    assert any("request" in leak and "toolkit-lib" in leak for leak in leaks)


def test_leak_in_context_fails():
    case = Case.model_validate(case_dict(context="We already depend on toolkitlib."))
    assert any("context" in leak for leak in find_leaks(case, {}))


def test_leak_variant_in_workspace_fails():
    case = Case.model_validate(case_dict())
    leaks = find_leaks(case, {"app/x.py": "import toolkit_lib\n"})
    assert leaks == ["workspace file app/x.py mentions 'toolkit_lib'"]


def test_substring_is_not_a_leak():
    data = case_dict()
    data["ground_truth"]["accepted_tools"][0].update(
        name="re", packages=["re"], import_names=["re"]
    )
    case = Case.model_validate(data | {"request": "Retry the request when it fails."})
    assert find_leaks(case, {}) == []


def test_binary_workspace_file_skipped_not_crash(tmp_path):
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "logo.png").write_bytes(b"\x89PNG\x00\xff\xfe")
    (ws / "main.py").write_bytes(b"print('hi')\n")
    texts, skipped = read_workspace_texts(ws)
    assert texts == {"main.py": "print('hi')\n"}
    assert skipped == ["logo.png"]


def test_example_outside_examples_dir_fails(tmp_path, project_root):
    root = _make_root(tmp_path, project_root)
    write_yaml(root / "cases" / "example-sample.yaml", case_dict())
    report = validate_all(root)
    assert any("example: true" in err for err in report.errors)


def test_real_case_inside_examples_dir_fails(tmp_path, project_root):
    root = _make_root(tmp_path, project_root)
    write_yaml(root / "cases" / "examples" / "case-x.yaml", case_dict(id="case-x", example=False))
    report = validate_all(root)
    assert any("examples" in err for err in report.errors)


def test_duplicate_ids_fail(tmp_path, project_root):
    root = _make_root(tmp_path, project_root)
    write_yaml(root / "cases" / "examples" / "a.yaml", case_dict())
    write_yaml(root / "cases" / "examples" / "b.yaml", case_dict())
    report = validate_all(root)
    assert any("duplicate" in err for err in report.errors)


def test_workspace_must_exist_inside_workspaces_dir(tmp_path, project_root):
    root = _make_root(tmp_path, project_root)
    write_yaml(root / "cases" / "examples" / "a.yaml", case_dict(workspace="workspaces/missing"))
    write_yaml(
        root / "cases" / "examples" / "b.yaml", case_dict(id="example-b", workspace="../outside")
    )
    report = validate_all(root)
    assert any("workspaces/missing" in err for err in report.errors)
    assert any("../outside" in err for err in report.errors)


def test_leak_in_workspace_dir_is_reported(tmp_path, project_root):
    root = _make_root(tmp_path, project_root)
    ws = root / "workspaces" / "example-sample"
    ws.mkdir()
    (ws / "client.py").write_text("from toolkit_lib import retry\n", encoding="utf-8")
    write_yaml(
        root / "cases" / "examples" / "a.yaml", case_dict(workspace="workspaces/example-sample")
    )
    report = validate_all(root)
    assert any("client.py" in err for err in report.errors)


def test_generated_workspace_is_leak_checked(tmp_path, project_root):
    root = _make_root(tmp_path, project_root)
    stack = {"language": "python", "python_version": "3.12", "frameworks": ["toolkit-lib"]}
    write_yaml(root / "cases" / "examples" / "a.yaml", case_dict(stack=stack))
    report = validate_all(root)
    assert any("pyproject.toml" in err for err in report.errors)


def test_cli_validate_exit_codes(tmp_path, project_root, capsys):
    assert main(["validate", "--root", str(_examples_root(tmp_path, project_root))]) == 0
    out = capsys.readouterr().out
    assert "0 real cases (0 reuse, 0 control); 3 example fixtures (excluded from counts)" in out
    root = _make_root(tmp_path / "second", project_root)
    write_yaml(root / "cases" / "examples" / "a.yaml", case_dict(request="Use toolkitlib."))
    assert main(["validate", "--root", str(root)]) == 1


def test_request_starting_with_dash_fails(tmp_path, project_root):
    root = _make_root(tmp_path, project_root)
    write_yaml(root / "cases" / "examples" / "a.yaml", case_dict(request="- retry failed calls"))
    report = validate_all(root)
    assert any("request must not start with '-'" in err for err in report.errors)
