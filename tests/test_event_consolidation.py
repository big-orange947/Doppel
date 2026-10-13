from __future__ import annotations

from datetime import UTC, datetime

import pytest

from benchmarks.event_consolidation_audit import ForcedMerge, audit, records
from doppel_memory import (
    ConsolidationPlanningError,
    ConsolidationRunner,
    DeterministicMemoryConsolidator,
    InMemoryStore,
    MemoryFilter,
    PersonalMemoryQueryDraft,
    PersonalMemoryQueryEngine,
    consolidation,
)


async def put(source):
    store = InMemoryStore()
    for record in source:
        await store.put(record)
    return store


@pytest.mark.parametrize(
    "difference",
    [
        "details",
        "decimal",
        "event",
        "missing",
        "one-missing",
        "start",
        "end",
        "status",
        "revision",
    ],
)
async def test_destructive_episode_merge_rejected_without_writes(difference):
    source = records(
        ["I paid 1.2 yuan."] * 2, ["one-event"] * 2, topic="activity.generic"
    )
    if difference in {"details", "decimal"}:
        source[1].content = (
            "The attendee was Sam." if difference == "details" else "I paid 12 yuan."
        )
    else:
        key, value = {
            "event": ("event_key", "other-event"),
            "missing": ("event_key", ""),
            "one-missing": ("event_key", ""),
            "start": ("valid_from", "2026-02-01T00:00:00+00:00"),
            "end": ("valid_to", "2026-02-01T00:00:00+00:00"),
            "status": ("temporal_status", "planned"),
            "revision": ("revision_kind", "retraction"),
        }[difference]
        source[1].metadata[key] = value
        if difference == "missing":
            source[0].metadata[key] = value
    store = await put(source)
    with pytest.raises(ConsolidationPlanningError, match="episode merge"):
        await ConsolidationRunner(store).plan_once(ForcedMerge(), source[0].scope)
    deterministic = await ConsolidationRunner(store).plan_once(
        DeterministicMemoryConsolidator(), source[0].scope
    )
    assert deterministic.actions == []
    assert (
        await store.scan(source[0].scope, filters=MemoryFilter(include_inactive=True))
    ).records == source


@pytest.mark.parametrize("topic", ["", "activity.generic"])
async def test_true_episode_duplicate_merge_and_replay_preserve_identity(topic):
    source = records(["I attended an event."] * 2, ["same-event"] * 2, topic=topic)
    store = await put(source)
    runner = ConsolidationRunner(store)
    plan = await runner.plan_once(DeterministicMemoryConsolidator(), source[0].scope)
    assert len(plan.actions) == 1
    first = await runner.execute(plan)
    second = await runner.execute(plan)
    assert not first.errors and not second.errors
    assert first.committable_checkpoint is not None
    assert second.actions[0].canonical_write.status == "duplicate"
    active = await store.scan(source[0].scope)
    assert len(active.records) == 1
    assert active.records[0].metadata["event_key"] == "same-event"
    assert active.records[0].content == source[0].content
    assert {
        s["memory_id"]
        for s in active.records[0].metadata["consolidation"]["source_memories"]
    } == {s.memory_id for s in source}


async def test_legacy_unsafe_plan_revalidated_before_any_write(monkeypatch):
    source = records(["First event detail", "Second event detail"], ["one"] * 2)
    store = await put(source)
    runner = ConsolidationRunner(store)
    # Simulate a serialized plan admitted by the old runner, not a forgery that
    # would be caught by plan integrity. Restore the real gate before execution.
    with monkeypatch.context() as patch:
        patch.setattr(consolidation, "_validate_episode_merge", lambda *args: None)
        plan = await runner.plan_once(ForcedMerge(), source[0].scope)
    result = await runner.execute(plan)
    assert result.committable_checkpoint is None
    assert result.actions[0].canonical_write.status == "failed"
    assert result.actions[0].transitions == []
    assert result.errors[0].stage == "decision_validate"
    assert result.errors[0].error_type == "UnsafeEpisodeMerge"
    assert (
        len(
            (
                await store.scan(
                    source[0].scope, filters=MemoryFilter(include_inactive=True)
                )
            ).records
        )
        == 2
    )


class CountPlanner:
    name, version = "test.structural-count", "1"

    async def plan(self, request):
        return PersonalMemoryQueryDraft(intent="count", memory_types=["episode"])


async def test_real_query_count_uses_keys_not_detail_records_and_keeps_both_hits():
    source = records(["I paid 340 yuan.", "I left a 25 yuan tip."], ["dinner-one"] * 2)
    store = await put(source)
    engine = PersonalMemoryQueryEngine(store)
    result = await engine.query(
        CountPlanner(),
        "Count structurally selected episodes",
        [source[0].scope],
        now=datetime(2026, 4, 1, tzinfo=UTC),
    )
    assert result.count.status == "exact" and result.count.value == 1
    assert result.count.observed_records == 2
    assert {h.record.content for h in result.hits} == {r.content for r in source}
    # No destructive merge means both details still qualify in normal queries.
    unchanged = await ConsolidationRunner(store).run_once(
        DeterministicMemoryConsolidator(), source[0].scope
    )
    assert unchanged.actions == []
    after = await engine.query(
        CountPlanner(),
        "Count structurally selected episodes",
        [source[0].scope],
        now=datetime(2026, 4, 1, tzinfo=UTC),
    )
    assert after.count == result.count


async def test_zero_model_audit_remains_structured_and_retains_failed_probe():
    result = await audit(None)
    assert (
        result["model_calls"]
        == result["external_store_writes"]
        == result["plans_executed"]
        == 0
    )
    for name, row in result["synthetic_probes"].items():
        if name == "same_event_exact_duplicate":
            assert len(row["deterministic"]["actions"]) == 1
        else:
            assert row["forced_merge"]["status"] == "rejected"
            assert row["deterministic"]["actions"] == []


async def test_reference_consolidator_exposes_event_key_and_new_identity():
    class Model:
        name, version = "fake-reference", "1"

        async def generate(self, request):
            assert request.input["memories"][0]["event_key"] == "event-one"
            assert (
                "Different details of the same event remain separate"
                in request.instructions
            )
            return {"decisions": []}

    model = consolidation.ReferenceMemoryConsolidator(Model())
    assert model.version.startswith("5.")
    source = records(["One detail"], ["event-one"])
    await model.consolidate(
        consolidation.ConsolidationInput(scope=source[0].scope, records=source)
    )
