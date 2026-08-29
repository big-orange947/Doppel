"""Personal-memory query planning, temporal guards, and conservative counts."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from doppel_memory.consolidation import (
    ConsolidationRunner,
    DeterministicMemoryConsolidator,
)
from doppel_memory.in_memory_store import InMemoryStore
from doppel_memory.intelligence import StructuredGenerationRequest
from doppel_memory.models import (
    Actor,
    FactAuthority,
    MemoryIsolationError,
    MemoryRecord,
    MemoryScope,
    MemoryState,
    RecallResult,
    WriteStatus,
)
from doppel_memory.query import (
    DeterministicPersonalMemoryQueryPlanner,
    PersonalMemoryCountStatus,
    PersonalMemoryQueryConfig,
    PersonalMemoryQueryDraft,
    PersonalMemoryQueryEngine,
    PersonalMemoryQueryIntent,
    PersonalMemoryQueryPlanningError,
    PersonalMemoryQueryReadLimitError,
    PersonalMemoryQueryRequest,
    ReferencePersonalMemoryQueryPlanner,
)

SCOPE = MemoryScope(user_id="owner", agent_id="personal-agent")
CONVERSATION_SCOPE = MemoryScope(
    user_id="owner",
    agent_id="personal-agent",
    platform="qq",
    chat_type="private",
    chat_id="friend",
)
OTHER_SCOPE = MemoryScope(user_id="other", agent_id="personal-agent")
NOW = datetime(2026, 8, 28, 12, tzinfo=UTC)


def _record(
    memory_id: str,
    content: str,
    *,
    memory_type: str,
    temporal_status: str,
    day: int,
    scope: MemoryScope = SCOPE,
    topic_key: str = "",
    event_key: str = "",
    valid_from: datetime | None = None,
    valid_to: datetime | None = None,
    subject: str = Actor.OWNER,
    subject_id: str = "",
    revision_kind: str = "assertion",
) -> MemoryRecord:
    created_at = datetime(2026, 1, day, tzinfo=UTC)
    return MemoryRecord(
        memory_id=memory_id,
        scope=scope,
        content=content,
        kind="fact",
        actor=Actor.OWNER,
        authority=FactAuthority.HUMAN_SELF,
        state=MemoryState.CANDIDATE,
        tags=["personal-memory", memory_type],
        source_message_id=f"message-{memory_id}",
        extractor="tests.personal-memory",
        created_at=created_at,
        updated_at=created_at,
        metadata={
            "personal_memory_type": memory_type,
            "topic_key": topic_key,
            "event_key": event_key,
            "subject": subject,
            "subject_id": subject_id or scope.user_id,
            "temporal_status": temporal_status,
            "revision_kind": revision_kind,
            "valid_from": valid_from.isoformat() if valid_from else None,
            "valid_to": valid_to.isoformat() if valid_to else None,
            "evidence": [{"evidence_id": f"message-{memory_id}"}],
        },
    )


async def _put(store: InMemoryStore, *records: MemoryRecord) -> None:
    for record in records:
        result = await store.put(record)
        assert result.status is WriteStatus.CREATED


class _DraftPlanner:
    name = "tests.query-planner"
    version = "1"

    def __init__(self, **draft: Any) -> None:
        self.draft = draft
        self.requests: list[PersonalMemoryQueryRequest] = []

    async def plan(
        self, request: PersonalMemoryQueryRequest
    ) -> PersonalMemoryQueryDraft:
        self.requests.append(request)
        return PersonalMemoryQueryDraft.model_validate(self.draft)


async def test_current_residence_excludes_planned_and_historical_records() -> None:
    store = InMemoryStore()
    await _put(
        store,
        _record(
            "home-shanghai",
            "用户现在长期住在上海。",
            memory_type="state",
            temporal_status="current",
            topic_key="residence.primary",
            day=1,
        ),
        _record(
            "trip-beijing",
            "用户计划去北京临时住两个月。",
            memory_type="state",
            temporal_status="planned",
            topic_key="residence.primary",
            day=2,
        ),
        _record(
            "old-home-hangzhou",
            "用户以前住在杭州。",
            memory_type="state",
            temporal_status="historical",
            topic_key="residence.primary",
            day=3,
        ),
    )

    result = await PersonalMemoryQueryEngine(store).query(
        DeterministicPersonalMemoryQueryPlanner(),
        "我现在住在哪里？",
        [SCOPE],
        now=NOW,
    )

    assert result.plan.intent == PersonalMemoryQueryIntent.CURRENT
    assert result.plan.topic_keys == []
    assert [hit.record.memory_id for hit in result.hits] == ["home-shanghai"]
    assert result.ambiguous is False


async def test_current_query_surfaces_open_conflict_without_recalling_marker_as_fact() -> (
    None
):
    store = InMemoryStore()
    await _put(
        store,
        _record(
            "home-shanghai-conflict",
            "用户现在住在上海。",
            memory_type="state",
            temporal_status="current",
            topic_key="residence.primary",
            day=1,
        ),
        _record(
            "home-hangzhou-conflict",
            "用户现在住在杭州。",
            memory_type="state",
            temporal_status="current",
            topic_key="residence.primary",
            day=2,
        ),
    )
    consolidation = await ConsolidationRunner(store).run_once(
        DeterministicMemoryConsolidator(), SCOPE, run_id="query-open-conflict"
    )
    assert not consolidation.errors

    result = await PersonalMemoryQueryEngine(store).query(
        DeterministicPersonalMemoryQueryPlanner(),
        "我现在住在哪里？",
        [SCOPE],
        now=NOW,
    )

    assert result.ambiguous is True
    assert result.scanned_conflict_count == 1
    assert {hit.record.memory_id for hit in result.hits} == {
        "home-shanghai-conflict",
        "home-hangzhou-conflict",
    }
    assert all(hit.record.kind != "memory_conflict" for hit in result.hits)
    assert len(result.conflicts) == 1
    conflict = result.conflicts[0]
    assert conflict.record.kind == "memory_conflict"
    assert set(conflict.source_memory_ids) == {
        "home-shanghai-conflict",
        "home-hangzhou-conflict",
    }
    assert set(conflict.matched_source_memory_ids) == set(conflict.source_memory_ids)


async def test_later_explicit_correction_makes_old_conflict_marker_query_inert() -> (
    None
):
    store = InMemoryStore()
    await _put(
        store,
        _record(
            "inert-home-shanghai",
            "用户现在住在上海。",
            memory_type="state",
            temporal_status="current",
            topic_key="residence.primary",
            day=1,
        ),
        _record(
            "inert-home-hangzhou",
            "用户现在住在杭州。",
            memory_type="state",
            temporal_status="current",
            topic_key="residence.primary",
            day=2,
        ),
    )
    runner = ConsolidationRunner(store)
    first = await runner.run_once(
        DeterministicMemoryConsolidator(), SCOPE, run_id="create-old-conflict"
    )
    assert first.actions[0].operation == "conflict"
    await _put(
        store,
        _record(
            "inert-home-suzhou",
            "用户明确更正：现在住在苏州。",
            memory_type="state",
            temporal_status="current",
            topic_key="residence.primary",
            revision_kind="correction",
            day=3,
        ),
    )
    corrected = await runner.run_once(
        DeterministicMemoryConsolidator(), SCOPE, run_id="resolve-old-conflict"
    )
    assert corrected.actions[0].operation == "correct"

    result = await PersonalMemoryQueryEngine(store).query(
        DeterministicPersonalMemoryQueryPlanner(),
        "我现在住在哪里？",
        [SCOPE],
        now=NOW,
    )

    assert [hit.record.content for hit in result.hits] == [
        "用户明确更正：现在住在苏州。"
    ]
    assert result.scanned_conflict_count == 1
    assert result.conflicts == []
    assert result.ambiguous is False


async def test_current_query_excludes_ended_validity_before_governance_runs() -> None:
    store = InMemoryStore()
    await _put(
        store,
        _record(
            "ended-beijing-trip",
            "用户临时在北京住两个月。",
            memory_type="state",
            temporal_status="current",
            topic_key="residence.primary",
            day=1,
            valid_from=datetime(2026, 3, 1, tzinfo=UTC),
            valid_to=datetime(2026, 5, 1, tzinfo=UTC),
        ),
        _record(
            "home-shanghai",
            "用户长期住在上海。",
            memory_type="state",
            temporal_status="current",
            topic_key="residence.primary",
            day=2,
            valid_from=datetime(2025, 1, 1, tzinfo=UTC),
        ),
    )

    result = await PersonalMemoryQueryEngine(store).query(
        DeterministicPersonalMemoryQueryPlanner(),
        "我现在住在哪里？",
        [SCOPE],
        now=NOW,
    )

    assert [hit.record.memory_id for hit in result.hits] == ["home-shanghai"]
    assert "valid_at_now" in result.hits[0].reasons


async def test_planned_residence_does_not_claim_the_plan_already_happened() -> None:
    store = InMemoryStore()
    await _put(
        store,
        _record(
            "home-shanghai",
            "用户现在长期住在上海。",
            memory_type="state",
            temporal_status="current",
            topic_key="residence.primary",
            day=1,
        ),
        _record(
            "planned-beijing",
            "用户计划去北京临时住两个月。",
            memory_type="state",
            temporal_status="planned",
            topic_key="residence.primary",
            day=2,
        ),
    )

    result = await PersonalMemoryQueryEngine(store).query(
        DeterministicPersonalMemoryQueryPlanner(),
        "我计划住在哪里？",
        [SCOPE],
        now=NOW,
    )

    assert result.plan.intent == PersonalMemoryQueryIntent.PLANNED
    assert [hit.record.memory_id for hit in result.hits] == ["planned-beijing"]


async def test_as_of_query_uses_explicit_validity_intervals() -> None:
    store = InMemoryStore()
    await _put(
        store,
        _record(
            "home-beijing-2024",
            "用户当时住在北京。",
            memory_type="state",
            temporal_status="historical",
            topic_key="residence.primary",
            day=1,
            valid_from=datetime(2024, 1, 1, tzinfo=UTC),
            valid_to=datetime(2024, 12, 31, 23, 59, tzinfo=UTC),
        ),
        _record(
            "home-shanghai-2025",
            "用户后来住在上海。",
            memory_type="state",
            temporal_status="current",
            topic_key="residence.primary",
            day=2,
            valid_from=datetime(2025, 1, 1, tzinfo=UTC),
        ),
    )

    result = await PersonalMemoryQueryEngine(store).query(
        DeterministicPersonalMemoryQueryPlanner(),
        "我在2024年06月01日住在哪里？",
        [SCOPE],
        now=NOW,
    )

    assert result.plan.intent == PersonalMemoryQueryIntent.AS_OF
    assert result.plan.as_of == datetime(2024, 6, 1, 12, tzinfo=UTC)
    assert [hit.record.memory_id for hit in result.hits] == ["home-beijing-2024"]


async def test_as_of_query_does_not_treat_an_unfulfilled_plan_as_actual() -> None:
    store = InMemoryStore()
    await _put(
        store,
        _record(
            "home-shanghai",
            "用户现在长期住在上海。",
            memory_type="state",
            temporal_status="current",
            topic_key="residence.primary",
            day=1,
            valid_from=datetime(2025, 1, 1, tzinfo=UTC),
        ),
        _record(
            "planned-beijing",
            "用户计划去北京临时住两个月。",
            memory_type="state",
            temporal_status="planned",
            topic_key="residence.primary",
            day=2,
            valid_from=datetime(2026, 9, 1, tzinfo=UTC),
            valid_to=datetime(2026, 10, 31, tzinfo=UTC),
        ),
    )

    result = await PersonalMemoryQueryEngine(store).query(
        DeterministicPersonalMemoryQueryPlanner(),
        "我在2026年09月15日住在哪里？",
        [SCOPE],
        now=NOW,
    )

    assert [hit.record.memory_id for hit in result.hits] == ["home-shanghai"]
    assert result.warnings == [
        "future as_of returns present evidence only; future actual state is unknown"
    ]


async def test_episode_count_deduplicates_only_explicit_stable_event_keys() -> None:
    store = InMemoryStore()
    await _put(
        store,
        _record(
            "trip-beijing-first-mention",
            "用户去年去北京旅行。",
            memory_type="episode",
            temporal_status="historical",
            event_key="trip:2025-05:beijing",
            day=1,
        ),
        _record(
            "trip-beijing-second-mention",
            "用户后来又提到去年北京之旅。",
            memory_type="episode",
            temporal_status="historical",
            event_key="trip:2025-05:beijing",
            day=2,
        ),
        _record(
            "trip-chengdu",
            "用户今年去成都旅行。",
            memory_type="episode",
            temporal_status="historical",
            event_key="trip:2026-03:chengdu",
            day=3,
        ),
    )

    result = await PersonalMemoryQueryEngine(store).query(
        DeterministicPersonalMemoryQueryPlanner(),
        "我一共旅行了几次？",
        [SCOPE],
        now=NOW,
    )

    assert result.matched_record_count == 3
    assert result.count.status == PersonalMemoryCountStatus.EXACT
    assert result.count.value == 2
    assert result.count.distinct_event_keys == [
        "trip:2025-05:beijing",
        "trip:2026-03:chengdu",
    ]


async def test_episode_count_abstains_when_any_event_identity_is_missing() -> None:
    store = InMemoryStore()
    await _put(
        store,
        _record(
            "known-trip",
            "用户去过北京旅行。",
            memory_type="episode",
            temporal_status="historical",
            event_key="trip:2025-05:beijing",
            day=1,
        ),
        _record(
            "unknown-trip",
            "用户还提到一次旅行。",
            memory_type="episode",
            temporal_status="historical",
            day=2,
        ),
    )

    result = await PersonalMemoryQueryEngine(store).query(
        DeterministicPersonalMemoryQueryPlanner(),
        "我一共旅行了几次？",
        [SCOPE],
        now=NOW,
    )

    assert result.count.status == PersonalMemoryCountStatus.INDETERMINATE
    assert result.count.value is None
    assert "event_key" in result.count.reason
    assert result.warnings == [result.count.reason]


async def test_business_trip_count_is_structurally_limited_to_episodes() -> None:
    planner = DeterministicPersonalMemoryQueryPlanner()

    draft = await planner.plan(
        PersonalMemoryQueryRequest(
            query="我一共出差了几次？",
            now=NOW,
            default_subject_id="owner",
        )
    )

    assert draft.intent == PersonalMemoryQueryIntent.COUNT
    assert draft.memory_types == ["episode"]


async def test_pet_name_question_reduces_to_retrievable_entity_text() -> None:
    draft = await DeterministicPersonalMemoryQueryPlanner().plan(
        PersonalMemoryQueryRequest(
            query="我的猫叫什么？",
            now=NOW,
            default_subject_id="owner",
        )
    )

    assert draft.search_text == "猫"


@pytest.mark.parametrize(
    "query",
    [
        "我不吃什么东西？",
        "我有什么忌口？",
        "我在哪里工作？",
        "我下周要去哪开会？",
        "我最喜欢什么颜色？",
        "我的猫叫什么？",
    ],
)
async def test_domain_questions_do_not_create_hard_coded_topic_filters(
    query: str,
) -> None:
    draft = await DeterministicPersonalMemoryQueryPlanner().plan(
        PersonalMemoryQueryRequest(
            query=query,
            now=NOW,
            default_subject_id="owner",
        )
    )

    assert draft.search_text
    assert draft.memory_types == []
    assert draft.topic_keys == []


async def test_current_conflicts_are_returned_as_ambiguous_evidence() -> None:
    store = InMemoryStore()
    await _put(
        store,
        _record(
            "blue",
            "用户现在最喜欢蓝色。",
            memory_type="preference",
            temporal_status="current",
            topic_key="preference.favorite-color",
            day=1,
        ),
        _record(
            "green",
            "用户现在最喜欢绿色。",
            memory_type="preference",
            temporal_status="current",
            topic_key="preference.favorite-color",
            day=2,
        ),
    )

    result = await PersonalMemoryQueryEngine(store).query(
        DeterministicPersonalMemoryQueryPlanner(),
        "我现在最喜欢什么颜色？",
        [SCOPE],
        now=NOW,
    )

    assert result.ambiguous is True
    assert len(result.hits) == 2
    assert "preference.favorite-color" in result.warnings[0]


async def test_multi_scope_query_stays_within_one_user_and_deduplicates_scopes() -> (
    None
):
    store = InMemoryStore()
    await _put(
        store,
        _record(
            "global-home",
            "用户现在住在上海。",
            memory_type="state",
            temporal_status="current",
            topic_key="residence.primary",
            day=1,
        ),
        _record(
            "conversation-home",
            "用户在这个会话里确认住在上海。",
            memory_type="state",
            temporal_status="current",
            topic_key="residence.primary",
            day=2,
            scope=CONVERSATION_SCOPE,
        ),
        _record(
            "other-user-home",
            "其他用户住在北京。",
            memory_type="state",
            temporal_status="current",
            topic_key="residence.primary",
            day=3,
            scope=OTHER_SCOPE,
        ),
    )
    engine = PersonalMemoryQueryEngine(store)

    result = await engine.query(
        DeterministicPersonalMemoryQueryPlanner(),
        "我现在住在哪里？",
        [SCOPE, CONVERSATION_SCOPE, SCOPE],
        now=NOW,
    )

    assert {hit.record.memory_id for hit in result.hits} == {
        "global-home",
        "conversation-home",
    }
    assert result.scanned_record_count == 2
    with pytest.raises(MemoryIsolationError, match="cross user_id"):
        await engine.query(
            DeterministicPersonalMemoryQueryPlanner(),
            "我现在住在哪里？",
            [SCOPE, OTHER_SCOPE],
            now=NOW,
        )


async def test_planner_subject_and_plan_integrity_are_trusted_boundaries() -> None:
    store = InMemoryStore()
    engine = PersonalMemoryQueryEngine(store)
    unsafe_subject = _DraftPlanner(
        intent="lookup",
        subject=Actor.CONTACT,
        subject_id="friend-1",
    )
    with pytest.raises(PersonalMemoryQueryPlanningError, match="authorization"):
        await engine.plan(unsafe_subject, "朋友喜欢什么？", [SCOPE], now=NOW)

    plan = await engine.plan(
        DeterministicPersonalMemoryQueryPlanner(),
        "我现在住在哪里？",
        [SCOPE],
        now=NOW,
    )
    tampered = plan.model_copy(update={"topic_keys": ["work.current-employer"]})
    with pytest.raises(PersonalMemoryQueryPlanningError, match="plan_id"):
        await engine.execute(tampered)


async def test_full_scope_bound_fails_instead_of_returning_partial_count() -> None:
    store = InMemoryStore()
    await _put(
        store,
        _record(
            "trip-1",
            "用户去北京旅行。",
            memory_type="episode",
            temporal_status="historical",
            event_key="trip:1",
            day=1,
        ),
        _record(
            "trip-2",
            "用户去上海旅行。",
            memory_type="episode",
            temporal_status="historical",
            event_key="trip:2",
            day=2,
        ),
    )

    with pytest.raises(PersonalMemoryQueryReadLimitError, match="max_records"):
        await PersonalMemoryQueryEngine(
            store,
            PersonalMemoryQueryConfig(page_size=1, max_records_per_scope=1),
        ).query(
            DeterministicPersonalMemoryQueryPlanner(),
            "我一共旅行了几次？",
            [SCOPE],
            now=NOW,
        )


class _StubStructuredModel:
    name = "tests.query-model"
    version = "1"

    def __init__(self, result: dict[str, Any]) -> None:
        self.result = result
        self.requests: list[StructuredGenerationRequest] = []

    async def generate(self, request: StructuredGenerationRequest):
        self.requests.append(request)
        return self.result


class _SemanticIndex:
    async def search(self, query, scopes, *, filters=None, limit=10):
        del query, filters, limit
        return [
            RecallResult(
                fact="semantic match",
                memory_id="semantic-chengdu",
                scope=scopes[0],
                similarity=0.91,
            ),
            RecallResult(
                fact="malicious cross-user candidate",
                memory_id="other-memory",
                scope=OTHER_SCOPE,
                similarity=1.0,
            ),
        ]


class _LowSemanticIndex:
    async def search(self, query, scopes, *, filters=None, limit=10):
        del query, filters, limit
        return [
            RecallResult(
                fact="weak unrelated candidate",
                memory_id="weak-candidate",
                scope=scopes[0],
                similarity=0.2,
            )
        ]


class _CountingSemanticIndex:
    def __init__(self) -> None:
        self.calls = 0

    async def search(self, query, scopes, *, filters=None, limit=10):
        del query, scopes, filters, limit
        self.calls += 1
        return []


async def test_exact_count_never_depends_on_bounded_semantic_top_k() -> None:
    store = InMemoryStore()
    await _put(
        store,
        _record(
            "counted-event",
            "用户参加了一次公开活动。",
            memory_type="episode",
            temporal_status="historical",
            event_key="event:2026-01:public",
            day=1,
        ),
    )
    semantic_index = _CountingSemanticIndex()

    result = await PersonalMemoryQueryEngine(
        store, semantic_index=semantic_index
    ).query(
        DeterministicPersonalMemoryQueryPlanner(),
        "我参加公开活动几次？",
        [SCOPE],
        now=NOW,
    )

    assert semantic_index.calls == 0
    assert result.complete is True
    assert result.count.status == PersonalMemoryCountStatus.EXACT
    assert result.count.value == 1


async def test_low_semantic_similarity_does_not_turn_every_candidate_into_a_hit() -> (
    None
):
    store = InMemoryStore()
    await _put(
        store,
        _record(
            "weak-candidate",
            "用户喜欢听古典音乐。",
            memory_type="preference",
            temporal_status="current",
            day=1,
        ),
    )

    result = await PersonalMemoryQueryEngine(
        store, semantic_index=_LowSemanticIndex()
    ).query(
        DeterministicPersonalMemoryQueryPlanner(),
        "我住在哪个城市？",
        [SCOPE],
        now=NOW,
    )

    assert result.hits == []
    assert result.complete is False


async def test_semantic_candidates_only_score_known_authorized_records() -> None:
    store = InMemoryStore()
    await _put(
        store,
        _record(
            "semantic-chengdu",
            "用户去成都旅行。",
            memory_type="episode",
            temporal_status="historical",
            event_key="trip:chengdu",
            day=1,
        ),
        _record(
            "other-memory",
            "其他用户的越权记忆。",
            memory_type="episode",
            temporal_status="historical",
            event_key="trip:other",
            day=2,
            scope=OTHER_SCOPE,
        ),
        _record(
            "same-scope-distractor",
            "用户喜欢听古典音乐。",
            memory_type="preference",
            temporal_status="current",
            day=3,
        ),
    )

    result = await PersonalMemoryQueryEngine(
        store,
        PersonalMemoryQueryConfig(page_size=1, max_records_per_scope=1),
        semantic_index=_SemanticIndex(),
    ).query(
        DeterministicPersonalMemoryQueryPlanner(),
        "蓉城之旅",
        [SCOPE],
        now=NOW,
    )

    assert [hit.record.memory_id for hit in result.hits] == ["semantic-chengdu"]
    assert result.hits[0].semantic_score == 0.91
    assert "semantic_match" in result.hits[0].reasons
    assert result.scanned_record_count == 1
    assert result.complete is False


async def test_reference_planner_gets_schema_but_cannot_choose_read_scopes() -> None:
    model = _StubStructuredModel(
        {
            "intent": "current",
            "memory_types": ["state"],
            "topic_keys": ["residence.primary"],
            "temporal_statuses": ["current"],
            "subject": "owner",
            "explanation": "current primary residence",
        }
    )
    planner = ReferencePersonalMemoryQueryPlanner(model)

    draft = await planner.plan(
        PersonalMemoryQueryRequest(
            query="我现在住在哪里？",
            now=NOW,
            default_subject_id="owner",
        )
    )

    assert draft.intent == PersonalMemoryQueryIntent.CURRENT
    request = model.requests[0]
    assert "never choose read scopes" in request.instructions
    assert request.output_schema["title"] == "PersonalMemoryQueryDraft"
    assert "scopes" not in request.output_schema["properties"]
