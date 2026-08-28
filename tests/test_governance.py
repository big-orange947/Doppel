"""Lifecycle governance tests: conservative policy, auditability, and replay."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from doppel_memory.client import DoppelClient
from doppel_memory.governance import (
    DeterministicGovernancePolicyConfig,
    DeterministicMemoryGovernancePolicy,
    MemoryGovernanceAnalysis,
    MemoryGovernanceCheckpoint,
    MemoryGovernanceConfig,
    MemoryGovernanceDecision,
    MemoryGovernanceInput,
    MemoryGovernanceOperation,
    MemoryGovernancePlanningError,
    MemoryGovernanceReadLimitError,
    MemoryGovernanceRunner,
)
from doppel_memory.in_memory_store import InMemoryStore
from doppel_memory.models import (
    FactAuthority,
    MemoryFilter,
    MemoryRecord,
    MemoryScope,
    MemoryState,
    WriteStatus,
)

NOW = datetime(2026, 8, 28, 12, tzinfo=UTC)
SCOPE = MemoryScope(user_id="owner", agent_id="assistant", platform="test")


def _record(
    content: str,
    *,
    memory_type: str = "fact",
    importance: float = 0.5,
    authority: FactAuthority = FactAuthority.HUMAN_SELF,
    state: MemoryState = MemoryState.CONFIRMED,
    valid_to: str | None = None,
    retention_class: str = "",
    evidence_count: int = 1,
) -> MemoryRecord:
    metadata = {
        "personal_memory_type": memory_type,
        "subject": "owner",
        "temporal_status": "current",
        "evidence": [
            {
                "evidence_id": f"evidence-{index}",
                "message_id": f"message-{index}",
                "actor": "owner",
                "at": "2026-01-01T00:00:00+00:00",
            }
            for index in range(evidence_count)
        ],
    }
    if valid_to is not None:
        metadata["valid_to"] = valid_to
    if retention_class:
        metadata["retention_class"] = retention_class
    return MemoryRecord(
        scope=SCOPE,
        content=content,
        authority=authority,
        state=state,
        importance=importance,
        tags=["personal-memory"],
        extractor="tests",
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
        updated_at=datetime(2026, 1, 1, tzinfo=UTC),
        metadata=metadata,
    )


async def _put(store: InMemoryStore, record: MemoryRecord) -> MemoryRecord:
    result = await store.put(record)
    assert result.record is not None
    return result.record


async def test_default_policy_is_conservative_and_type_aware() -> None:
    policy = DeterministicMemoryGovernancePolicy()
    records = [
        _record(
            "两个月的北京出差已经结束。",
            memory_type="state",
            valid_to="2026-06-01T00:00:00+00:00",
        ).model_copy(update={"memory_id": "expired-state"}),
        _record(
            "用户长期住在上海。",
            memory_type="fact",
            valid_to="2020-01-01T00:00:00+00:00",
        ).model_copy(update={"memory_id": "long-term-fact"}),
        _record(
            "用户喜欢清淡饮食。", memory_type="preference", evidence_count=1
        ).model_copy(update={"memory_id": "old-preference"}),
        _record("临时提醒", retention_class="ephemeral", evidence_count=1).model_copy(
            update={"memory_id": "opt-in-but-decay-disabled"}
        ),
    ]

    analysis = await policy.evaluate(
        MemoryGovernanceInput(scope=SCOPE, records=records, now=NOW)
    )

    assert [(item.operation, item.source_memory_id) for item in analysis.decisions] == [
        (MemoryGovernanceOperation.ARCHIVE, "expired-state")
    ]


async def test_policy_reinforces_new_distinct_trusted_evidence_once() -> None:
    policy = DeterministicMemoryGovernancePolicy()
    source = _record("用户住在上海。", evidence_count=3, importance=0.5).model_copy(
        update={"memory_id": "memory-a"}
    )
    analysis = await policy.evaluate(
        MemoryGovernanceInput(scope=SCOPE, records=[source], now=NOW)
    )
    assert len(analysis.decisions) == 1
    assert analysis.decisions[0].operation == MemoryGovernanceOperation.REINFORCE
    assert analysis.decisions[0].target_importance == pytest.approx(0.6)

    governed = source.model_copy(
        update={
            "metadata": {
                **source.metadata,
                "governance": {
                    "operation": "reinforce",
                    "observed_evidence_count": 3,
                },
            }
        }
    )
    repeated = await policy.evaluate(
        MemoryGovernanceInput(scope=SCOPE, records=[governed], now=NOW)
    )
    assert repeated.decisions == []

    untrusted = source.model_copy(update={"authority": FactAuthority.AGENT_OUTPUT})
    rejected = await policy.evaluate(
        MemoryGovernanceInput(scope=SCOPE, records=[untrusted], now=NOW)
    )
    assert rejected.decisions == []


async def test_decay_requires_host_opt_in_and_is_interval_limited() -> None:
    policy = DeterministicMemoryGovernancePolicy(
        DeterministicGovernancePolicyConfig(enable_decay=True, decay_after_days=30)
    )
    normal = _record("普通长期事实", evidence_count=1).model_copy(
        update={"memory_id": "normal"}
    )
    ephemeral = _record(
        "临时线索", retention_class="ephemeral", importance=0.5, evidence_count=1
    ).model_copy(update={"memory_id": "ephemeral"})

    analysis = await policy.evaluate(
        MemoryGovernanceInput(scope=SCOPE, records=[normal, ephemeral], now=NOW)
    )
    assert len(analysis.decisions) == 1
    assert analysis.decisions[0].source_memory_id == "ephemeral"
    assert analysis.decisions[0].operation == MemoryGovernanceOperation.DECAY
    assert analysis.decisions[0].target_importance == pytest.approx(0.4)

    recently_decayed = ephemeral.model_copy(
        update={
            "metadata": {
                **ephemeral.metadata,
                "governance": {
                    "operation": "decay",
                    "evaluated_at": "2026-08-20T00:00:00+00:00",
                },
            }
        }
    )
    repeated = await policy.evaluate(
        MemoryGovernanceInput(scope=SCOPE, records=[recently_decayed], now=NOW)
    )
    assert repeated.decisions == []


async def test_governance_cycle_writes_auditable_snapshots_and_replays() -> None:
    store = InMemoryStore()
    expiring = await _put(
        store,
        _record(
            "北京临时出差。",
            memory_type="state",
            valid_to="2026-06-01T00:00:00+00:00",
        ),
    )
    reinforced = await _put(
        store, _record("用户住在上海。", evidence_count=3, importance=0.5)
    )
    runner = MemoryGovernanceRunner(store)
    plan = await runner.plan_once(
        DeterministicMemoryGovernancePolicy(), SCOPE, now=NOW, run_id="cycle-1"
    )

    assert plan.plan_id.startswith("gpl_")
    assert {action.operation for action in plan.actions} == {"archive", "reinforce"}
    result = await runner.execute(plan)
    assert result.errors == []
    assert result.committable_checkpoint is not None
    assert all(action.complete for action in result.actions)

    old_expiring = await store.get(SCOPE, expiring.memory_id)
    old_reinforced = await store.get(SCOPE, reinforced.memory_id)
    assert old_expiring is not None and old_expiring.state is MemoryState.SUPERSEDED
    assert old_reinforced is not None and old_reinforced.state is MemoryState.SUPERSEDED

    page = await store.scan(
        SCOPE, filters=MemoryFilter(include_inactive=True), limit=100
    )
    archives = [
        record for record in page.records if "governance-archive" in record.tags
    ]
    active = [
        record
        for record in page.records
        if record.state in {MemoryState.CANDIDATE, MemoryState.CONFIRMED}
    ]
    assert len(archives) == 1
    assert archives[0].state is MemoryState.EXPIRED
    assert archives[0].metadata["governance"]["source_memory_id"] == expiring.memory_id
    assert archives[0].metadata["governance"]["source_fingerprint"]
    assert len(active) == 1
    assert active[0].importance == pytest.approx(0.6)
    assert active[0].metadata["governance"]["observed_evidence_count"] == 3

    replay = await runner.execute(plan)
    assert replay.errors == []
    assert all(
        action.replacement_write.status is WriteStatus.DUPLICATE
        and action.transition is not None
        and action.transition.status == "already_applied"
        for action in replay.actions
    )
    replay_page = await store.scan(
        SCOPE, filters=MemoryFilter(include_inactive=True), limit=100
    )
    assert len(replay_page.records) == len(page.records)


async def test_restore_is_explicit_preserves_temporal_meaning_and_replays() -> None:
    store = InMemoryStore()
    await _put(
        store,
        _record(
            "北京临时出差。",
            memory_type="state",
            valid_to="2026-06-01T00:00:00+00:00",
        ),
    )
    runner = MemoryGovernanceRunner(store)
    archived = await runner.run_once(
        DeterministicMemoryGovernancePolicy(), SCOPE, now=NOW
    )
    archive_record = archived.actions[0].replacement_write.record
    assert archive_record is not None

    restore_plan = await runner.plan_restore(
        SCOPE,
        archive_record.memory_id,
        target_state=MemoryState.CANDIDATE,
        now=datetime(2026, 8, 29, tzinfo=UTC),
        run_id="restore-1",
    )
    restored = await runner.execute(restore_plan)
    assert restored.errors == []
    replacement = restored.actions[0].replacement_write.record
    assert replacement is not None
    assert replacement.state is MemoryState.CANDIDATE
    assert replacement.metadata["valid_to"] == "2026-06-01T00:00:00+00:00"
    assert replacement.metadata["governance"]["operation"] == "restore"
    assert "governance:restore" in replacement.tags
    assert "governance:archive" not in replacement.tags
    assert "governance-archive" not in replacement.tags
    unchanged_archive = await store.get(SCOPE, archive_record.memory_id)
    assert unchanged_archive is not None
    assert unchanged_archive.state is MemoryState.EXPIRED

    replay = await runner.execute(restore_plan)
    assert replay.errors == []
    assert replay.actions[0].replacement_write.status is WriteStatus.DUPLICATE
    assert replay.actions[0].transition is not None
    assert replay.actions[0].transition.status == "not_required"


async def test_restore_rejects_arbitrary_expired_record() -> None:
    store = InMemoryStore()
    expired = await _put(store, _record("普通失效记录", state=MemoryState.EXPIRED))
    with pytest.raises(MemoryGovernancePlanningError, match="archive snapshot"):
        await MemoryGovernanceRunner(store).plan_restore(SCOPE, expired.memory_id)


async def test_client_facade_runs_default_governance_and_restore() -> None:
    store = InMemoryStore()
    await _put(
        store,
        _record(
            "已结束的临时状态",
            memory_type="state",
            valid_to="2026-06-01T00:00:00+00:00",
        ),
    )
    client = DoppelClient(store)
    governed = await client.govern_personal_memory(SCOPE, now=NOW)
    archive = governed.actions[0].replacement_write.record
    assert archive is not None and archive.state is MemoryState.EXPIRED

    restored = await client.restore_personal_memory(SCOPE, archive.memory_id, now=NOW)
    replacement = restored.actions[0].replacement_write.record
    assert replacement is not None and replacement.state is MemoryState.CANDIDATE


async def test_plan_integrity_and_source_conflicts_fail_closed() -> None:
    store = InMemoryStore()
    source = await _put(store, _record("用户住在上海。", evidence_count=3))
    runner = MemoryGovernanceRunner(store)
    plan = await runner.plan_once(DeterministicMemoryGovernancePolicy(), SCOPE, now=NOW)
    tampered = plan.model_copy(update={"run_id": "tampered"})
    with pytest.raises(MemoryGovernancePlanningError, match="plan_id"):
        await runner.execute(tampered)

    await store.transition(
        SCOPE,
        source.memory_id,
        MemoryState.REJECTED,
        expected_state=MemoryState.CONFIRMED,
    )
    conflicted = await runner.execute(plan)
    assert conflicted.committable_checkpoint is None
    assert conflicted.actions[0].replacement_write.status is WriteStatus.FAILED
    assert conflicted.errors[0].stage == "source_validate"


async def test_policy_output_is_bound_to_known_unique_active_sources() -> None:
    class UnsafePolicy:
        name = "tests.unsafe"
        version = "1"

        async def evaluate(
            self, input: MemoryGovernanceInput
        ) -> MemoryGovernanceAnalysis:
            del input
            return MemoryGovernanceAnalysis(
                decisions=[
                    MemoryGovernanceDecision(
                        operation="archive",
                        source_memory_id="unknown",
                        reason="unsafe",
                    )
                ]
            )

    store = InMemoryStore()
    await _put(store, _record("known"))
    with pytest.raises(MemoryGovernancePlanningError, match="unknown"):
        await MemoryGovernanceRunner(store).plan_once(UnsafePolicy(), SCOPE, now=NOW)


async def test_checkpoint_identity_and_read_bounds_are_enforced() -> None:
    store = InMemoryStore()
    await _put(store, _record("one"))
    runner = MemoryGovernanceRunner(store, MemoryGovernanceConfig(max_records=1))
    foreign = MemoryGovernanceCheckpoint(policy="another-policy")
    with pytest.raises(MemoryGovernancePlanningError, match="another policy"):
        await runner.plan_once(
            DeterministicMemoryGovernancePolicy(),
            SCOPE,
            now=NOW,
            checkpoint=foreign,
        )

    await _put(store, _record("two"))
    with pytest.raises(MemoryGovernanceReadLimitError, match="max_records 1"):
        await runner.plan_once(DeterministicMemoryGovernancePolicy(), SCOPE, now=NOW)


def test_decision_schema_rejects_invalid_importance_direction_shape() -> None:
    with pytest.raises(ValueError, match="requires target_importance"):
        MemoryGovernanceDecision(
            operation="decay", source_memory_id="memory", reason="because"
        )
    with pytest.raises(ValueError, match="must not change importance"):
        MemoryGovernanceDecision(
            operation="archive",
            source_memory_id="memory",
            target_importance=0.2,
            reason="because",
        )


def test_policy_config_fingerprint_is_set_order_independent() -> None:
    first = DeterministicGovernancePolicyConfig(
        expirable_memory_types=frozenset({"state", "plan"}),
        ephemeral_retention_classes=frozenset({"short", "ephemeral"}),
    )
    second = DeterministicGovernancePolicyConfig(
        expirable_memory_types=frozenset({"plan", "state"}),
        ephemeral_retention_classes=frozenset({"ephemeral", "short"}),
    )
    assert first.fingerprint == second.fingerprint
