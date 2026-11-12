"""Deterministic dev/holdout assignment, stratified by case kind.

Within each kind, cases are ordered by sha256(f"{seed}:{case_id}"); even positions are dev and
odd positions are holdout. Splits are never set by hand. Phase 1 uses all cases; Phase 2 may
only inspect dev cases while building.
"""

from __future__ import annotations

import hashlib
from typing import Literal

from reuse_bench.schema import Case

SPLIT_SEED = "reuse-bench-2026-11-12"
Split = Literal["dev", "holdout"]


def _key(seed: str, case_id: str) -> str:
    return hashlib.sha256(f"{seed}:{case_id}".encode()).hexdigest()


def _assign(ids_by_kind: dict[str, list[str]], seed: str) -> dict[str, Split]:
    splits: dict[str, Split] = {}
    for ids in ids_by_kind.values():
        for position, case_id in enumerate(sorted(ids, key=lambda i: _key(seed, i))):
            splits[case_id] = "dev" if position % 2 == 0 else "holdout"
    return splits


def assign_splits(cases: list[Case], seed: str = SPLIT_SEED) -> dict[str, Split]:
    """Split for every real case; example fixtures never get one."""
    ids_by_kind: dict[str, list[str]] = {}
    for case in cases:
        if not case.example:
            ids_by_kind.setdefault(case.kind, []).append(case.id)
    return _assign(ids_by_kind, seed)
