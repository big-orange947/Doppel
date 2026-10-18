from __future__ import annotations

from copy import deepcopy
from types import SimpleNamespace

import pytest

from benchmarks import public_memory_uniform_qa as runner
from benchmarks.public_memory_pilot import _hash
from tests.test_prospective_selection import bound
from tests.test_public_memory_fresh_cohort import SHA


def frozen(value):
    return {**value, "plan_fingerprint": _hash(value)}


def inputs():
    raw, parent = bound()
    reports = {}
    for key, factory in (
        ("twenty", runner.prepare_twenty),
        ("ten", runner.prepare_ten),
    ):
        cases, manifest = factory(raw, parent, source_sha=SHA)
        rows, certs = [], []
        for meta, (_, scoring) in zip(manifest["cases"], cases, strict=True):
            coverage = {
                "abstention_label": False,
                "annotated_turn_count": 1,
                "annotated_turn_hits": 1,
            }
            pack = {
                "packed_context_sha256": "packed",
                "packed_positions": [[0, 0]],
                "after": coverage,
            }
            rows.append(
                {
                    "case_id": scoring.case_id,
                    "profile": runner.RETRIEVAL_PROFILE,
                    "retrieved_source_positions": [[0, 0]],
                    "candidate_window_score": coverage,
                    "at_20": coverage,
                    "packing": {"ranked_fit": pack},
                }
            )
            certs.append(
                {
                    "case_id": scoring.case_id,
                    "before_sha256": "digest",
                    "after_sha256": "digest",
                    "corpus_sha256": "digest",
                }
            )
        reports[key] = {
            "status": "complete",
            "plan": frozen(
                {
                    "manifest": manifest,
                    "schema": "synthetic_" + key,
                    "reranker": {"model": "unchanged"},
                }
            ),
            "rows": rows,
            "receipts": certs,
        }
    binding = {
        "dataset": SHA,
        "manifest": "manifest",
        "twenty": "twenty",
        "packing": "packing",
        "ten": "ten",
    }
    reports["packing"] = {
        "status": "complete",
        "plan": frozen(
            {
                "binding": {
                    "dataset": SHA,
                    "parent_manifest": "manifest",
                    "retrieval_report": "twenty",
                }
            }
        ),
        "rows": [
            {"case_id": r["case_id"], "profile": r["profile"], **r["packing"]}
            for r in reports["twenty"]["rows"]
        ],
        "source_certificates": reports["twenty"]["receipts"],
    }
    return {"dataset": raw, "manifest": parent, **reports}, binding


def test_all_thirty_fixed_queue_first27_then_three_opened_not_outcome_selection():
    data, binding = inputs()
    queue, groups = runner.prepare_inputs(data, binding)
    assert len(queue) == 30 and len(groups) == 2
    assert [r[0]["ordinal"] for r in queue[-3:]] == [32, 37, 40]
    assert len([r for r in queue if not r[0]["previous_qa"]]) == 27
    assert {r[0]["ordinal"] for r in queue} == set(range(11, 41))
    plan = runner.make_plan("prepare", queue, groups, binding)
    assert sum(v["max_calls"] for v in plan["stages"].values()) == 60
    assert not plan["retrieval_rerun"] and not plan["llm_selection"]
    assert "PRIVATE GOLD" not in str(plan) and "PRIVATE QUESTION" not in str(plan)
    assert not plan["publication_ready"] and plan["opened_development_not_blind"]


@pytest.mark.parametrize(
    "change", ["incomplete", "duplicate_rank", "corpus", "binding", "model", "manifest"]
)
def test_invalid_or_unbound_inputs_stop_before_calls(change):
    data, binding = inputs()
    if change == "incomplete":
        data["ten"]["status"] = "failed"
    elif change == "duplicate_rank":
        data["ten"]["rows"].append(deepcopy(data["ten"]["rows"][0]))
    elif change == "corpus":
        data["packing"]["source_certificates"][0]["before_sha256"] = "changed"
    elif change == "binding":
        binding["twenty"] = "changed"
    elif change == "model":
        data["ten"]["plan"]["reranker"] = {"model": "different"}
        data["ten"]["plan"] = frozen(
            {k: v for k, v in data["ten"]["plan"].items() if k != "plan_fingerprint"}
        )
    else:
        data["manifest"]["cases"].reverse()
    with pytest.raises(ValueError):
        runner.prepare_inputs(data, binding)


