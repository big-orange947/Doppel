from __future__ import annotations

import json

import pytest

from benchmarks import public_memory_neighborhood_trial as runner
from benchmarks.public_context_baseline import RawHistoryHost
from benchmarks.public_longmemeval import prepare_case
from benchmarks.public_memory_pilot import _hash
from doppel_memory.bounded_selection import BoundedTopKSelector
from doppel_memory.models import RecallResult
from doppel_memory.sqlite_store import SQLiteStore
from integrations.aml.contract import memory_scope
from tests.test_prospective_selection import bound
from tests.test_public_context_baseline import sample
from tests.test_public_memory_fresh_cohort import SHA


def test_fixed_last_five_manifest_excludes_labels_and_all_opened_histories():
    raw, parent = bound()
    cases, manifest = runner.prepare(raw, parent, SHA)
    diagnostic = [r for r in parent["cases"] if r["partition"] == "diagnostic"]
    assert [r["case_id"] for r in manifest["cases"]] == [
        r["case_id"] for r in diagnostic[45:]
    ]
    assert [r["ordinal"] for r in manifest["cases"]] == list(range(46, 51))
    assert len(cases) == 5
    assert all(
        s not in str(manifest)
        for s in ("PRIVATE GOLD", "PRIVATE QUESTION", "has_answer")
    )


@pytest.mark.parametrize(
    "mutation",
    ["source", "payload", "count", "chunk", "opened", "reserved", "fingerprint"],
)
def test_bad_or_overlapping_source_rejected(mutation):
    raw, parent = bound()
    diagnostic = [r for r in parent["cases"] if r["partition"] == "diagnostic"]
    sha = SHA
    if mutation == "source":
        sha = "b" * 64
    elif mutation == "payload":
        diagnostic[45]["history_payload_sha256"] = "changed"
    elif mutation == "count":
        diagnostic[45]["raw_turn_count"] += 1
    elif mutation == "chunk":
        diagnostic[45]["chunk_count"] += 1
    elif mutation == "opened":
        diagnostic[45].update(diagnostic[44])
    elif mutation == "reserved":
        diagnostic[45]["history_group"] = next(
            r["history_group"]
            for r in parent["cases"]
            if r["partition"] != "diagnostic"
        )
    else:
        parent["cases"].reverse()
    if mutation != "fingerprint":
        parent["manifest_fingerprint"] = _hash(
            {k: v for k, v in parent.items() if k != "manifest_fingerprint"}
        )
    with pytest.raises(ValueError):
        runner.prepare(raw, parent, sha)


def test_frozen_same_selector_both_arms_and_forty_call_ceiling():
    raw, parent = bound()
    _, manifest = runner.prepare(raw, parent, SHA)
    plan = runner.make_plan("prepare", manifest)
    assert sum(s["max_calls"] for s in plan["stages"].values()) == 40
    assert plan["selector"]["max_candidates"] == 240
    assert plan["neighborhood"]["before"] == plan["neighborhood"]["after"] == 1
    assert plan["source_limit"] == plan["output_limit"] == 20
    assert plan["context_byte_limit"] == 24000 and plan["graph_calls"] == 0
    preparation = {"status": "complete", "plan": plan, "receipts": []}
    with pytest.raises(ValueError, match="ten bounded"):
        runner.make_plan("evaluate", manifest, preparation)
    preparation["plan"]["selector"]["max_candidates"] = 80
    with pytest.raises(ValueError, match="binding"):
        runner.make_plan("evaluate", manifest, preparation)


class TailSelector:
    name, version = "fake", "1"

    def __init__(self):
        self.requests = []

    async def generate(self, request):
        self.requests.append(request)
        return {"selected_ids": [request.input["items"][-1]["item_id"]]}


@pytest.mark.asyncio
async def test_full_100_pool_reaches_selector_and_exact_preview_no_old80_crop(tmp_path):
    raw = sample()
    raw["haystack_sessions"][0] = [
        {
            "role": "user" if i % 2 == 0 else "assistant",
            "content": f"Unchanged source {i}",
        }
        for i in range(100)
    ]
    case = prepare_case(raw, dataset_namespace="synthetic")
    store = SQLiteStore(tmp_path / "raw.sqlite3")
    host = RawHistoryHost(store)
    scope = memory_scope("run", case.runtime.user_id)
    try:
        records = await host.ingest(case.runtime, scope, max_messages=10)
        records = {r.memory_id: r for r in records}
        manifest = {"max_messages": 10}
        host, items = runner.bind_host(case.runtime, manifest, scope, records, store)
        pool = [
            RecallResult(
                scope=scope, memory_id=r.memory_id, fact="POISON", similarity=0.9
            )
            for r in list(records.values())[:100]
        ]
        snippets = await runner.validated(
            store, scope, host, pool, case.runtime.query.query
        )
        request = runner.preview(case.runtime.query.query, scope, snippets)
        assert len(request.input["items"]) == 100
        assert (
            "POISON" not in request.model_dump_json()
            and "GOLD_SECRET" not in request.model_dump_json()
        )
        model = TailSelector()
        selector = BoundedTopKSelector(model, runner.SELECTION)
        context = await runner.context_row(
            store,
            scope,
            host,
            pool,
            case.runtime,
            case.scoring,
            runner.PROFILES[0],
            selector,
            items,
        )
        assert model.requests[0] == request
        assert context["source_selection"]["offered_candidates"] == 100
        assert len(model.requests) == 2  # source and passage
        assert context["context"][0]["source_memory_id"] == pool[-1].memory_id
        assert context["source_execution"]["final_store_checks"] >= 1
        assert context["context_bytes"] <= 24000
        assert (
            json.loads(model.requests[0].input["items"][-1]["content"])["source_text"]
            == snippets[-1].text
        )
        assert all(
            k not in model.requests[0].input
            for k in ("profile", "answer", "evidence_turns")
        )
        with pytest.raises(ValueError, match="window"):
            runner.preview(case.runtime.query.query, scope, snippets * 3)
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_preview_never_calls_provider_and_char_cap_not_silently_truncated():
    selector = BoundedTopKSelector(runner.NoGenerate(), runner.SELECTION)
    with pytest.raises(RuntimeError, match="preflight"):
        await runner.NoGenerate().generate(
            selector.build_request("question", [], limit=20)
        )
    assert selector.config.max_input_chars == 350000
