from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from reuse_bench.adapters.base import AgentAdapter
from reuse_bench.schema import Limits, RunMeta
from tests.fakes import FakeAdapter


def test_fake_adapter_satisfies_protocol():
    assert isinstance(FakeAdapter(), AgentAdapter)


def test_run_meta_requires_hashes_and_records_limits():
    now = datetime.now(UTC)
    meta = RunMeta(
        run_id="case-001--A--r1",
        case_id="case-001",
        case_hash="a" * 64,
        condition_id="A",
        condition_hash="b" * 64,
        repeat=1,
        order_seed=1,
        order_position=0,
        limits=Limits(),
        harness_commit=None,
        example=False,
        pilot=False,
        agent="fake",
        agent_version=None,
        model=None,
        exit_status="completed",
        failure_reason=None,
        cost_usd=None,
        usage=None,
        num_turns=None,
        permission_denials=[],
        isolation={},
        started_at=now,
        ended_at=now,
    )
    assert meta.limits.max_turns == 30
    assert meta.limits.timeout_s == 900
    with pytest.raises(ValidationError):
        RunMeta.model_validate(meta.model_dump() | {"exit_status": "crashed"})
