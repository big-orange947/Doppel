from __future__ import annotations

import pytest

from doppel_memory.bounded_selection import BoundedTopKSelector
from doppel_memory.reference_selection import ReferenceTopKSelector
from tests.test_reference_selection import Model
from tests.test_source_aware_rerank import candidates


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "selected", [[], ["candidate-1"], ["candidate-2", "candidate-0"]]
)
async def test_upper_bound_no_fabricated_tail_or_scores(selected):
    model = Model({"selected_ids": selected})
    selector = BoundedTopKSelector(model)
    result = await selector.rerank("generic", candidates(), limit=2)
    assert len(result) == len(selected)
    assert selector.last_selection.selected_ids == tuple(selected)
    assert len(selector.last_selection.unranked_ids) == 3 - len(selected)
    assert (
        model.requests[0].output_schema["properties"]["selected_ids"]["minItems"] == 0
    )
    assert "UPPER BOUND" in model.requests[0].instructions


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "selected",
    [
        ["candidate-0", "candidate-1", "candidate-2"],
        ["candidate-0", "candidate-0"],
        ["not-authorized"],
    ],
)
async def test_upper_bound_does_not_relax_identity_unique_or_maximum(selected):
    model = Model({"selected_ids": selected})
    with pytest.raises(ValueError):
        await BoundedTopKSelector(model).rerank("generic", candidates(), limit=2)
    assert len(model.requests) == 1


@pytest.mark.asyncio
async def test_exact_contract_still_rejects_short_output():
    with pytest.raises(ValueError):
        await ReferenceTopKSelector(Model({"selected_ids": ["candidate-1"]})).rerank(
            "generic", candidates(), limit=2
        )


def test_remaining_two_budget_and_preserved_exact_failure(tmp_path, monkeypatch):
    import json

    from benchmarks import public_memory_bounded_topk_diagnostic as runner

    failure = tmp_path / "exact-failed.json"
    failure.write_text(
        json.dumps(
            {
                "status": "failed",
                "stopped_stage": "source-selection",
                "usage": {
                    "selector": {
                        "attempts_reserved": 1,
                        "reported_tokens": {"total_tokens": 19378},
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(runner, "FAILED_EXACT", failure)
    monkeypatch.setattr(
        runner,
        "make_plan",
        lambda *args: {
            "plan_fingerprint": "old",
            "stages": {
                name: {"max_calls": 3} for name in ("selector", "reader", "judge")
            },
            "source_sha256": {},
        },
    )
    plan = runner.bounded_plan({}, [], "synthetic")
    assert plan["cases"] == ["gpt4_ec93e27f", "gpt4_2f8be40d"]
    assert sum(s["max_calls"] for s in plan["stages"].values()) == 8
    assert plan["failed_exact_spend"] == {"calls": 1, "tokens": 19378}
    assert plan["selection_cardinality"] == "upper-bound-not-quota"
