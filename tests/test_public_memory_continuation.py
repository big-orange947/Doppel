from __future__ import annotations

from copy import deepcopy
from types import SimpleNamespace

import pytest

from benchmarks import public_memory_continuation as runner
from benchmarks.public_context_baseline import RawHistoryHost
from benchmarks.public_memory_pilot import _hash, build_manifest
from doppel_memory.in_memory_store import InMemoryStore
from integrations.aml.contract import memory_scope
from tests.test_public_memory_fresh_cohort import SHA, dataset


def bound():
    raw = dataset()
    parent = build_manifest(
        raw,
        dataset_namespace="synthetic",
        run_namespace="parent",
        source_sha256=SHA,
        diagnostic_count=40,
        reserved_count=2,
    )
    return raw, parent


def test_exact_next_ten_with_no_opened_or_reserved_groups():
    raw, parent = bound()
    cases, manifest = runner.prepare(raw, parent, SHA)
    selected = [c for c in parent["cases"] if c["partition"] == "diagnostic"]
    assert [c["case_id"] for c in manifest["cases"]] == [
        c["case_id"] for c in selected[30:40]
    ]
    assert len(cases) == 10
    assert [c["ordinal"] for c in manifest["cases"]] == list(range(31, 41))
    assert "PRIVATE GOLD" not in str(manifest) and "has_answer" not in str(manifest)
    plan = runner.make_plan(manifest, SimpleNamespace(report=dict))
    assert len(plan["profiles"]) == 3 and plan["policies"] == ["prefix", "ranked_fit"]
    assert plan["candidate_window"] == 80 and plan["output_limit"] == 20
    assert (
        plan["context_byte_limit"] == 24000
        and plan["llm_calls"] == plan["graph_calls"] == 0
    )


@pytest.mark.parametrize(
    "mutation", ["source", "payload", "count", "opened_overlap", "fingerprint"]
)
def test_source_selection_and_overlap_must_match_frozen_manifest(mutation):
    raw, original = bound()
    parent = deepcopy(original)
    selected = [c for c in parent["cases"] if c["partition"] == "diagnostic"]
    source = SHA
    if mutation == "source":
        source = "b" * 64
    elif mutation == "payload":
        selected[30]["history_payload_sha256"] = "changed"
    elif mutation == "count":
        selected[30]["raw_turn_count"] += 1
    elif mutation == "opened_overlap":
        selected[30].update(selected[0])
    else:
        parent["cases"].reverse()
    if mutation not in {"source", "fingerprint"}:
        parent["manifest_fingerprint"] = _hash(
            {k: v for k, v in parent.items() if k != "manifest_fingerprint"}
        )
    with pytest.raises(ValueError):
        runner.prepare(raw, parent, source)


@pytest.mark.asyncio
async def test_contexts_bound_to_real_raw_ingestion_without_labels_or_text_changes():
    raw, parent = bound()
    cases, manifest = runner.prepare(raw, parent, SHA)
    runtime, _ = cases[0]
    store = InMemoryStore()
    host = RawHistoryHost(store)
    scope = memory_scope(manifest["run_namespace"], runtime.user_id)
    records = await host.ingest(runtime, scope, max_messages=manifest["max_messages"])
    items = runner.bound_items(
        runtime, manifest, scope, host, {r.memory_id: r for r in records}
    )
    assert len(items) == len(records)
    assert all(
        item["role"] == "user" and item["channel"] == "raw" for item in items.values()
    )
    assert "PRIVATE GOLD" not in str(items)
    changed = records[0].model_copy(update={"content": "changed"})
    with pytest.raises(ValueError):
        runner.bound_items(runtime, manifest, scope, host, {changed.memory_id: changed})


@pytest.mark.asyncio
async def test_execution_refuses_unfrozen_or_previously_started_work(tmp_path):
    raw, parent = bound()
    cases, manifest = runner.prepare(raw, parent, SHA)
    reranker = SimpleNamespace(report=dict)
    plan = runner.make_plan(manifest, reranker)
    args = SimpleNamespace(frozen_preflight=None, run_dir=tmp_path)
    with pytest.raises(ValueError, match="frozen"):
        await runner.execute(args, cases, manifest, plan, reranker)
    frozen = tmp_path / "frozen.json"
    runner.save(frozen, {"plan": plan})
    args.frozen_preflight = frozen
    with pytest.raises(ValueError, match="silent second"):
        await runner.execute(args, cases, manifest, plan, reranker)
