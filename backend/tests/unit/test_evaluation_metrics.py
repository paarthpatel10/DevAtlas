import pytest

from app.config import BACKEND_DIR
from app.services.evaluation import hit_at_k, load_benchmark, precision_at_k, reciprocal_rank


def test_reciprocal_rank_case_insensitive():
    assert reciprocal_rank(["a/x", "b/y"], {"B/Y"}) == 0.5
    assert reciprocal_rank(["a/x"], {"c/z"}) == 0.0


def test_hit_at_k():
    assert hit_at_k(["a", "b", "c"], {"c"}, 2) is False
    assert hit_at_k(["a", "b", "c"], {"c"}, 3) is True


def test_precision_at_k_uses_k_as_denominator():
    assert precision_at_k(["a", "b"], {"a"}, 5) == pytest.approx(0.2)


def test_benchmark_file_is_valid_and_uses_curated_repos():
    import json

    snapshot_names = {
        json.loads(p.read_text(encoding="utf-8"))["full_name"].lower()
        for p in (BACKEND_DIR / "data" / "seed_snapshot").glob("*.json")
    }
    cases = load_benchmark(BACKEND_DIR / "eval" / "benchmark.yaml")
    assert len(cases) == 15
    assert len({c.id for c in cases}) == 15
    for case in cases:
        assert case.expected, case.id
        missing = {e.lower() for e in case.expected} - snapshot_names
        assert not missing, (case.id, missing)
