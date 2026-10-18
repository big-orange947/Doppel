from __future__ import annotations

from copy import deepcopy
from types import SimpleNamespace

import pytest

from benchmarks import public_memory_uniform_completion as runner
from benchmarks import public_memory_uniform_qa as baseline
from benchmarks.public_memory_pilot import _hash
from doppel_memory.models import MemoryFilter, MemoryState
from tests.test_uniform_qa import frozen, inputs


def bound():
    old, binding = inputs()
    binding["baseline_answers"] = "baseline_answers"
    queue, groups = baseline.prepare_inputs(old, binding)
    contexts = {
        "status": "complete",
        "plan": baseline.make_plan("prepare", queue, groups, binding),
        "rows": [],
    }
    answer_plan = baseline.make_plan("answers", queue, groups, binding)
    answer_plan.pop("plan_fingerprint")
    answer_plan["preparation_sha256"] = _hash(contexts)

    def row(ordinal, case_id, category):
        return {
            "ordinal": ordinal,
            "case_id": case_id,
            "question_type": category,
            "abstention_label": False,
            "grade": {"answer_correct": True},
            "checks": {"structurally_valid": True},
        }

    answers = {
        "status": "complete",
        "plan": frozen(answer_plan),
        "rows": [row(m["ordinal"], s.case_id, s.category) for m, _, s in queue],
        "usage": {},
    }
    data = {
        "dataset": old["dataset"],
        "manifest": old["manifest"],
        "baseline_retrieval": old["twenty"],
        "baseline_contexts": contexts,
        "baseline_answers": answers,
        "ingestion": {"ingestion": {"postgres_schema": "synthetic_first"}},
        "nograph": {"status": "complete", "plans": {}},
    }
    selected = [r for r in data["manifest"]["cases"] if r["partition"] == "diagnostic"]
    for ordinal in range(1, 11):
        source = frozen({"corpus_sha256": "digest"})
        if ordinal <= 5:
            data[f"query{ordinal}"] = {
                "status": "complete",
                "plans": {"raw_vector_reranked": source},
            }
        else:
            data["nograph"]["plans"][str(ordinal)] = {"raw_vector_reranked": source}
    pool = [{"fact": "unchanged", "memory_id": f"m{i}"} for i in range(180)]
    for key, ordinals in (
        ("selection", range(41, 46)),
        ("neighborhood", range(46, 51)),
    ):
        receipts = []
        for ordinal in ordinals:
            r = {"case_id": selected[ordinal - 1]["case_id"], "corpus_sha256": "digest"}
            if key == "selection":
                r.update(pool=pool[:80], pool_sha256=_hash(pool[:80]))
            else:
                r.update(
                    pools={"neighborhood": {"pool": pool, "pool_sha256": _hash(pool)}},
                    expansion={"anchor_count": 80},
                )
            receipts.append(r)
        data[key] = {
            "status": "complete",
            "plan": frozen(
                {"manifest": data["manifest"], "schema": "synthetic_" + key}
            ),
            "receipts": receipts,
        }
    return data, binding, row


def test_fixed_complement_not_nativeN_prefix_or_best_arm():
    data, binding, _ = bound()
    queue, groups = runner.prepare_inputs(data, binding)
    assert [m["ordinal"] for m, _, _ in queue] == list(runner.ORDINALS)
    assert all(m["pool"] is None for m, _, _ in queue[:10])
    assert all(len(m["pool"]) == 80 for m, _, _ in queue[10:])
    assert (
        queue[-1][0]["pool"]
        == data["neighborhood"]["receipts"][-1]["pools"]["neighborhood"]["pool"][:80]
    )
    assert len(groups) == 3
    plan = runner.make_plan("prepare", data, binding, queue, groups)
    assert sum(s["max_calls"] for s in plan["stages"].values()) == 40
    assert plan["local_query_embeddings_max"] == 10 and plan["pairs_max"] == 1600
    assert not plan["llm_selection"] and not plan["publication_ready"]
    assert "PRIVATE GOLD" not in str(plan) and "PRIVATE QUESTION" not in str(plan)


@pytest.mark.parametrize(
    "change",
    ["dataset", "payload", "pool", "anchor", "baseline_config", "baseline_count"],
)
def test_changed_sources_or_protocol_fail_before_model_calls(change):
    data, binding, _ = bound()
    if change == "dataset":
        binding["dataset"] = "changed"
    elif change == "payload":
        raw = next(
            r
            for r in data["dataset"]
            if r["question_id"] == data["manifest"]["cases"][0]["case_id"]
        )
        raw["haystack_sessions"][0][0]["content"] = "changed"
    elif change == "pool":
        data["selection"]["receipts"][0]["pool"].reverse()
    elif change == "anchor":
        data["neighborhood"]["receipts"][0]["expansion"]["anchor_count"] = 79
    elif change == "baseline_config":
        p = data["baseline_answers"]["plan"]
        p["stages"]["reader"]["config"]["temperature"] = 0.1
        data["baseline_answers"]["plan"] = frozen(
            {k: v for k, v in p.items() if k != "plan_fingerprint"}
        )
    else:
        data["baseline_answers"]["rows"].pop()
    with pytest.raises(ValueError):
        runner.prepare_inputs(data, binding)


@pytest.mark.parametrize("prefix", ["", "record."])
def test_raw_channel_sql_predicate_bound_and_applied_before_limit(prefix):
    where, params = [], []
    filters = MemoryFilter(states={MemoryState.CONFIRMED})
    runner.RawOnlyStore._append_filters(where, params, filters, prefix=prefix)
    assert where[-1] == f"{prefix}extractor=$2" and params[-1] == "ingestor"
    original, original_params = [], []
    runner.ReadOnlyStore._append_filters(
        original, original_params, filters, prefix=prefix
    )
    assert where[:-1] == original and params[:-1] == original_params
    with pytest.raises(ValueError):
        runner.RawOnlyStore._append_filters([], [], filters, prefix="untrusted;")


