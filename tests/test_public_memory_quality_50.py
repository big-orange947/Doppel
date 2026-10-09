"""Fifty-question harness binding and accounting using synthetic fake responses."""

from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import replace

import pytest

from benchmarks.public_memory_answer_comparison import COMPARISON_RUNNER, PROFILE_NAMES
from benchmarks.public_memory_comparison import encoded
from benchmarks.public_memory_quality_50 import build_plan, prepare_batches, run
from tests.test_public_memory_answer_comparison import RecordingFactory
from tests.test_public_memory_expansion import respond, setup


def inputs():
    original, _, _, rows = setup()
    runtime, scoring = original[0]
    cases = [
        (
            replace(runtime, query=replace(runtime.query, query=f"Question {i}")),
            replace(scoring, case_id=f"case-{i:02d}"),
        )
        for i in range(50)
    ]
    context = list(rows[0].context)
    manifest = {"manifest_fingerprint": "a" * 64}
    comparison = {
        "runner": COMPARISON_RUNNER,
        "status": "complete",
        "manifest_fingerprint": "a" * 64,
        "corpus_sha256_before": "b" * 64,
        "corpus_sha256_after": "b" * 64,
        "record_or_index_writes": 0,
        "rows": [
            {
                "case_id": s.case_id,
                "profile": p,
                "context": deepcopy(context),
                "packed_item_count": len(context),
                "packed_context_bytes": len(encoded(context)),
            }
            for _, s in cases
            for p in PROFILE_NAMES
        ],
    }
    return cases, manifest, comparison


def test_fixed_partition_budget_and_provider_payload():
    cases, manifest, comparison = inputs()
    batches = prepare_batches(cases, manifest, comparison)
    plan = build_plan(batches, {"comparison": "c" * 64})
    assert plan["logical_rows"] == 150 and plan["max_total_calls"] == 300
    assert [r.case_id for b in batches for r in b[::3]] == [s.case_id for _, s in cases]
    assert len(plan["batch_rows"]) == 5
    from benchmarks.public_memory_expansion import reader_request

    for batch in batches:
        for row in batch:
            request = reader_request(row)
            assert set(request.input) == {
                "question",
                "question_reference_time",
                "context_items",
            }
            assert "GOLD_NOT_IN_MANIFEST" not in json.dumps(
                request.model_dump(mode="json")
            )
            assert "profile" not in request.input


@pytest.mark.parametrize(
    "mutation",
    [
        "missing",
        "duplicate",
        "changed_store",
        "write",
        "manifest",
        "budget",
        "count",
        "field",
    ],
)
def test_invalid_parent_fails_before_any_calls(mutation):
    cases, manifest, comparison = inputs()
    if mutation == "missing":
        comparison["rows"].pop()
    elif mutation == "duplicate":
        comparison["rows"][1] = comparison["rows"][0]
    elif mutation == "changed_store":
        comparison["corpus_sha256_after"] = "changed"
    elif mutation == "write":
        comparison["record_or_index_writes"] = 1
    elif mutation == "manifest":
        comparison["manifest_fingerprint"] = "changed"
    elif mutation == "budget":
        comparison["rows"][0]["context"][0]["text"] = "X" * 24_000
    elif mutation == "count":
        comparison["rows"][0]["packed_item_count"] = 2
    else:
        del comparison["rows"][0]["context"][0]["authority"]
    with pytest.raises(ValueError):
        prepare_batches(cases, manifest, comparison)


@pytest.mark.asyncio
async def test_five_batches_replay_with_zero_calls_and_unchanged_parents(tmp_path):
    cases, manifest, comparison = inputs()
    batches = prepare_batches(cases, manifest, comparison)
    before = deepcopy(comparison)
    plan = build_plan(batches, {"comparison": "c" * 64})
    factory = RecordingFactory(respond)
    live = await run(
        batches,
        plan,
        run_dir=tmp_path,
        api_key="FAKE-KEY",
        cache_only=False,
        provider_factory=factory,
    )
    assert live["status"] == "complete" and live["new_calls"] == 100
    assert all(
        s["questions"] == s["correctness_denominator"] == 50
        for s in live["summary"].values()
    )
    assert comparison == before
    assert "FAKE-KEY" not in json.dumps(live)
    replay = await run(
        batches,
        plan,
        run_dir=tmp_path,
        api_key="",
        cache_only=True,
        provider_factory=factory,
    )
    assert replay["summary"] == live["summary"] and replay["new_calls"] == 0
    assert [[r["reader"]["output"] for r in b["rows"]] for b in replay["batches"]] == [
        [r["reader"]["output"] for r in b["rows"]] for b in live["batches"]
    ]


@pytest.mark.asyncio
async def test_changed_request_plan_cannot_spend_calls(tmp_path):
    cases, manifest, comparison = inputs()
    batches = prepare_batches(cases, manifest, comparison)
    plan = build_plan(batches, {"comparison": "c" * 64})
    row = batches[0][0]
    batches[0][0] = replace(
        row,
        runtime=replace(row.runtime, query=replace(row.runtime.query, query="changed")),
    )
    factory = RecordingFactory(respond)
    with pytest.raises(ValueError, match="changed"):
        await run(
            batches,
            plan,
            run_dir=tmp_path,
            api_key="FAKE-KEY",
            cache_only=False,
            provider_factory=factory,
        )
    assert factory.calls == 0
