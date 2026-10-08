"""Synthetic strict cache reuse and five-call bounds; no live API."""

import json
from copy import deepcopy
from dataclasses import replace

import pytest

from benchmarks import public_memory_packing_reader as module
from benchmarks.public_memory_answer_comparison import _request_sha256, _StageExecutor
from benchmarks.public_memory_expansion import config
from benchmarks.public_memory_pilot import _hash
from benchmarks.public_memory_reader_v2 import ReaderV2Output, build_request
from benchmarks.public_memory_recovery import cache_inventory
from benchmarks.public_memory_runtime import DurableCallLedger, PilotStructuredModel
from tests.test_public_memory_answer_comparison import RecordingFactory
from tests.test_public_memory_expansion import setup


def respond(request):
    return {
        "answer": "Tuesday"
        if len(request.input["context_items"]) == 1
        else "New answer",
        "abstained": False,
        "cited_memory_ids": [request.input["context_items"][0]["memory_id"]],
        "derived": None,
    }


async def fixture(tmp_path, *, seed=True):
    _, _, _, baseline = setup()
    cache = tmp_path / "parent-cache"
    cache.mkdir()
    parent = {
        "plan": {"reader_config": config(2048).model_dump(mode="json")},
        "answers": {"rows": []},
    }
    if seed:
        ledger = DurableCallLedger(
            tmp_path / "parent-usage.sqlite3",
            budget_id="synthetic-parent",
            max_calls=30,
        )
        factory = RecordingFactory(respond)
        model = PilotStructuredModel(
            factory(config(2048), "SYNTHETIC", ledger.observe_usage),
            ledger=ledger,
            cache_dir=cache,
        )
        stage = _StageExecutor(model, ledger, ReaderV2Output, cache_only=False)
    try:
        for row in baseline:
            output = (
                (await stage.execute(build_request(row), row.index))[0]
                if seed
                else ReaderV2Output.model_validate(respond(build_request(row)))
            )
            parent["answers"]["rows"].append(
                {
                    "index": row.index,
                    "case_id": row.case_id,
                    "profile": row.profile,
                    "reader": {
                        "status": "completed",
                        "request_sha256": _request_sha256(build_request(row)),
                        "output": output.model_dump(mode="json"),
                    },
                }
            )
    finally:
        if seed:
            ledger.close()
    rows = [
        replace(
            row,
            context=(
                *row.context,
                {
                    **row.context[0],
                    "memory_id": "extra-" + str(row.index),
                    "text": "Extra evidence",
                },
            ),
        )
        if row.index < 5
        else row
        for row in baseline
    ]
    plan = module.build_plan(
        baseline,
        rows,
        parent,
        binding={"parent": "synthetic"},
        cache_inventory_sha256=_hash(cache_inventory(cache)),
    )
    return baseline, rows, parent, cache, plan


async def run(fx, directory, factory, *, cache_only=False):
    baseline, rows, parent, cache, plan = fx
    return await module.run_reader(
        baseline,
        rows,
        parent,
        plan,
        run_dir=directory,
        parent_cache=cache,
        api_key="SYNTHETIC-SECRET",
        cache_only=cache_only,
        provider_factory=factory,
    )


@pytest.mark.asyncio
async def test_five_new_calls_unmodified_cache_and_zero_call_replay(tmp_path):
    fx = await fixture(tmp_path)
    _, _, _, cache, _ = fx
    inventory = cache_inventory(cache)
    factory = RecordingFactory(respond)
    live = await run(fx, tmp_path / "child", factory)
    assert live["status"] == "complete" and live["new_reader_calls"] == 5
    assert live["new_judge_calls"] == 0 and live["qa_metrics_available"] is False
    assert factory.calls == 5 and factory.providers[0].requests == []
    assert live["structurally_valid_rows"] == 30 and live["answer_changed_rows"] == 5
    assert cache_inventory(cache) == inventory
    assert len(live["rows"]) == 30
    replay_factory = RecordingFactory(
        lambda r: pytest.fail("cache replay reached provider")
    )
    replay = await run(fx, tmp_path / "child", replay_factory, cache_only=True)
    assert replay["status"] == "complete" and replay["new_reader_calls"] == 0
    assert replay_factory.calls == 0
    assert [r["reader"]["output"] for r in replay["rows"]] == [
        r["reader"]["output"] for r in live["rows"]
    ]
    assert replay["usage_cumulative"] == live["usage_cumulative"]
    with pytest.raises(ValueError, match="cache-only"):
        await run(fx, tmp_path / "child", RecordingFactory(respond))
    assert "SYNTHETIC-SECRET" not in json.dumps(live)