def test_aggregate_exact_complement_no_duplicate_or_missing_rows():
    data, binding, row = bound()
    queue, groups = runner.prepare_inputs(data, binding)
    preparation = {
        "status": "complete",
        "plan": runner.make_plan("prepare", data, binding, queue, groups),
        "rows": [
            {
                "ordinal": m["ordinal"],
                "reader_request_sha256": "sha",
                "reader_request_bytes": 100,
                "context_sha256": "ctx",
            }
            for m, _, _ in queue
        ],
    }
    completion = {
        "status": "complete",
        "plan": runner.make_plan("answers", data, binding, queue, groups, preparation),
        "rows": [row(m["ordinal"], s.case_id, s.category) for m, _, s in queue],
        "usage": {},
    }
    result = runner.aggregate(data, binding, completion, preparation)
    assert result["summary"]["n"] == 50 and result["summary"]["correct"] == 50
    assert [r["ordinal"] for r in result["rows"]] == list(range(1, 51))
    bad = deepcopy(completion)
    bad["rows"][-1] = deepcopy(bad["rows"][0])
    with pytest.raises(ValueError, match="disjoint"):
        runner.aggregate(data, binding, bad, preparation)
    bad = deepcopy(completion)
    bad["plan"]["context_byte_limit"] = 48000
    bad["plan"] = frozen(
        {k: v for k, v in bad["plan"].items() if k != "plan_fingerprint"}
    )
    with pytest.raises(ValueError):
        runner.aggregate(data, binding, bad, preparation)


@pytest.mark.asyncio
async def test_mixed_store_bound_raw_and_fake_paid_flow(tmp_path, monkeypatch):
    from benchmarks.public_context_baseline import RawHistoryHost
    from benchmarks.public_longmemeval import prepare_case
    from doppel_memory.models import MemoryRecord, RecallResult
    from doppel_memory.sqlite_store import SQLiteStore
    from integrations.aml.contract import memory_scope
    from tests.test_public_context_baseline import sample

    raw = sample()
    raw["haystack_sessions"][0] = [
        {"role": "user", "content": f"original {i}"} for i in range(100)
    ]
    case = prepare_case(raw, dataset_namespace="synthetic")
    scope = memory_scope("run", case.runtime.user_id)
    store = SQLiteStore(tmp_path / "raw.sqlite3")
    host = RawHistoryHost(store)
    created = await host.ingest(case.runtime, scope, max_messages=10)
    await store.put(
        MemoryRecord(
            scope=scope,
            content="derived must not be a raw source",
            kind="event",
            extractor="llm",
        )
    )
    records = await runner.inventory(store, [scope])
    meta = {
        "ordinal": 1,
        "case_id": case.scoring.case_id,
        "group": "first",
        "corpus_sha256": runner.digest(records),
        "raw_records": len(created),
        "pool": None,
    }
    group = {
        "manifest": {"run_namespace": "run", "max_messages": 10},
        "schema": "unused",
    }
    _, _, items = await runner.bound_source(store, meta, case.runtime, group)
    assert len(items) == len(created) and len(records) == len(created) + 1
    packed, _ = runner.pack_ranked_fit(list(items.values())[:20])
    import hashlib

    row = runner.AnswerRow(
        0,
        case.scoring.case_id,
        runner.PROFILE,
        case.runtime,
        case.scoring,
        tuple(packed),
    )
    request = runner.reader_request(row)
    pool = [
        RecallResult(
            scope=scope, memory_id=r.memory_id, fact="untrusted", similarity=1
        ).model_dump(mode="json")
        for r in created[:80]
    ]
    context = {
        "ordinal": 1,
        "case_id": case.scoring.case_id,
        "context": packed,
        "context_sha256": hashlib.sha256(runner.encoded(packed)).hexdigest(),
        "pool": pool,
        "pool_sha256": _hash(pool),
        "reader_request_sha256": runner._request_sha256(request),
        "packed_coverage": {},
    }
    await store.close()
    monkeypatch.setattr(runner, "local_diagnostic_dsn", lambda _: "unused")
    monkeypatch.setattr(
        runner, "ReadOnlyStore", lambda *a, **kw: SQLiteStore(tmp_path / "raw.sqlite3")
    )
    monkeypatch.setenv("DEEPSEEK_API_KEY", "fake-unit-test-only")
    requests = []

    class Fake:
        name, version = "fake", "1"

        async def generate(self, req):
            requests.append(req)
            if "answer_correct" in req.output_schema.get("properties", {}):
                return {"answer_correct": True, "rationale": "synthetic"}
            assert "GOLD_SECRET" not in req.model_dump_json()
            return {
                "answer": "synthetic",
                "abstained": False,
                "cited_memory_ids": [packed[0]["memory_id"]],
            }

    monkeypatch.setattr(runner, "_default_provider_factory", lambda *a: Fake())
    plan = {
        "plan_fingerprint": "fake",
        "stages": {
            n: {
                "max_calls": 20,
                "max_request_bytes": 100000,
                "max_total_request_bytes": 2000000,
            }
            for n in runner.STAGES
        },
    }
    result = await runner.evaluate_run(
        SimpleNamespace(run_dir=tmp_path / "run"),
        [(meta, case.runtime, case.scoring)],
        {"first": group},
        plan,
        {"rows": [context]},
    )
    assert result["status"] == "complete" and len(requests) == 2
    assert "GOLD_SECRET" in requests[1].model_dump_json()
    assert result["rows"][0]["checks"]["structurally_valid"]
