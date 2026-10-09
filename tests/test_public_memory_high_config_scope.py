from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from benchmarks.public_longmemeval import QueryInput, RuntimeCase
from benchmarks.public_memory_high_config_scope import scope_plan
from benchmarks.public_memory_pilot import _hash
from doppel_memory.models import MemoryScope


@pytest.mark.parametrize("ordinal", [2, 3])
def test_scope_plan_keeps_frozen_policy_and_separate_quality_contract(ordinal):
    runtime = RuntimeCase(
        "owner",
        (),
        QueryInput("owner", "natural query", datetime(2024, 1, 1, tzinfo=UTC)),
    )
    schema = {"plan": {"source": {"relation_names": ["REL"]}}, "definitions": []}
    scorer = SimpleNamespace(report=lambda: {"name": "fake", "version": "1"})
    plan = scope_plan(
        {"dataset": "sha"},
        runtime,
        MemoryScope(user_id="owner", agent_id="agent"),
        schema,
        "corpus",
        {},
        scorer,
        ordinal,
        {"plan_fingerprint": "fixed-batch"},
    )
    assert plan["scope_ordinal"] == ordinal
    assert plan["batch_plan_fingerprint"] == "fixed-batch"
    assert plan["item_limit"] == 20 and plan["context_byte_limit"] == 24000
    assert sum(s["max_calls"] for s in plan["stages"].values()) == 5
    assert plan["execution_contract"] == "doppel.high-config-execution-contract.v2"
    assert not plan["publication_ready"]
    assert plan["plan_fingerprint"] == _hash(
        {k: v for k, v in plan.items() if k != "plan_fingerprint"}
    )
    assert "reference_answer" not in str(plan)


def test_scope_outside_fixed_batch_rejected_before_other_inputs():
    for ordinal in [1, 4, -1]:
        with pytest.raises(ValueError):
            scope_plan({}, None, None, {}, "", {}, None, ordinal, {})
