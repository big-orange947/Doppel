from datetime import UTC, datetime

import pytest

pytest.importorskip("graphiti_core")

from benchmarks.public_memory_graph_consecutive_batch import build_batch
from benchmarks.public_memory_pilot import _hash
from doppel_memory.models import (
    Actor,
    FactAuthority,
    MemoryRecord,
    MemoryScope,
    MemoryState,
)


def sources():
    scopes = [MemoryScope(user_id=f"owner-{n}", agent_id="agent") for n in range(4)]
    records = {
        f"m-{n}": MemoryRecord(
            memory_id=f"m-{n}",
            scope=scope,
            content="source-only, not a benchmark answer",
            actor=Actor.OWNER,
            authority=FactAuthority.HUMAN_SELF,
            state=MemoryState.CONFIRMED,
            tags=["personal-memory"],
            created_at=datetime(2024, 1, 1, tzinfo=UTC),
            metadata={
                "subject": "owner",
                "subject_id": scope.user_id,
                "evidence": [{"evidence_id": f"source-{n}"}],
            },
        )
        for n, scope in enumerate(scopes)
    }
    ingestion = {
        "status": "complete",
        "all_histories_ingested": True,
        "plan": {"plan_fingerprint": "f" * 64},
        "postgres_schema": "synthetic",
        "embedding": {"name": "fake", "version": "1", "dimensions": 2},
    }
    return records, scopes, ingestion


def test_fixed_next_two_complete_scopes_and_explicit_budget():
    records, scopes, ingestion = sources()
    batch = build_batch(records, scopes, ingestion, {"manifest": "sha"}, {"count": 4})
    assert [p["scope_ordinal"] for p in batch["scope_plans"]] == [2, 3]
    assert [[t["memory_id"] for t in p["records"]] for p in batch["scope_plans"]] == [
        ["m-1"],
        ["m-2"],
    ]
    assert all(
        p["selected_records"] == p["eligible_records"] for p in batch["scope_plans"]
    )
    assert sum(p["max_calls"] for p in batch["scope_plans"]) == 3000
    assert sum(p["max_total_request_bytes"] for p in batch["scope_plans"]) == 64000000
    assert "source-only, not a benchmark answer" not in str(batch)
    for plan in [batch, *batch["scope_plans"]]:
        assert plan["plan_fingerprint"] == _hash(
            {k: v for k, v in plan.items() if k != "plan_fingerprint"}
        )


def test_incomplete_scope_inventory_rejected():
    records, scopes, ingestion = sources()
    with pytest.raises(ValueError):
        build_batch(records, scopes[:2], ingestion, {}, {})
    records.pop("m-1")
    with pytest.raises(ValueError):
        build_batch(records, scopes, ingestion, {}, {})


def test_record_snapshot_and_remaining_scopes_preserved():
    records, scopes, ingestion = sources()
    before = {k: r.model_dump(mode="json") for k, r in records.items()}
    batch = build_batch(records, scopes, ingestion, {}, {})
    assert batch["corpus_sha256"] == _hash(before)
    assert {k: r.model_dump(mode="json") for k, r in records.items()} == before
    assert not batch["reserved_histories_executed"]
    assert not batch["publication_ready"]
