from __future__ import annotations

import copy
from types import SimpleNamespace

import pytest

from benchmarks import public_memory_fresh_recover as runner
from benchmarks.public_memory_pilot import _hash


def fixture(monkeypatch):
    chunks = [{"write_key": str(i)} for i in range(5)]
    plan = {"chunks": chunks, "plan_fingerprint": "i"}
    cohort = {"ingestion_plan": plan, "plan_fingerprint": "c"}
    failed = {
        "call_id": 2,
        "request_sha256": "r",
        "status": "failed",
        "diagnostics": {"code": "transport_error"},
    }
    snapshot = {"durable_attempts": 2, "failed_attempt": failed, "calls_sha256": "s"}
    calls = [
        {"call_id": 1, "status": "succeeded"},
        {k: v for k, v in failed.items() if k != "diagnostics"},
    ]
    parent = {
        "status": "failed",
        "ingestion": {
            "plan": plan,
            "status": "failed",
            "store_record_audit": {"provenance_failures": 0},
            "stopped": {
                "stage": "extraction",
                "code": "stage-execution-failed",
                "write_key": "1",
            },
            "usage_cumulative": {
                "ledger": {
                    "failure_diagnostics": [
                        {"call_id": 2, "request_sha256": "r", "code": "transport_error"}
                    ]
                }
            },
            "audit": {
                "completed_chunks": 1,
                "chunks_without_analysis_observation": 1,
                "chunks": [
                    {"write_key": "0", "completed": True},
                    {
                        "write_key": "1",
                        "completed": False,
                        "raw_stage_persisted": True,
                        "proposal_stage_persisted": False,
                        "analysis_diagnostics": None,
                        "consolidation_plan_persisted": False,
                        "consolidation_done": False,
                    },
                ],
            },
        },
    }
    monkeypatch.setattr(
        runner, "prepare_stage", lambda *a, **kw: ([], {"max_new_chunks": 5})
    )
    monkeypatch.setattr(runner, "state", lambda *a: (snapshot, calls))
    return cohort, parent, snapshot, calls


def prepare(cohort, parent, tmp_path, mode="recover"):
    return runner.prepare(
        [],
        {},
        cohort,
        parent,
        source_sha="s",
        parent_sha="p",
        run_dir=tmp_path,
        mode=mode,
    )[1]


def test_one_recovery_retains_failure_and_does_not_allocate_remaining_budget(
    monkeypatch, tmp_path
):
    cohort, parent, snapshot, _ = fixture(monkeypatch)
    stage = prepare(cohort, parent, tmp_path)
    assert stage["max_provider_attempts"] == stage["max_new_chunks"] == 1
    assert stage["target_completed_chunks"] == 2
    assert stage["checkpoint"] == snapshot
    assert stage["generation_settings_changed"] is False
    assert stage["graph_calls"] == stage["qa_calls"] == 0


@pytest.mark.parametrize(
    "mutation",
    [
        "gap",
        "proposal",
        "analysis",
        "consolidation",
        "provenance",
        "diagnostic",
        "completed",
        "stop",
    ],
)
def test_recovery_rejects_changed_or_non_pending_source(
    monkeypatch, tmp_path, mutation
):
    cohort, parent, _, _ = fixture(monkeypatch)
    ingestion = parent["ingestion"]
    pending = ingestion["audit"]["chunks"][-1]
    if mutation == "gap":
        pending["write_key"] = "2"
    elif mutation == "proposal":
        pending["proposal_stage_persisted"] = True
    elif mutation == "analysis":
        pending["analysis_diagnostics"] = {}
    elif mutation == "consolidation":
        pending["consolidation_done"] = True
    elif mutation == "provenance":
        ingestion["store_record_audit"]["provenance_failures"] = 1
    elif mutation == "diagnostic":
        ingestion["usage_cumulative"]["ledger"]["failure_diagnostics"][0]["code"] = (
            "timeout"
        )
    elif mutation == "completed":
        pending["completed"] = True
    else:
        ingestion["stopped"]["write_key"] = "2"
    with pytest.raises(ValueError):
        prepare(cohort, parent, tmp_path)


def test_resume_requires_verified_recovery_and_exact_post_checkpoint(
    monkeypatch, tmp_path
):
    cohort, parent, snapshot, _ = fixture(monkeypatch)
    recovery_stage = prepare(cohort, parent, tmp_path)
    ingestion = parent["ingestion"]
    ingestion["status"] = "partial"
    ingestion["audit"]["chunks"][-1]["completed"] = True
    ingestion["audit"].update(completed_chunks=2, chunks_without_analysis_observation=0)
    parent.update(
        runner=runner.RUNNER,
        stage=recovery_stage,
        recovery_verified=True,
        post_checkpoint=copy.deepcopy(snapshot),
    )
    stage = prepare(cohort, parent, tmp_path, "resume")
    assert stage["max_provider_attempts"] == 3
    assert stage["target_completed_chunks"] == 5
    parent["post_checkpoint"]["durable_attempts"] += 1
    with pytest.raises(ValueError):
        prepare(cohort, parent, tmp_path, "resume")


@pytest.mark.asyncio
async def test_failed_recovery_produces_receipt_without_second_attempt(
    monkeypatch, tmp_path
):
    calls = []

    async def execute(*args):
        calls.append(1)
        return {"ingestion": {"status": "failed", "stopped": {"stage": "extraction"}}}

    monkeypatch.setattr(runner, "execute", execute)
    result = await runner.run(SimpleNamespace(run_dir=tmp_path), [], {}, {}, {})
    assert calls == [1]
    assert result["stage_verified"] is result["recovery_verified"] is False
    assert result["ingestion"]["stopped"]["stage"] == "extraction"


@pytest.mark.asyncio
async def test_recovery_verifies_identical_request_and_preserves_old_ledger(
    monkeypatch, tmp_path
):
    cohort, parent, _, calls = fixture(monkeypatch)
    stage = prepare(cohort, parent, tmp_path)
    stage["checkpoint"]["calls_sha256"] = _hash(calls)
    ingestion = parent["ingestion"]
    ingestion["status"] = "partial"
    ingestion["audit"]["chunks"][-1]["completed"] = True
    ingestion["audit"].update(completed_chunks=2, chunks_without_analysis_observation=0)

    async def execute(*args):
        return {"ingestion": ingestion}

    monkeypatch.setattr(runner, "execute", execute)
    calls.append({"status": "succeeded", "request_sha256": "r"})
    result = await runner.run(SimpleNamespace(run_dir=tmp_path), [], {}, cohort, stage)
    assert result["recovery_verified"] is True
    calls[-1]["request_sha256"] = "changed"
    result = await runner.run(SimpleNamespace(run_dir=tmp_path), [], {}, cohort, stage)
    assert result["recovery_verified"] is False
