from __future__ import annotations

import copy

import pytest

from benchmarks.public_memory_fresh_continue import completed_prefix, prepare
from tests.test_public_memory_fresh_ingest import SHA, bound


def parent(plan):
    return {
        "ingestion": {
            "plan": plan["ingestion_plan"],
            "status": "partial",
            "store_record_audit": {"provenance_failures": 0},
            "audit": {
                "completed_chunks": 1,
                "chunks_without_analysis_observation": 0,
                "chunks": [
                    {
                        "write_key": plan["ingestion_plan"]["chunks"][0]["write_key"],
                        "completed": True,
                    }
                ],
            },
        },
    }


def test_continuation_uses_remaining_fixed_prefix_not_another_full_budget(
    tmp_path, monkeypatch
):
    from benchmarks import public_memory_fresh_continue as runner

    raw, manifest, plan = bound()
    monkeypatch.setattr(runner, "checkpoint", lambda *args: {"durable_attempts": 1})
    cases, stage = prepare(
        raw,
        manifest,
        plan,
        parent(plan),
        source_sha=SHA,
        parent_sha="a" * 64,
        run_dir=tmp_path,
        histories=3,
    )
    target = sum(c["chunk_count"] for c in manifest["cases"][:3])
    assert stage["max_provider_attempts"] == target - 1
    assert stage["target_completed_chunks"] == target
    assert stage["graph_calls"] == stage["qa_calls"] == 0
    assert all(c.query.query == "Withheld until frozen query execution" for c in cases)


@pytest.mark.parametrize(
    "mutation", ["unsettled", "gap", "count", "observation", "provenance", "plan"]
)
def test_prefix_must_be_complete_bound_and_audited(mutation):
    _, _, plan = bound()
    ingestion = copy.deepcopy(parent(plan)["ingestion"])
    if mutation == "unsettled":
        ingestion["audit"]["chunks"][0]["completed"] = False
    elif mutation == "gap":
        ingestion["audit"]["chunks"][0]["write_key"] = "unknown"
    elif mutation == "count":
        ingestion["audit"]["completed_chunks"] = 2
    elif mutation == "observation":
        ingestion["audit"]["chunks_without_analysis_observation"] = 1
    elif mutation == "provenance":
        ingestion["store_record_audit"]["provenance_failures"] = 1
    else:
        ingestion["plan"]["max_calls"] += 1
    with pytest.raises(ValueError):
        completed_prefix(ingestion, plan["ingestion_plan"])
