from __future__ import annotations

import asyncio

import pytest

from doppel_memory.models import MemoryIsolationError
from doppel_memory.reference_selection import (
    ReferenceTopKSelector,
    TopKSelectionConfig,
    TopKSelectionOutput,
)
from tests.test_source_aware_rerank import candidates


class Model:
    name, version = "fake-selection", "1"

    def __init__(self, output=None):
        self.output = (
            output
            if output is not None
            else {"selected_ids": ["candidate-2", "candidate-0"]}
        )
        self.requests = []

    async def generate(self, request):
        self.requests.append(request)
        return self.output


@pytest.mark.asyncio
async def test_only_selected_originals_returned_remainder_explicitly_unranked():
    original = candidates()
    snapshots = {c.memory_id: c.model_dump(mode="json") for c in original}
    model = Model()
    selector = ReferenceTopKSelector(model)
    selected = await selector.rerank("generic", original, limit=2)
    assert [c.memory_id for c in selected] == [
        original[2].memory_id,
        original[0].memory_id,
    ]
    assert all(c.model_dump(mode="json") == snapshots[c.memory_id] for c in selected)
    assert selector.last_selection.unranked_ids == ("candidate-1",)
    assert not hasattr(selector.last_selection, "scores")
    assert "private-" not in model.requests[0].model_dump_json()
    schema = model.requests[0].output_schema["properties"]["selected_ids"]
    assert schema["minItems"] == schema["maxItems"] == 2
    assert schema["uniqueItems"] is True and len(schema["items"]["enum"]) == 3


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "output",
    [
        {"selected_ids": []},
        {"selected_ids": ["candidate-0"]},
        {"selected_ids": ["candidate-0", "candidate-0"]},
        {"selected_ids": ["candidate-0", "invented"]},
        {"selected_ids": ["candidate-0", "candidate-1", "candidate-2"]},
        {"selected_ids": [0, 1]},
        {"selected_ids": ["candidate-0", "candidate-1"], "answer": "invented"},
        {"ordered_ids": ["candidate-0", "candidate-1"]},
    ],
)
async def test_invalid_output_not_repaired_truncated_or_retried(output):
    model = Model(output)
    selector = ReferenceTopKSelector(model)
    with pytest.raises(ValueError):
        await selector.rerank("generic", candidates(), limit=2)
    assert len(model.requests) == 1 and selector.last_selection is None


@pytest.mark.asyncio
async def test_empty_no_call_short_pool_explicit_smaller_count():
    model = Model({"selected_ids": ["candidate-0"]})
    selector = ReferenceTopKSelector(model)
    assert await selector.rerank("generic", [], limit=20) == []
    assert not model.requests
    assert len(await selector.rerank("generic", candidates()[:1], limit=20)) == 1
    assert model.requests[0].input["select_count"] == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("limit", [0, -1, 81, True, 1.5])
async def test_bad_limit_stops_before_call(limit):
    model = Model()
    with pytest.raises(ValueError):
        await ReferenceTopKSelector(model).rerank("generic", candidates(), limit=limit)
    assert not model.requests


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "config",
    [TopKSelectionConfig(max_candidates=2), TopKSelectionConfig(max_input_chars=1)],
)
async def test_input_budget_stops_before_call(config):
    model = Model()
    with pytest.raises(ValueError):
        await ReferenceTopKSelector(model, config).rerank(
            "generic", candidates(), limit=2
        )
    assert not model.requests


@pytest.mark.asyncio
async def test_scope_and_duplicate_guards():
    model = Model()
    value = candidates()
    value[0].scope = None
    with pytest.raises(MemoryIsolationError):
        await ReferenceTopKSelector(model).rerank("generic", value, limit=2)
    value = candidates()
    with pytest.raises(ValueError, match="duplicate"):
        await ReferenceTopKSelector(model).rerank(
            "generic", [value[0], value[0]], limit=2
        )
    assert not model.requests


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["request", "identity"])
async def test_model_mutation_rejected(change):
    class Mutated(Model):
        async def generate(self, request):
            if change == "request":
                request.input["items"].clear()
            else:
                self.version = "changed"
            return self.output

    value = candidates()
    with pytest.raises(ValueError, match="changed"):
        await ReferenceTopKSelector(Mutated()).rerank("generic", value, limit=2)
    assert len(value) == 3


@pytest.mark.asyncio
async def test_timeout_no_retry_and_schema_model_output():
    class Slow(Model):
        async def generate(self, request):
            self.requests.append(request)
            await asyncio.sleep(1)

    model = Slow()
    with pytest.raises(TimeoutError):
        await ReferenceTopKSelector(
            model, TopKSelectionConfig(timeout_seconds=0.001)
        ).rerank("generic", candidates(), limit=2)
    assert len(model.requests) == 1
    parsed = Model(TopKSelectionOutput(selected_ids=["candidate-0", "candidate-1"]))
    assert (
        len(
            await ReferenceTopKSelector(parsed).rerank("generic", candidates(), limit=2)
        )
        == 2
    )


@pytest.mark.asyncio
async def test_previous_79_id_response_is_not_a_top20_success():
    value = candidates()
    pool = [
        value[i % 3].model_copy(update={"memory_id": f"m-{i}"}, deep=True)
        for i in range(80)
    ]
    model = Model({"selected_ids": [f"candidate-{i}" for i in range(79)]})
    with pytest.raises(ValueError):
        await ReferenceTopKSelector(model).rerank("generic", pool, limit=20)