def test_exact_saved_context_hash_order_bytes_and_no_repacking_tuning():
    items = {
        (0, 0): {"text": "original", "memory_id": "m"},
        (0, 1): {"text": "second", "memory_id": "n"},
    }
    packed, _ = runner.pack_ranked_fit(list(items.values()))
    import hashlib

    meta = {
        "positions": [[0, 0], [0, 1]],
        "packed_positions": [[0, 0], [0, 1]],
        "packed_sha256": hashlib.sha256(runner.encoded(packed)).hexdigest(),
    }
    assert runner.checked_context(meta, items) == packed
    for field, value in (
        ("positions", [[0, 1], [0, 0]]),
        ("positions", [[0, 0], [0, 0]]),
        ("packed_sha256", "changed"),
    ):
        with pytest.raises(ValueError):
            runner.checked_context({**meta, field: value}, items)


def test_frozen_prepare_binding_cannot_change_before_paid_phase():
    data, binding = inputs()
    queue, groups = runner.prepare_inputs(data, binding)
    plan = runner.make_plan("prepare", queue, groups, binding)
    preparation = {"status": "complete", "plan": plan, "rows": []}
    with pytest.raises(ValueError, match="thirty"):
        runner.make_plan("answers", queue, groups, binding, preparation)
    preparation["plan"]["context_byte_limit"] = 48000
    with pytest.raises(ValueError, match="binding"):
        runner.make_plan("answers", queue, groups, binding, preparation)


def test_summary_does_not_count_missing_rows_as_completed_or_negative_as_positive():
    rows = [
        {
            "previous_qa": False,
            "abstention_label": False,
            "question_type": "temporal",
            "grade": {"answer_correct": True},
            "checks": {"structurally_valid": True},
        },
        {
            "previous_qa": False,
            "abstention_label": True,
            "question_type": "user",
            "grade": {"answer_correct": True},
            "checks": {"structurally_valid": True},
        },
        {
            "previous_qa": True,
            "abstention_label": False,
            "question_type": "temporal",
            "grade": None,
        },
    ]
    out = runner.summary(rows)
    assert out["completed"] == 2 and not out["all_thirty_complete"]
    assert (
        out["expected"] == 30
        and out["answerable"]["completed"] == 1
        and out["unanswerable"]["completed"] == 1
    )
    assert out["previously_answered_diagnostic"]["accuracy"] is None


@pytest.mark.asyncio
async def test_real_context_prepare_and_fake_qa_gold_separation_no_network(
    tmp_path, monkeypatch
):
    from doppel_memory.sqlite_store import SQLiteStore
    from tests.test_public_context_baseline import setup

    store, _host, case, scope, records, _ = await setup(tmp_path)
    records = {r.memory_id: r for r in records}
    manifest = {"run_namespace": "run", "max_messages": 1}
    _, items = runner.bind_host(case.runtime, manifest, scope, records, store)
    packed, _ = runner.pack_ranked_fit(list(items.values()))
    import hashlib

    meta = {
        "ordinal": 11,
        "case_id": case.scoring.case_id,
        "group": "one",
        "previous_qa": False,
        "corpus_sha256": runner.digest(records),
        "positions": [list(p) for p in items],
        "packed_positions": [list(p) for p in items],
        "packed_sha256": hashlib.sha256(runner.encoded(packed)).hexdigest(),
        "packed_coverage": {},
    }
    queue = [(meta, case.runtime, case.scoring)]
    groups = {"one": {"manifest": manifest, "schema": "unused"}}
    await store.close()
    monkeypatch.setattr(runner, "local_diagnostic_dsn", lambda _: "unused")
    monkeypatch.setattr(
        runner, "ReadOnlyStore", lambda *a, **kw: SQLiteStore(tmp_path / "raw.sqlite3")
    )
    monkeypatch.setenv("DEEPSEEK_API_KEY", "fake-unit-test-only")
    args = SimpleNamespace(run_dir=tmp_path / "run")
    plan = runner.make_plan("prepare", queue, groups, {})
    prep = await runner.prepare_run(args, queue, groups, plan)
    assert prep["status"] == "complete" and prep["new_calls"] == 0
    requests = []

    class Fake:
        name, version = "fake", "1"

        async def generate(self, request):
            requests.append(request)
            if len(requests) % 2 == 0:
                return {"answer_correct": True, "rationale": "synthetic"}
            assert "GOLD_SECRET" not in request.model_dump_json()
            return {
                "answer": "synthetic",
                "abstained": False,
                "cited_memory_ids": [packed[0]["memory_id"]],
            }

    monkeypatch.setattr(runner, "_default_provider_factory", lambda *a: Fake())
    result = await runner.evaluate_run(args, queue, groups, plan, prep)
    assert result["status"] == "complete" and len(requests) == 2
    assert "GOLD_SECRET" in requests[1].model_dump_json()
    assert result["rows"][0]["checks"]["structurally_valid"]
