"""Ranking primitives: ranked hits and Reciprocal Rank Fusion (spec 6.3).

RRF(d) = sum over lists r of 1 / (k + rank_r(d)). Scores are for ordering only; they are
not calibrated probabilities and are never shown as a "match percentage".
"""

import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class RankedHit:
    repository_id: uuid.UUID
    rank: int  # 1-based
    score: float
    chunk_id: uuid.UUID | None = None


@dataclass(frozen=True)
class FusedHit:
    repository_id: uuid.UUID
    score: float
    ranks: dict[str, int | None]


def rrf_fuse(rankings: Mapping[str, Sequence[uuid.UUID]], k: int = 60) -> list[FusedHit]:
    if k <= 0:
        raise ValueError("RRF k must be positive")
    ranks: dict[uuid.UUID, dict[str, int | None]] = {}
    for name, ids in rankings.items():
        for position, repo_id in enumerate(ids, start=1):
            entry = ranks.setdefault(repo_id, dict.fromkeys(rankings, None))
            if entry[name] is None:
                entry[name] = position
    fused = [
        FusedHit(
            repository_id=repo_id,
            score=sum(1.0 / (k + r) for r in per_list.values() if r is not None),
            ranks={name: per_list[name] for name in rankings},
        )
        for repo_id, per_list in ranks.items()
    ]

    def best_rank(hit: FusedHit) -> int:
        return min(r for r in hit.ranks.values() if r is not None)

    fused.sort(key=lambda h: (-h.score, best_rank(h), str(h.repository_id)))
    return fused
