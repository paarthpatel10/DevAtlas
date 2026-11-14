from reuse_bench.cli import main
from reuse_bench.schema import Case
from reuse_bench.splits import SPLIT_SEED, _assign, assign_splits
from tests.conftest import case_dict


def _ids_by_kind(n_reuse: int, n_control: int) -> dict[str, list[str]]:
    return {
        "reuse": [f"case-{i:03d}" for i in range(n_reuse)],
        "control": [f"case-{100 + i:03d}" for i in range(n_control)],
    }


def test_seed_is_fixed():
    assert SPLIT_SEED == "reuse-bench-2026-11-12"


def test_split_is_deterministic():
    assert _assign(_ids_by_kind(6, 4), SPLIT_SEED) == _assign(_ids_by_kind(6, 4), SPLIT_SEED)


def test_split_is_stratified():
    splits = _assign(_ids_by_kind(6, 4), SPLIT_SEED)
    reuse = [splits[i] for i in _ids_by_kind(6, 4)["reuse"]]
    control = [splits[i] for i in _ids_by_kind(6, 4)["control"]]
    assert reuse.count("dev") == 3 and reuse.count("holdout") == 3
    assert control.count("dev") == 2 and control.count("holdout") == 2


def test_split_odd_count_is_roughly_half():
    splits = _assign(_ids_by_kind(5, 0), SPLIT_SEED)
    assert sorted(splits.values()).count("dev") in (2, 3)


def test_split_independent_of_input_order():
    ids = _ids_by_kind(6, 4)
    reversed_ids = {kind: list(reversed(v)) for kind, v in ids.items()}
    assert _assign(ids, SPLIT_SEED) == _assign(reversed_ids, SPLIT_SEED)


def test_seed_changes_assignment():
    ids = _ids_by_kind(10, 0)
    assert _assign(ids, SPLIT_SEED) != _assign(ids, "other-seed")


def test_examples_get_no_split():
    cases = [Case.model_validate(case_dict(id=f"example-{i}")) for i in range(4)]
    assert assign_splits(cases) == {}


def test_cli_splits_without_real_cases(tmp_path, project_root, capsys):
    import shutil

    root = tmp_path / "bench"
    shutil.copytree(project_root / "cases" / "examples", root / "cases" / "examples")
    assert main(["splits", "--root", str(root)]) == 0
    assert "no real cases" in capsys.readouterr().out


def test_cli_splits_runs_on_repo(project_root):
    assert main(["splits", "--root", str(project_root)]) == 0
