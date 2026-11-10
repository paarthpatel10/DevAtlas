import uuid

import pytest

from app.services.ranking import rrf_fuse


def uuids(n: int) -> list[uuid.UUID]:
    return [uuid.UUID(int=i + 1) for i in range(n)]


def test_rrf_combines_lists():
    a, b, c = uuids(3)
    fused = rrf_fuse({"keyword": [a, b], "semantic": [b, c]}, k=60)
    assert [f.repository_id for f in fused] == [b, a, c]
    assert fused[0].score == pytest.approx(1 / 62 + 1 / 61)
    assert fused[1].score == pytest.approx(1 / 61)
    assert fused[1].ranks == {"keyword": 1, "semantic": None}
    assert fused[0].ranks == {"keyword": 2, "semantic": 1}


def test_rrf_tie_break_is_deterministic():
    a, b = uuids(2)
    # Equal scores and equal best ranks: ordered by id string.
    first = rrf_fuse({"keyword": [b], "semantic": [a]}, k=60)
    second = rrf_fuse({"semantic": [a], "keyword": [b]}, k=60)
    assert [f.repository_id for f in first] == [a, b]
    assert [f.repository_id for f in second] == [a, b]


def test_rrf_k_changes_scores():
    (a,) = uuids(1)
    assert rrf_fuse({"keyword": [a]}, k=10)[0].score == pytest.approx(1 / 11)


def test_rrf_empty_lists():
    assert rrf_fuse({"keyword": [], "semantic": []}) == []


@pytest.mark.parametrize("k", [0, -1])
def test_rrf_rejects_non_positive_k(k):
    with pytest.raises(ValueError):
        rrf_fuse({"keyword": []}, k=k)
