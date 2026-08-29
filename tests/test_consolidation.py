"""Consolidation decisions, scope guards, optimistic races, and replay safety."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from doppel_memory.consolidation import (
    ConsolidationAnalysis,
    ConsolidationConfig,
    ConsolidationDecision,
    ConsolidationInput,
    ConsolidationPlanningError,
    ConsolidationReadLimitError,
    ConsolidationRunner,
    DeterministicMemoryConsolidator,
    ReferenceMemoryConsolidator,
)
from doppel_memory.in_memory_store import InMemoryStore
from doppel_memory.intelligence import StructuredGenerationRequest
from doppel_memory.models import (
    Actor,
    FactAuthority,
    MemoryFilter,
    MemoryRecord,
    MemoryScope,
    MemoryState,
    MemoryStateConflictError,
    WriteStatus,
)

SCOPE = MemoryScope(user_id="owner", agent_id="personal-agent")
OTHER_SCOPE = MemoryScope(user_id="other", agent_id="personal-agent")


def _record(
    memory_id: str,
    content: str,
    *,
    day: int,
    topic_key: str = "",
    memory_type: str = "preference",
    temporal_status: str = "current",
    scope: MemoryScope = SCOPE,
    state: MemoryState = MemoryState.CANDIDATE,
    revision_kind: str = "assertion",
) -> MemoryRecord:
    return MemoryRecord(
        memory_id=memory_id,
        scope=scope,
        content=content,
        kind="fact",
        actor=Actor.OWNER,
        authority=FactAuthority.HUMAN_SELF,
        state=state,
        tags=["personal-memory", memory_type],
        source_event_id=f"event-{memory_id}",
        source_message_id=f"message-{memory_id}",
        extractor="tests.personal-memory",
        created_at=datetime(2026, 1, day, tzinfo=UTC),
        updated_at=datetime(2026, 1, day, tzinfo=UTC),
        metadata={
            "personal_memory_type": memory_type,
            "topic_key": topic_key,
            "subject": Actor.OWNER,
            "subject_id": scope.user_id,
            "temporal_status": temporal_status,
            "revision_kind": revision_kind,
            "valid_from": datetime(2026, 1, day, tzinfo=UTC).isoformat(),
            "evidence": [
                {
                    "evidence_id": f"message-{memory_id}",
                    "message_id": f"message-{memory_id}",
                    "event_id": f"event-{memory_id}",
                    "actor": Actor.OWNER,
                    "at": datetime(2026, 1, day, tzinfo=UTC).isoformat(),
                }
            ],
        },
    )


async def _put(store: InMemoryStore, *records: MemoryRecord) -> None:
    for record in records:
        result = await store.put(record)
        assert result.status is WriteStatus.CREATED


async def test_deterministic_duplicate_merge_unions_evidence_and_supersedes_sources() -> (
    None
):
    store = InMemoryStore()
    first = _record("coffee-1", "用户不喝咖啡。", day=1)
    second = _record("coffee-2", "用户不喝咖啡", day=2)
    await _put(store, first, second)

    result = await ConsolidationRunner(store).run_once(
        DeterministicMemoryConsolidator(),
        SCOPE,
        run_id="merge-duplicates",
    )

    assert not result.errors
    assert result.committable_checkpoint is not None
    assert result.committable_checkpoint.cycle == 1
    assert len(result.actions) == 1
    action = result.actions[0]
    assert action.operation == "merge"
    assert action.complete is True
    assert action.canonical_write.status is WriteStatus.CREATED
    canonical = action.canonical_write.record
    assert canonical is not None
    assert canonical.content == second.content
    assert canonical.state is MemoryState.CANDIDATE
    assert canonical.metadata["consolidation"]["canonical_source_memory_id"] == (
        second.memory_id
    )
    assert {item["evidence_id"] for item in canonical.metadata["evidence"]} == {
        "message-coffee-1",
        "message-coffee-2",
    }
    assert set(canonical.metadata["derived_chain"]) == {
        "memory:coffee-1",
        "memory:coffee-2",
    }
    stored_first = await store.get(SCOPE, first.memory_id)
    stored_second = await store.get(SCOPE, second.memory_id)
    assert stored_first is not None and stored_first.state is MemoryState.SUPERSEDED
    assert stored_second is not None and stored_second.state is MemoryState.SUPERSEDED
    active = await store.scan(
        SCOPE,
        filters=MemoryFilter(tags={"personal-memory"}),
        limit=20,
    )
    assert [record.memory_id for record in active.records] == [canonical.memory_id]


async def test_explicit_topic_slot_correction_keeps_newest_current_claim() -> None:
    store = InMemoryStore()
    old = _record(
        "color-blue",
        "用户最喜欢蓝色。",
        day=1,
        topic_key="preference.favorite-color",
    )
    new = _record(
        "color-green",
        "用户现在最喜欢绿色。",
        day=5,
        topic_key="preference.favorite-color",
        revision_kind="correction",
    )
    await _put(store, old, new)

    result = await ConsolidationRunner(store).run_once(
        DeterministicMemoryConsolidator(), SCOPE, run_id="correct-color"
    )

    assert not result.errors
    assert result.actions[0].operation == "correct"
    canonical = result.actions[0].canonical_write.record
    assert canonical is not None
    assert canonical.content == "用户现在最喜欢绿色。"
    assert canonical.metadata["topic_key"] == "preference.favorite-color"
    assert canonical.metadata["consolidation"]["operation"] == "correct"
    stored_old = await store.get(SCOPE, "color-blue")
    stored_new = await store.get(SCOPE, "color-green")
    assert stored_old is not None and stored_old.state is MemoryState.SUPERSEDED
    assert stored_new is not None and stored_new.state is MemoryState.SUPERSEDED


async def test_unmarked_divergent_claims_create_replay_safe_open_conflict() -> None:
    store = InMemoryStore()
    first = _record(
        "home-shanghai",
        "用户现在住在上海。",
        day=1,
        topic_key="residence.primary",
        memory_type="state",
    )
    second = _record(
        "home-hangzhou",
        "用户现在住在杭州。",
        day=2,
        topic_key="residence.primary",
        memory_type="state",
    )
    await _put(store, first, second)
    runner = ConsolidationRunner(store)

    result = await runner.run_once(
        DeterministicMemoryConsolidator(), SCOPE, run_id="open-conflict"
    )

    assert not result.errors
    assert result.committable_checkpoint is not None
    assert len(result.actions) == 1
    action = result.actions[0]
    assert action.operation == "conflict"
    assert action.complete is True
    assert action.transitions == []
    marker = action.canonical_write.record
    assert marker is not None
    assert marker.kind == "memory_conflict"
    assert marker.authority is FactAuthority.DERIVED_SUMMARY
    assert marker.tags == ["memory-conflict", "open"]
    assert marker.metadata["conflict"]["status"] == "open"
    assert marker.metadata["consolidation"]["canonical_source_memory_id"] == ""
    assert {
        item["memory_id"] for item in marker.metadata["conflict"]["source_memories"]
    } == {first.memory_id, second.memory_id}
    assert (await store.get(SCOPE, first.memory_id)).state is MemoryState.CANDIDATE
    assert (await store.get(SCOPE, second.memory_id)).state is MemoryState.CANDIDATE

    replayed = await runner.run_once(
        DeterministicMemoryConsolidator(), SCOPE, run_id="replay-conflict"
    )

    assert not replayed.errors
    assert replayed.actions[0].canonical_write.status is WriteStatus.DUPLICATE
    markers = await store.scan(
        SCOPE,
        filters=MemoryFilter(tags={"memory-conflict"}),
        limit=20,
    )
    assert [record.memory_id for record in markers.records] == [marker.memory_id]


async def test_correction_does_not_supersede_historical_claims_in_same_topic() -> None:
    store = InMemoryStore()
    historical = _record(
        "historical-beijing",
        "用户去年住在北京。",
        day=6,
        topic_key="residence.primary",
        temporal_status="historical",
    )
    old_current = _record(
        "current-shanghai",
        "用户住在上海。",
        day=1,
        topic_key="residence.primary",
    )
    new_current = _record(
        "current-hangzhou",
        "用户现在住在杭州。",
        day=5,
        topic_key="residence.primary",
        revision_kind="correction",
    )
    await _put(store, historical, old_current, new_current)

    result = await ConsolidationRunner(store).run_once(
        DeterministicMemoryConsolidator(), SCOPE, run_id="preserve-history"
    )

    assert not result.errors
    assert len(result.actions) == 1
    action = result.actions[0]
    assert action.operation == "correct"
    assert {item.memory_id for item in action.transitions} == {
        "current-shanghai",
        "current-hangzhou",
    }
    canonical = action.canonical_write.record
    assert canonical is not None
    assert canonical.content == "用户现在住在杭州。"
    stored_historical = await store.get(SCOPE, "historical-beijing")
    assert stored_historical is not None
    assert stored_historical.state is MemoryState.CANDIDATE


async def test_current_and_planned_claims_coexist_in_one_topic_slot() -> None:
    store = InMemoryStore()
    await _put(
        store,
        _record(
            "current-shanghai",
            "用户现在住在上海。",
            day=1,
            topic_key="residence.primary",
            temporal_status="current",
        ),
        _record(
            "planned-beijing",
            "用户计划下个月去北京住两个月。",
            day=2,
            topic_key="residence.primary",
            temporal_status="planned",
        ),
    )

    result = await ConsolidationRunner(store).run_once(
        DeterministicMemoryConsolidator(), SCOPE, run_id="current-plus-plan"
    )

    assert result.plan.actions == []
    assert result.committable_checkpoint is not None


@pytest.mark.parametrize("revision_kind", ["correction", "retraction"])
async def test_historical_revision_retires_one_active_planned_slot(
    revision_kind: str,
) -> None:
    store = InMemoryStore()
    planned = _record(
        "planned-beijing-meeting",
        "用户下周三去北京开会。",
        day=1,
        topic_key="travel.plan",
        memory_type="plan",
        temporal_status="planned",
    )
    cancelled = _record(
        "cancelled-beijing-meeting",
        "下周的会取消了，改成线上。",
        day=3,
        topic_key="travel.plan",
        memory_type="plan",
        temporal_status="historical",
        revision_kind=revision_kind,
    )
    await _put(store, planned, cancelled)

    result = await ConsolidationRunner(store).run_once(
        DeterministicMemoryConsolidator(),
        SCOPE,
        run_id=f"revise-planned-meeting:{revision_kind}",
    )

    assert not result.errors
    assert len(result.actions) == 1
    action = result.actions[0]
    assert action.operation == "correct"
    assert action.canonical_write.record is not None
    assert action.canonical_write.record.content == cancelled.content
    assert (await store.get(SCOPE, planned.memory_id)).state is MemoryState.SUPERSEDED
    assert (
        await store.get(SCOPE, cancelled.memory_id)
    ).state is MemoryState.SUPERSEDED


async def test_historical_retraction_does_not_guess_between_current_and_planned() -> None:
    store = InMemoryStore()
    await _put(
        store,
        _record(
            "current-plan-slot",
            "用户当前在线参会。",
            day=1,
            topic_key="meeting.mode",
            memory_type="plan",
            temporal_status="current",
        ),
        _record(
            "planned-plan-slot",
            "用户下周线下参会。",
            day=2,
            topic_key="meeting.mode",
            memory_type="plan",
            temporal_status="planned",
        ),
        _record(
            "historical-retraction",
            "线下参会计划已取消。",
            day=3,
            topic_key="meeting.mode",
            memory_type="plan",
            temporal_status="historical",
            revision_kind="retraction",
        ),
    )

    result = await ConsolidationRunner(store).run_once(
        DeterministicMemoryConsolidator(), SCOPE, run_id="ambiguous-retraction"
    )

    assert not result.errors
    assert result.plan.actions == []


async def test_equal_text_current_and_historical_claims_do_not_merge() -> None:
    store = InMemoryStore()
    await _put(
        store,
        _record(
            "same-city-historical",
            "用户住在上海。",
            day=1,
            topic_key="residence.primary",
            memory_type="state",
            temporal_status="historical",
        ),
        _record(
            "same-city-current",
            "用户住在上海。",
            day=2,
            topic_key="residence.primary",
            memory_type="state",
            temporal_status="current",
        ),
    )

    result = await ConsolidationRunner(store).run_once(
        DeterministicMemoryConsolidator(), SCOPE
    )

    assert not result.errors
    assert result.plan.actions == []


async def test_tied_latest_revision_cannot_correct_an_older_claim() -> None:
    store = InMemoryStore()
    await _put(
        store,
        _record(
            "old-color",
            "用户最喜欢蓝色。",
            day=1,
            topic_key="preference.favorite-color",
        ),
        _record(
            "tied-color-green",
            "用户最喜欢绿色。",
            day=5,
            topic_key="preference.favorite-color",
            revision_kind="correction",
        ),
        _record(
            "tied-color-red",
            "用户最喜欢红色。",
            day=5,
            topic_key="preference.favorite-color",
            revision_kind="correction",
        ),
    )

    result = await ConsolidationRunner(store).run_once(
        DeterministicMemoryConsolidator(), SCOPE
    )

    assert not result.errors
    assert result.actions[0].operation == "conflict"
    assert result.actions[0].transitions == []


async def test_different_claims_without_topic_key_are_not_silently_corrected() -> None:
    store = InMemoryStore()
    await _put(
        store,
        _record("hobby-hiking", "用户喜欢爬山。", day=1),
        _record("hobby-swimming", "用户喜欢游泳。", day=2),
    )

    result = await ConsolidationRunner(store).run_once(
        DeterministicMemoryConsolidator(), SCOPE, run_id="unrelated"
    )

    assert result.plan.actions == []
    assert result.actions == []
    assert result.committable_checkpoint is not None
    hiking = await store.get(SCOPE, "hobby-hiking")
    swimming = await store.get(SCOPE, "hobby-swimming")
    assert hiking is not None and hiking.state is MemoryState.CANDIDATE
    assert swimming is not None and swimming.state is MemoryState.CANDIDATE


@pytest.mark.parametrize(
    "records",
    [
        (
            _record(
                "trip-1",
                "用户去北京旅行。",
                day=1,
                memory_type="episode",
                topic_key="",
            ),
            _record(
                "trip-2",
                "用户去北京旅行。",
                day=2,
                memory_type="episode",
                topic_key="",
            ),
        ),
        (
            _record(
                "preference-1",
                "用户偏好安静的环境。",
                day=1,
                topic_key="hotel.environment",
            ),
            _record(
                "preference-2",
                "用户偏好安静的环境。",
                day=2,
                topic_key="office.environment",
            ),
        ),
    ],
)
async def test_similar_episodes_and_different_topics_do_not_false_merge(
    records: tuple[MemoryRecord, MemoryRecord],
) -> None:
    store = InMemoryStore()
    await _put(store, *records)

    result = await ConsolidationRunner(store).run_once(
        DeterministicMemoryConsolidator(), SCOPE
    )

    assert result.plan.actions == []
    assert result.committable_checkpoint is not None


class _DecisionConsolidator:
    name = "tests.decision-consolidator"
    version = "1"

    def __init__(self, decisions: list[dict[str, Any]]) -> None:
        self.decisions = decisions

    async def consolidate(self, input: ConsolidationInput) -> ConsolidationAnalysis:
        del input
        return ConsolidationAnalysis.model_validate({"decisions": self.decisions})


async def test_unknown_and_overlapping_sources_are_rejected_before_writes() -> None:
    store = InMemoryStore()
    await _put(
        store,
        _record("one", "用户喜欢茶。", day=1),
        _record("two", "用户喜欢茶。", day=2),
        _record("three", "用户喜欢茶。", day=3),
    )
    runner = ConsolidationRunner(store)
    with pytest.raises(ConsolidationPlanningError, match="unknown memory"):
        await runner.plan_once(
            _DecisionConsolidator(
                [
                    {
                        "operation": "merge",
                        "source_memory_ids": ["one", "other-user-memory"],
                        "canonical_source_memory_id": "one",
                        "explanation": "invalid cross-scope reference",
                    }
                ]
            ),
            SCOPE,
        )
    with pytest.raises(ConsolidationPlanningError, match="multiple decisions"):
        await runner.plan_once(
            _DecisionConsolidator(
                [
                    {
                        "operation": "merge",
                        "source_memory_ids": ["one", "two"],
                        "canonical_source_memory_id": "two",
                        "explanation": "first",
                    },
                    {
                        "operation": "merge",
                        "source_memory_ids": ["two", "three"],
                        "canonical_source_memory_id": "three",
                        "explanation": "overlap",
                    },
                ]
            ),
            SCOPE,
        )
    assert len((await store.scan(SCOPE, limit=20)).records) == 3


async def test_correction_requires_one_trusted_nonempty_topic_slot() -> None:
    store = InMemoryStore()
    await _put(
        store,
        _record("old", "用户住在北京。", day=1, topic_key=""),
        _record("new", "用户住在上海。", day=2, topic_key=""),
    )
    decision = _DecisionConsolidator(
        [
            {
                "operation": "correct",
                "source_memory_ids": ["old", "new"],
                "canonical_source_memory_id": "new",
                "explanation": "model tried to correct without a stable slot",
            }
        ]
    )

    with pytest.raises(ConsolidationPlanningError, match="non-empty topic_key"):
        await ConsolidationRunner(store).plan_once(decision, SCOPE)


async def test_model_correction_cannot_mix_current_and_planned_claims() -> None:
    store = InMemoryStore()
    await _put(
        store,
        _record(
            "current-home",
            "用户现在住在上海。",
            day=1,
            topic_key="residence.primary",
            temporal_status="current",
        ),
        _record(
            "planned-trip",
            "用户计划去北京住两个月。",
            day=2,
            topic_key="residence.primary",
            temporal_status="planned",
        ),
    )
    decision = _DecisionConsolidator(
        [
            {
                "operation": "correct",
                "source_memory_ids": ["current-home", "planned-trip"],
                "canonical_source_memory_id": "planned-trip",
                "explanation": "unsafe inference that a plan already happened",
            }
        ]
    )

    with pytest.raises(ConsolidationPlanningError, match="temporal_status"):
        await ConsolidationRunner(store).plan_once(decision, SCOPE)


class _FailOnceTransitionStore(InMemoryStore):
    def __init__(self, fail_memory_id: str) -> None:
        super().__init__()
        self.fail_memory_id = fail_memory_id
        self.failed = False

    async def transition(
        self,
        scope: MemoryScope,
        memory_id: str,
        to_state: MemoryState,
        *,
        expected_state: MemoryState | None = None,
    ) -> MemoryRecord:
        if memory_id == self.fail_memory_id and not self.failed:
            self.failed = True
            raise MemoryStateConflictError("injected transition race")
        return await super().transition(
            scope,
            memory_id,
            to_state,
            expected_state=expected_state,
        )


async def test_partial_failure_replays_original_plan_without_duplicate_canonical() -> (
    None
):
    store = _FailOnceTransitionStore("duplicate-2")
    await _put(
        store,
        _record("duplicate-1", "用户不喝咖啡。", day=1),
        _record("duplicate-2", "用户不喝咖啡。", day=2),
    )
    runner = ConsolidationRunner(store)
    plan = await runner.plan_once(
        DeterministicMemoryConsolidator(), SCOPE, run_id="replay-plan"
    )

    failed = await runner.execute(plan)

    assert failed.committable_checkpoint is None
    assert failed.actions[0].canonical_write.status is WriteStatus.CREATED
    assert [item.status for item in failed.actions[0].transitions] == [
        "transitioned",
        "failed",
    ]

    replayed = await runner.execute(plan)

    assert not replayed.errors
    assert replayed.committable_checkpoint == plan.next_checkpoint
    assert replayed.actions[0].canonical_write.status is WriteStatus.DUPLICATE
    assert [item.status for item in replayed.actions[0].transitions] == [
        "already_applied",
        "transitioned",
    ]
    all_records = await store.scan(
        SCOPE,
        filters=MemoryFilter(include_inactive=True),
        limit=20,
    )
    canonical_records = [
        record
        for record in all_records.records
        if record.metadata.get("consolidation", {}).get("decision_id")
        == plan.actions[0].decision_id
    ]
    assert len(canonical_records) == 1


async def test_source_version_race_blocks_canonical_write_and_checkpoint() -> None:
    store = InMemoryStore()
    await _put(
        store,
        _record("race-1", "用户喜欢绿色。", day=1),
        _record("race-2", "用户喜欢绿色。", day=2),
    )
    runner = ConsolidationRunner(store)
    plan = await runner.plan_once(DeterministicMemoryConsolidator(), SCOPE)
    await store.transition(
        SCOPE,
        "race-1",
        MemoryState.REJECTED,
        expected_state=MemoryState.CANDIDATE,
    )

    result = await runner.execute(plan)

    assert result.committable_checkpoint is None
    assert result.actions[0].canonical_write.error_code == "source_conflict"
    assert any(error.stage == "source_validate" for error in result.errors)
    all_records = await store.scan(
        SCOPE, filters=MemoryFilter(include_inactive=True), limit=20
    )
    assert len(all_records.records) == 2


async def test_serialized_plan_tampering_is_rejected_before_execution() -> None:
    store = InMemoryStore()
    await _put(
        store,
        _record("plan-1", "用户喜欢绿色。", day=1),
        _record("plan-2", "用户喜欢绿色。", day=2),
    )
    runner = ConsolidationRunner(store)
    plan = await runner.plan_once(
        DeterministicMemoryConsolidator(), SCOPE, run_id="original"
    )
    tampered = plan.model_copy(update={"run_id": "tampered"})

    with pytest.raises(ConsolidationPlanningError, match="plan_id"):
        await runner.execute(tampered)

    assert len((await store.scan(SCOPE, limit=20)).records) == 2


class _StubStructuredModel:
    name = "tests.consolidation-model"
    version = "1"

    def __init__(self, result: dict[str, Any]) -> None:
        self.result = result
        self.requests: list[StructuredGenerationRequest] = []

    async def generate(self, request: StructuredGenerationRequest):
        self.requests.append(request)
        return self.result


async def test_reference_consolidator_only_selects_existing_canonical_content() -> None:
    first = _record("old-city", "用户住在北京。", day=1, topic_key="residence.primary")
    second = _record(
        "new-city",
        "用户现在住在上海。",
        day=2,
        topic_key="residence.primary",
        revision_kind="correction",
    )
    model = _StubStructuredModel(
        {
            "decisions": [
                {
                    "operation": "correct",
                    "source_memory_ids": ["old-city", "new-city"],
                    "canonical_source_memory_id": "new-city",
                    "confidence": 0.97,
                    "explanation": "new explicit residence replaces old residence",
                }
            ]
        }
    )
    consolidator = ReferenceMemoryConsolidator(model)

    analysis = await consolidator.consolidate(
        ConsolidationInput(scope=SCOPE, records=[first, second])
    )

    assert analysis.decisions[0].canonical_source_memory_id == "new-city"
    request = model.requests[0]
    assert "do not generate replacement content" in request.instructions.lower()
    assert request.input["memories"][1]["content"] == second.content
    assert request.output_schema["title"] == "ConsolidationAnalysis"


async def test_runner_rejects_model_correction_without_explicit_revision() -> None:
    store = InMemoryStore()
    await _put(
        store,
        _record(
            "unsafe-old-city",
            "用户住在北京。",
            day=1,
            topic_key="residence.primary",
            memory_type="state",
        ),
        _record(
            "unsafe-new-city",
            "用户住在上海。",
            day=2,
            topic_key="residence.primary",
            memory_type="state",
        ),
    )
    model = _StubStructuredModel(
        {
            "decisions": [
                {
                    "operation": "correct",
                    "source_memory_ids": ["unsafe-old-city", "unsafe-new-city"],
                    "canonical_source_memory_id": "unsafe-new-city",
                    "confidence": 0.99,
                    "explanation": "unsafe newest wins",
                }
            ]
        }
    )

    with pytest.raises(ConsolidationPlanningError, match="explicit correction"):
        await ConsolidationRunner(store).plan_once(
            ReferenceMemoryConsolidator(model), SCOPE
        )


async def test_full_scope_record_bound_fails_instead_of_partial_consolidation() -> None:
    store = InMemoryStore()
    await _put(
        store,
        _record("limit-1", "用户喜欢茶。", day=1),
        _record("limit-2", "用户喜欢茶。", day=2),
        _record("limit-3", "用户喜欢茶。", day=3),
    )

    with pytest.raises(ConsolidationReadLimitError, match="max_records"):
        await ConsolidationRunner(
            store, ConsolidationConfig(page_size=2, max_records=2)
        ).plan_once(DeterministicMemoryConsolidator(), SCOPE)


def test_decision_models_reject_generated_content_scope_and_invalid_sources() -> None:
    with pytest.raises(ValueError, match="canonical source must be included"):
        ConsolidationDecision(
            operation="merge",
            source_memory_ids=["one", "two"],
            canonical_source_memory_id="three",
            explanation="invalid",
        )
    with pytest.raises(ValueError, match="must not select a canonical"):
        ConsolidationDecision(
            operation="conflict",
            source_memory_ids=["one", "two"],
            canonical_source_memory_id="two",
            explanation="conflicts have no winner",
        )
    with pytest.raises(ValueError, match="Extra inputs are not permitted"):
        ConsolidationDecision.model_validate(
            {
                "operation": "merge",
                "source_memory_ids": ["one", "two"],
                "canonical_source_memory_id": "two",
                "explanation": "model cannot write content",
                "content": "hallucinated replacement",
                "scope": OTHER_SCOPE.model_dump(),
            }
        )