@pytest.mark.asyncio
async def test_missing_unchanged_cache_stops_before_any_changed_call(tmp_path):
    fx = await fixture(tmp_path, seed=False)
    factory = RecordingFactory(
        lambda r: pytest.fail("missing unchanged cache caused paid call")
    )
    result = await run(fx, tmp_path / "child", factory)
    assert result["status"] == "partial"
    assert result["new_reader_calls"] == 0 and factory.calls == 0
    assert result["stopped_reason"] == "unchanged-cache-missing-invalid-or-different"
    assert all(r["reader"]["status"] == "not_run" for r in result["rows"][:5])


@pytest.mark.asyncio
async def test_provider_failure_is_retained_not_retried(tmp_path):
    fx = await fixture(tmp_path)

    def fail(request):
        raise RuntimeError("SYNTHETIC-SECRET must not appear")

    factory = RecordingFactory(fail)
    result = await run(fx, tmp_path / "child", factory)
    assert result["status"] == "partial"
    assert result["new_reader_calls"] == 5 and factory.calls == 5
    assert result["usage_cumulative"]["attempt_status_counts"]["failed"] == 5
    assert "SYNTHETIC-SECRET" not in json.dumps(result)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "mutation",
    [
        "config",
        "baseline_request",
        "six_changed",
        "duplicate",
        "index",
        "missing_output",
    ],
)
async def test_frozen_parent_and_five_request_cap(tmp_path, mutation):
    baseline, rows, parent, _cache, _plan = await fixture(tmp_path)
    parent = deepcopy(parent)
    if mutation == "config":
        parent["plan"]["reader_config"]["max_completion_tokens"] = 4096
    elif mutation == "baseline_request":
        parent["answers"]["rows"][0]["reader"]["request_sha256"] = "wrong"
    elif mutation == "six_changed":
        rows[5] = replace(
            rows[5],
            context=(*rows[5].context, {**rows[5].context[0], "text": "changed"}),
        )
    elif mutation == "duplicate":
        rows[1] = rows[0]
    elif mutation == "index":
        baseline[0] = replace(baseline[0], index=30)
        rows[0] = replace(rows[0], index=30)
        parent["answers"]["rows"][0]["index"] = 30
    else:
        parent["answers"]["rows"][0]["reader"]["output"] = {}
    with pytest.raises(ValueError):
        module.build_plan(
            baseline, rows, parent, binding={}, cache_inventory_sha256="synthetic"
        )


@pytest.mark.asyncio
async def test_gold_and_profile_not_in_request_and_changed_context_bound(tmp_path):
    baseline, rows, parent, cache, plan = await fixture(tmp_path)
    row = rows[0]
    different = replace(
        row, scoring=replace(row.scoring, answer="GOLD-SHOULD-NOT-LEAK")
    )
    assert build_request(different) == build_request(row)
    assert set(build_request(row).input) == {
        "question",
        "question_reference_time",
        "context_items",
    }
    factory = RecordingFactory(respond)
    rows[0] = replace(row, context=(*row.context, {**row.context[0], "text": "new"}))
    with pytest.raises(ValueError, match="binding"):
        await run((baseline, rows, parent, cache, plan), tmp_path / "child", factory)
    assert factory.calls == 0


@pytest.mark.asyncio
async def test_child_cannot_write_into_parent_cache(tmp_path):
    fx = await fixture(tmp_path)
    with pytest.raises(ValueError, match="read-only parent"):
        await run(fx, fx[3] / "nested", RecordingFactory(respond))
