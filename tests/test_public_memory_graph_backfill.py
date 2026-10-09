from copy import deepcopy
from datetime import UTC, datetime

import pytest

pytest.importorskip("graphiti_core")

from benchmarks.public_memory_graph_backfill import (
    build_plan,
    writer_lock,
)
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
