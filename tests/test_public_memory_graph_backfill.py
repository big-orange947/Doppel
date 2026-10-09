import json
from copy import deepcopy
from datetime import UTC, datetime

import pytest

pytest.importorskip("graphiti_core")

from benchmarks.public_memory_graph_backfill import (
    build_plan,
    failure_details,
    parent_binding,
    writer_lock,
)
from benchmarks.public_memory_runtime import DurableCallLedger, PilotRuntimeError
from doppel_memory.intelligence import StructuredGenerationRequest
from doppel_memory.models import (
    Actor,
    FactAuthority,
    MemoryRecord,
    MemoryScope,
    MemoryState,
)


def fixture():
    scopes = [
        MemoryScope(user_id="first", agent_id="agent"),
        MemoryScope(user_id="second", agent_id="agent"),
    ]
    records = {
        f"memory-{i}": MemoryRecord(
            memory_id=f"memory-{i}",
            scope=scopes[i % 2],
            content="source memory",
            actor=Actor.OWNER,
            authority=FactAuthority.HUMAN_SELF,
            state=MemoryState.CONFIRMED,
            tags={"personal-memory"},
            created_at=datetime(2023, 1, i + 1, tzinfo=UTC),
            metadata={
                "subject": Actor.OWNER,
                "subject_id": scopes[i % 2].user_id,
                "evidence": [{"evidence_id": f"event-{i}"}],
            },
        )
        for i in range(4)
    }
    ingestion = {
        "status": "complete",
        "all_histories_ingested": True,
        "plan": {"plan_fingerprint": "a" * 64},
        "postgres_schema": "synthetic",
        "embedding": {"name": "synthetic", "version": "1", "dimensions": 2},
    }
    return records, scopes, ingestion


def test_plan_uses_source_order_no_question_or_gold():
    records, scopes, ingestion = fixture()
    before = deepcopy(records)
    plan = build_plan(records, scopes, ingestion, max_records=3, max_calls=48)
    assert [r["memory_id"] for r in plan["records"]] == [
        "memory-0",
        "memory-2",
        "memory-1",
    ]
    assert plan["eligible_records"] == 4
    assert records == before
    assert "source memory" not in str(plan)


@pytest.mark.parametrize(
    "mutation", ["inactive", "raw", "bad_subject", "bad_authority"]
)
def test_eligibility_does_not_upgrade_records(mutation):
    records, scopes, ingestion = fixture()
    record = records["memory-0"]
    updates = (
        {"state": MemoryState.SUPERSEDED}
        if mutation == "inactive"
        else (
            {"tags": []}
            if mutation == "raw"
            else (
                {"metadata": {**record.metadata, "subject_id": "other"}}
                if mutation == "bad_subject"
                else {"authority": FactAuthority.AGENT_OUTPUT}
            )
        )
    )
    records["memory-0"] = record.model_copy(update=updates)
    if mutation.startswith("bad"):
        with pytest.raises(ValueError):
            build_plan(records, scopes, ingestion, max_records=3, max_calls=48)
    else:
        assert (
            build_plan(records, scopes, ingestion, max_records=3, max_calls=48)[
                "eligible_records"
            ]
            == 3
        )


def test_process_lock_blocks_concurrent_writer_and_releases(tmp_path):
    path = tmp_path / "writer.lock"
    with writer_lock(path), pytest.raises(OSError), writer_lock(path):
        pass
    with writer_lock(path):
        pass


def parent_fixture(tmp_path):
    records, scopes, ingestion = fixture()
    plan = build_plan(records, scopes, ingestion, max_records=3, max_calls=48)
    tmp_path.mkdir(exist_ok=True)
    (tmp_path / "plan.json").write_text(json.dumps(plan), encoding="utf-8")
    cache = tmp_path / "cache"
    cache = cache / "provider-output-v1" / "model-version"
    cache.mkdir(parents=True)
    (cache / "synthetic.json").write_text('{"test-only": true}', encoding="utf-8")
    ledger = DurableCallLedger(
        tmp_path / "provider.sqlite3",
        budget_id=plan["plan_fingerprint"],
        max_calls=48,
        max_request_bytes=500_000,
        max_total_request_bytes=8_000_000,
    )
    ledger.bind_model("synthetic", "1")
    attempt = ledger.reserve(
        StructuredGenerationRequest(instructions="test", input={}, output_schema={})
    )
    ledger.finish(attempt, "succeeded")
    report = {
        "status": "partial",
        "plan": plan,
        "corpus_unchanged": True,
        "usage": {"ledger": ledger.report()},
    }
    ledger.close()
    path = tmp_path / "report.json"
    path.write_text(json.dumps(report), encoding="utf-8")
    return records, scopes, ingestion, path


def test_read_only_parent_binding_and_remaining_attempt_cap(tmp_path):
    records, scopes, ingestion, path = parent_fixture(tmp_path)
    parent = parent_binding(path, tmp_path)
    assert parent["attempts_spent"] == 1
    assert parent["remaining_attempts"] == 47
    child = build_plan(
        records, scopes, ingestion, max_records=3, max_calls=47, parent=parent
    )
    assert child["parent"] == parent
    assert child["max_calls"] + parent["attempts_spent"] == 48
    assert parent_binding(path, tmp_path) == parent
    with pytest.raises(ValueError, match="remaining attempt ceiling"):
        build_plan(
            records, scopes, ingestion, max_records=3, max_calls=48, parent=parent
        )
    with pytest.raises(ValueError, match="exact sources"):
        build_plan(
            records, scopes, ingestion, max_records=2, max_calls=47, parent=parent
        )


def test_changed_parent_ledger_is_rejected(tmp_path):
    _, _, _, path = parent_fixture(tmp_path)
    report = json.loads(path.read_text(encoding="utf-8"))
    report["usage"]["ledger"]["attempts_reserved"] = 0
    path.write_text(json.dumps(report), encoding="utf-8")
    with pytest.raises(ValueError, match="ledger changed"):
        parent_binding(path, tmp_path)


def test_nested_parent_cannot_hide_earlier_usage(tmp_path):
    _, _, _, path = parent_fixture(tmp_path)
    report = json.loads(path.read_text(encoding="utf-8"))
    report["plan"]["parent"] = {}
    path.write_text(json.dumps(report), encoding="utf-8")
    with pytest.raises(ValueError, match="settled matching"):
        parent_binding(path, tmp_path)


def test_failure_chain_reports_only_allowlisted_budget_reason():
    cause = PilotRuntimeError("total canonical request byte budget exhausted")
    error = RuntimeError("credential-and-provider-content-must-not-be-persisted")
    error.__cause__ = cause
    details = failure_details(error)
    assert details == {
        "failure_chain_types": ["RuntimeError", "PilotRuntimeError"],
        "budget_stop_reason": "total_request_bytes",
    }
    assert "credential" not in json.dumps(details)


def test_failure_chain_cycle_is_bounded_and_unknown_messages_hidden():
    cause = PilotRuntimeError("sk-this-is-a-test-secret")
    error = RuntimeError("private")
    error.__cause__ = cause
    cause.__cause__ = error
    details = failure_details(error)
    assert details["failure_chain_types"] == ["RuntimeError", "PilotRuntimeError"]
    assert details["budget_stop_reason"] is None
    assert "sk-" not in json.dumps(details)
