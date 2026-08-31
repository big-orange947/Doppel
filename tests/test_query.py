"""Personal-memory query planning, temporal guards, and conservative counts."""

from __future__ import annotations

import asyncio
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
from doppel_memory.relation import (
    RelationCandidate,
    RelationIndexUnavailableError,
)
from doppel_memory.vector import CompositeSemanticIndex

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
    actor: str = Actor.OWNER,
    authority: FactAuthority = FactAuthority.HUMAN_SELF,
    state: MemoryState = MemoryState.CANDIDATE,
) -> MemoryRecord:
    created_at = datetime(2026, 1, day, tzinfo=UTC)
    return MemoryRecord(
        memory_id=memory_id,
        scope=scope,
        content=content,
        kind="fact",
        actor=actor,
        authority=authority,
        state=state,
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


class _FilterIgnoringStore(InMemoryStore):
    async def scan(self, scope, *, filters=None, cursor="", limit=100):
        del filters
        return await super().scan(scope, filters=None, cursor=cursor, limit=limit)


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
            state=MemoryState.CONFIRMED,
        ),
        _record(
            "home-shanghai-2025",
            "用户后来住在上海。",
            memory_type="state",
            temporal_status="current",
            topic_key="residence.primary",
            day=2,
            valid_from=datetime(2025, 1, 1, tzinfo=UTC),
            state=MemoryState.CONFIRMED,
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


async def test_history_query_can_read_superseded_record_with_explicit_interval() -> None:
    store = InMemoryStore()
    await _put(
        store,
        _record(
            "old-role",
            "用户过去担任设计总监。",
            memory_type="state",
            temporal_status="historical",
            topic_key="employment.primary",
            day=1,
            valid_from=datetime(2024, 1, 1, tzinfo=UTC),
            valid_to=datetime(2025, 12, 31, tzinfo=UTC),
            state=MemoryState.SUPERSEDED,
        ),
        _record(
            "current-role",
            "用户目前担任产品经理。",
            memory_type="state",
            temporal_status="current",
            topic_key="employment.primary",
            day=2,
            valid_from=datetime(2026, 1, 1, tzinfo=UTC),
            state=MemoryState.CONFIRMED,
        ),
    )

    result = await PersonalMemoryQueryEngine(store).query(
        _DraftPlanner(
            intent="history",
            search_text="",
            temporal_statuses=["historical"],
            subject="owner",
        ),
        "我过去做什么工作？",
        [SCOPE],
        now=NOW,
    )

    assert [hit.record.memory_id for hit in result.hits] == ["old-role"]


async def test_intent_supplies_missing_domain_neutral_temporal_filter() -> None:
    store = InMemoryStore()
    await _put(
        store,
        _record(
            "past-trip",
            "用户去年去过香港。",
            memory_type="episode",
            temporal_status="historical",
            day=1,
            state=MemoryState.CONFIRMED,
        ),
        _record(
            "future-trip",
            "用户计划下个月去香港。",
            memory_type="plan",
            temporal_status="planned",
            day=2,
            state=MemoryState.CONFIRMED,
        ),
        _record(
            "current-home",
            "用户目前住在上海。",
            memory_type="state",
            temporal_status="current",
            day=3,
            state=MemoryState.CONFIRMED,
        ),
    )
    engine = PersonalMemoryQueryEngine(store)

    history = await engine.query(
        _DraftPlanner(intent="history", search_text="", subject="owner"),
        "我以前去过哪里？",
        [SCOPE],
        now=NOW,
    )
    planned = await engine.query(
        _DraftPlanner(intent="planned", search_text="", subject="owner"),
        "我接下来有什么计划？",
        [SCOPE],
        now=NOW,
    )
    current = await engine.query(
        _DraftPlanner(intent="current", search_text="", subject="owner"),
        "我现在住在哪里？",
        [SCOPE],
        now=NOW,
    )

    assert history.plan.temporal_statuses == ["historical"]
    assert [hit.record.memory_id for hit in history.hits] == ["past-trip"]
    assert planned.plan.temporal_statuses == ["planned"]
    assert [hit.record.memory_id for hit in planned.hits] == ["future-trip"]
    assert current.plan.temporal_statuses == ["current", "timeless"]
    assert [hit.record.memory_id for hit in current.hits] == ["current-home"]


async def test_as_of_query_can_read_superseded_record_only_inside_interval() -> None:
    store = InMemoryStore()
    await _put(
        store,
        _record(
            "old-role",
            "用户当时担任设计总监。",
            memory_type="state",
            temporal_status="historical",
            day=1,
            valid_from=datetime(2024, 1, 1, tzinfo=UTC),
            valid_to=datetime(2025, 12, 31, tzinfo=UTC),
            state=MemoryState.SUPERSEDED,
        ),
    )

    inside = await PersonalMemoryQueryEngine(store).query(
        _DraftPlanner(
            intent="as_of",
            search_text="",
            as_of=datetime(2025, 6, 1, tzinfo=UTC),
            subject="owner",
        ),
        "2025 年 6 月 1 日是什么岗位？",
        [SCOPE],
        now=NOW,
    )
    outside = await PersonalMemoryQueryEngine(store).query(
        _DraftPlanner(
            intent="as_of",
            search_text="",
            as_of=datetime(2026, 6, 1, tzinfo=UTC),
            subject="owner",
        ),
        "2026 年 6 月 1 日是什么岗位？",
        [SCOPE],
        now=NOW,
    )

    assert [hit.record.memory_id for hit in inside.hits] == ["old-role"]
    assert outside.hits == []


async def test_historical_expired_record_requires_interval_and_rejected_is_never_visible() -> None:
    store = InMemoryStore()
    await _put(
        store,
        _record(
            "archived-trip",
            "用户曾临时住在北京。",
            memory_type="state",
            temporal_status="historical",
            day=1,
            valid_from=datetime(2025, 3, 1, tzinfo=UTC),
            valid_to=datetime(2025, 5, 1, tzinfo=UTC),
            state=MemoryState.EXPIRED,
        ),
        _record(
            "interval-free-archive",
            "用户可能曾住在别处。",
            memory_type="state",
            temporal_status="historical",
            day=2,
            state=MemoryState.EXPIRED,
        ),
        _record(
            "rejected-history",
            "已经否定的历史说法。",
            memory_type="state",
            temporal_status="historical",
            day=3,
            valid_from=datetime(2025, 3, 1, tzinfo=UTC),
            valid_to=datetime(2025, 5, 1, tzinfo=UTC),
            state=MemoryState.REJECTED,
        ),
    )

    history = await PersonalMemoryQueryEngine(store).query(
        _DraftPlanner(
            intent="history",
            search_text="",
            temporal_statuses=["historical"],
            subject="owner",
        ),
        "我以前住过哪里？",
        [SCOPE],
        now=NOW,
    )
    current = await PersonalMemoryQueryEngine(store).query(
        _DraftPlanner(
            intent="current",
            search_text="",
            temporal_statuses=["current", "timeless"],
            subject="owner",
        ),
        "我现在住哪里？",
        [SCOPE],
        now=NOW,
    )

    assert [hit.record.memory_id for hit in history.hits] == ["archived-trip"]
    assert current.hits == []


async def test_human_candidates_remain_visible_but_agent_output_cannot_be_owner_fact() -> None:
    store = InMemoryStore()
    await _put(
        store,
        _record(
            "human-candidate",
            "用户现在偏好安静的环境。",
            memory_type="preference",
            temporal_status="current",
            day=1,
        ),
        _record(
            "derived-candidate",
            "有证据摘要显示用户当前偏好短回复。",
            memory_type="preference",
            temporal_status="current",
            day=2,
            authority=FactAuthority.DERIVED_SUMMARY,
        ),
        _record(
            "agent-candidate",
            "Agent 猜测用户可能喜欢养狗。",
            memory_type="fact",
            temporal_status="current",
            day=3,
            actor=Actor.AGENT,
            authority=FactAuthority.AGENT_OUTPUT,
        ),
        _record(
            "agent-confirmed",
            "Agent 声称用户会搬家。",
            memory_type="fact",
            temporal_status="current",
            day=4,
            actor=Actor.AGENT,
            authority=FactAuthority.AGENT_OUTPUT,
            state=MemoryState.CONFIRMED,
        ),
    )

    result = await PersonalMemoryQueryEngine(store).query(
        _DraftPlanner(
            intent="current",
            search_text="",
            temporal_statuses=["current", "timeless"],
            subject="owner",
        ),
        "关于我有什么当前记忆？",
        [SCOPE],
        now=NOW,
    )

    assert {hit.record.memory_id for hit in result.hits} == {
        "human-candidate",
        "derived-candidate",
    }


async def test_agent_output_is_eligible_only_for_agent_subject_query() -> None:
    store = InMemoryStore()
    await _put(
        store,
        _record(
            "agent-own-output",
            "Agent 当前采用简短回答策略。",
            memory_type="state",
            temporal_status="current",
            day=1,
            subject=Actor.AGENT,
            subject_id=SCOPE.agent_id,
            actor=Actor.AGENT,
            authority=FactAuthority.AGENT_OUTPUT,
            state=MemoryState.CONFIRMED,
        ),
    )

    result = await PersonalMemoryQueryEngine(store).query(
        _DraftPlanner(
            intent="current",
            search_text="",
            temporal_statuses=["current"],
            subject="agent",
        ),
        "Agent 当前采用什么回答策略？",
        [SCOPE],
        now=NOW,
        default_subject=Actor.AGENT,
        default_subject_id=SCOPE.agent_id,
    )

    assert [hit.record.memory_id for hit in result.hits] == ["agent-own-output"]


async def test_final_gate_rejects_agent_output_when_store_ignores_filters() -> None:
    store = _FilterIgnoringStore()
    await _put(
        store,
        _record(
            "ignored-filter-agent-output",
            "Agent 声称用户当前住在错误地点。",
            memory_type="state",
            temporal_status="current",
            day=1,
            actor=Actor.AGENT,
            authority=FactAuthority.AGENT_OUTPUT,
            state=MemoryState.CONFIRMED,
        ),
    )

    result = await PersonalMemoryQueryEngine(store).query(
        _DraftPlanner(
            intent="current",
            search_text="",
            temporal_statuses=["current"],
            subject="owner",
        ),
        "我现在住在哪里？",
        [SCOPE],
        now=NOW,
    )

    assert result.scanned_record_count == 1
    assert result.hits == []


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
            state=MemoryState.CONFIRMED,
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
            state=MemoryState.CONFIRMED,
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
        "我在2024年6月15日住在哪里？",
        "我在 2024 年 6 月 15 日住在哪里？",
        "我在2024-06-15住在哪里？",
        "我在2024/06/15住在哪里？",
    ],
)
async def test_deterministic_planner_parses_explicit_complete_dates(
    query: str,
) -> None:
    draft = await DeterministicPersonalMemoryQueryPlanner().plan(
        PersonalMemoryQueryRequest(
            query=query,
            now=NOW,
            default_subject_id="owner",
        )
    )

    assert draft.intent == PersonalMemoryQueryIntent.AS_OF
    assert draft.as_of == datetime(2024, 6, 15, 12, tzinfo=UTC)


@pytest.mark.parametrize(
    "query",
    [
        "2024 年 6 月我住在哪里？",
        "2024 年 2 月 30 日我住在哪里？",
    ],
)
async def test_deterministic_planner_does_not_guess_incomplete_or_invalid_dates(
    query: str,
) -> None:
    draft = await DeterministicPersonalMemoryQueryPlanner().plan(
        PersonalMemoryQueryRequest(
            query=query,
            now=NOW,
            default_subject_id="owner",
        )
    )

    assert draft.intent != PersonalMemoryQueryIntent.AS_OF
    assert draft.as_of is None


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


class _AgentOutputSemanticIndex:
    """Ignores filters to exercise the engine's final authority gate."""

    async def search(self, query, scopes, *, filters=None, limit=10):
        del query, filters, limit
        return [
            RecallResult(
                fact="malicious Agent-authored owner candidate",
                memory_id="semantic-agent-output",
                scope=scopes[0],
                similarity=1.0,
            )
        ]


class _TemporalSemanticIndex:
    def __init__(self) -> None:
        self.search_calls = 0
        self.search_at_calls: list[datetime] = []

    async def search(self, query, scopes, *, filters=None, limit=10):
        del query, scopes, filters, limit
        self.search_calls += 1
        return []

    async def search_at(
        self, query, scopes, *, valid_at, filters=None, limit=10
    ):
        del query, filters, limit
        self.search_at_calls.append(valid_at)
        return [
            RecallResult(
                fact="temporal graph candidate",
                memory_id="temporal-candidate",
                scope=scopes[0],
                similarity=0.9,
            )
        ]


class _RelationIndex:
    def __init__(self, candidates: list[RelationCandidate]) -> None:
        self.candidates = candidates
        self.calls: list[tuple[Any, list[MemoryScope], Any, int]] = []

    async def search_relations(
        self, request, scopes, *, filters=None, limit=10
    ):
        self.calls.append((request, list(scopes), filters, limit))
        return self.candidates


class _FailingRelationIndex:
    async def search_relations(
        self, request, scopes, *, filters=None, limit=10
    ):
        del request, scopes, filters, limit
        raise RelationIndexUnavailableError("synthetic relation outage")


async def test_semantic_and_relation_sources_execute_concurrently() -> None:
    semantic_started = asyncio.Event()
    relation_started = asyncio.Event()

    class _CoordinatedSemanticIndex:
        async def search(self, query, scopes, *, filters=None, limit=10):
            del query, scopes, filters, limit
            semantic_started.set()
            await relation_started.wait()
            return []

    class _CoordinatedRelationIndex:
        async def search_relations(
            self, request, scopes, *, filters=None, limit=10
        ):
            del request, scopes, filters, limit
            relation_started.set()
            await semantic_started.wait()
            return []

    engine = PersonalMemoryQueryEngine(
        InMemoryStore(),
        semantic_index=_CoordinatedSemanticIndex(),
        relation_index=_CoordinatedRelationIndex(),
    )
    result = await asyncio.wait_for(
        engine.query(
            _DraftPlanner(
                intent="lookup",
                search_text="相机在哪里",
                entity_mentions=["相机"],
                relation_hints=["位于"],
            ),
            "相机在哪里？",
            [SCOPE],
            now=NOW,
        ),
        timeout=1.0,
    )

    assert semantic_started.is_set()
    assert relation_started.is_set()
    assert result.hits == []


async def test_relation_candidates_are_separate_rank_features_and_store_reloaded() -> (
    None
):
    store = InMemoryStore()
    await _put(
        store,
        _record(
            "camera-holder",
            "该物品目前由联系人保管。",
            memory_type="state",
            temporal_status="current",
            topic_key="possession",
            day=1,
            state=MemoryState.CONFIRMED,
        ),
    )
    relation_index = _RelationIndex(
        [
            RelationCandidate(
                scope=SCOPE,
                memory_id="camera-holder",
                source="graphiti_relation",
                score=0.92,
                relation_type="HELD_BY",
                source_entity_id="entity-camera",
                source_entity_name="相机",
                target_entity_id="entity-contact",
                target_entity_name="联系人",
                edge_id="edge-held-by",
                episode_ids=["episode-camera"],
                valid_at=datetime(2026, 8, 1, tzinfo=UTC),
            )
        ]
    )
    engine = PersonalMemoryQueryEngine(
        store,
        PersonalMemoryQueryConfig(minimum_lexical_score=0.99),
        relation_index=relation_index,
    )

    result = await engine.query(
        _DraftPlanner(
            intent="lookup",
            search_text="那件东西现在在哪里",
            entity_mentions=["相机"],
            relation_hints=["持有"],
            subject="owner",
        ),
        "那件东西现在在哪里？",
        [SCOPE],
        now=NOW,
    )

    assert len(relation_index.calls) == 1
    request, scopes, filters, limit = relation_index.calls[0]
    assert request.entity_mentions == ["相机"]
    assert request.relation_hints == ["持有"]
    assert request.valid_at == NOW
    assert scopes == [SCOPE]
    assert filters.exclude_authorities == {FactAuthority.AGENT_OUTPUT}
    assert limit == engine.config.relation_candidate_limit
    assert [hit.record.memory_id for hit in result.hits] == ["camera-holder"]
    assert result.hits[0].relation_score == 0.92
    assert result.hits[0].semantic_score == 0.0
    assert "relation_source:graphiti_relation" in result.hits[0].reasons
    assert "relation_type:HELD_BY" in result.hits[0].reasons


async def test_explicit_relation_constraints_gate_semantic_and_lexical_hits() -> None:
    store = InMemoryStore()
    for record in (
        _record(
            "camera-location",
            "相机目前放在工作室。",
            memory_type="state",
            temporal_status="current",
            day=1,
            state=MemoryState.CONFIRMED,
        ),
        _record(
            "camera-purchase",
            "相机是去年购买的。",
            memory_type="episode",
            temporal_status="historical",
            day=1,
            state=MemoryState.CONFIRMED,
        ),
    ):
        await _put(store, record)

    class _BothSemanticCandidates:
        async def search(self, query, scopes, *, filters=None, limit=10):
            del query, filters, limit
            return [
                RecallResult(
                    fact="semantic location",
                    memory_id="camera-location",
                    scope=scopes[0],
                    similarity=0.9,
                ),
                RecallResult(
                    fact="semantic purchase",
                    memory_id="camera-purchase",
                    scope=scopes[0],
                    similarity=0.99,
                ),
            ]

    relation_index = _RelationIndex(
        [
            RelationCandidate(
                scope=SCOPE,
                memory_id="camera-location",
                source="graphiti_relation",
                score=0.95,
                relation_type="LOCATED_AT",
                edge_id="edge-location",
                episode_ids=["episode-location"],
            ),
            RelationCandidate(
                scope=SCOPE,
                memory_id="camera-purchase",
                source="graphiti_relation",
                score=0.2,
                relation_type="PURCHASED_AT",
                edge_id="edge-purchase",
                episode_ids=["episode-purchase"],
            ),
        ]
    )
    result = await PersonalMemoryQueryEngine(
        store,
        semantic_index=_BothSemanticCandidates(),
        relation_index=relation_index,
    ).query(
        _DraftPlanner(
            intent="lookup",
            search_text="相机",
            entity_mentions=["相机"],
            relation_hints=["位于"],
        ),
        "相机现在位于哪里？",
        [SCOPE],
        now=NOW,
    )

    assert [hit.record.memory_id for hit in result.hits] == ["camera-location"]
    assert result.hits[0].semantic_score == 0.9
    assert result.hits[0].relation_score == 0.95
    assert not result.complete


async def test_explicit_relation_constraints_abstain_on_relation_mismatch() -> None:
    store = InMemoryStore()
    await _put(
        store,
        _record(
            "camera-location",
            "相机目前放在工作室。",
            memory_type="state",
            temporal_status="current",
            day=1,
            state=MemoryState.CONFIRMED,
        ),
    )
    relation_index = _RelationIndex(
        [
            RelationCandidate(
                scope=SCOPE,
                memory_id="camera-location",
                source="graphiti_relation",
                score=0.2,
                relation_type="LOCATED_AT",
                edge_id="edge-location",
                episode_ids=["episode-location"],
            )
        ]
    )

    result = await PersonalMemoryQueryEngine(
        store, relation_index=relation_index
    ).query(
        _DraftPlanner(
            intent="lookup",
            search_text="相机",
            entity_mentions=["相机"],
            relation_hints=["购买"],
        ),
        "谁购买了相机？",
        [SCOPE],
        now=NOW,
    )

    assert result.hits == []
    assert any("no qualified relation evidence" in item for item in result.warnings)


async def test_relation_match_gate_can_be_disabled_for_legacy_augmentation() -> None:
    store = InMemoryStore()
    await _put(
        store,
        _record(
            "camera-location",
            "相机目前放在工作室。",
            memory_type="state",
            temporal_status="current",
            day=1,
            state=MemoryState.CONFIRMED,
        ),
    )
    result = await PersonalMemoryQueryEngine(
        store,
        PersonalMemoryQueryConfig(relation_hints_require_match=False),
        relation_index=_RelationIndex([]),
    ).query(
        _DraftPlanner(
            intent="lookup",
            search_text="相机",
            entity_mentions=["相机"],
            relation_hints=["购买"],
        ),
        "谁购买了相机？",
        [SCOPE],
        now=NOW,
    )

    assert [hit.record.memory_id for hit in result.hits] == ["camera-location"]


async def test_relation_index_requires_explicit_entity_anchor() -> None:
    store = InMemoryStore()
    relation_index = _RelationIndex([])
    result = await PersonalMemoryQueryEngine(
        store, relation_index=relation_index
    ).query(
        _DraftPlanner(intent="lookup", search_text="普通语义问题"),
        "普通语义问题",
        [SCOPE],
        now=NOW,
    )

    assert relation_index.calls == []
    assert result.hits == []


async def test_relation_hint_can_use_the_trusted_subject_as_graph_anchor() -> None:
    store = InMemoryStore()
    await _put(
        store,
        _record(
            "owner-employer",
            "我目前在星海科技任职。",
            memory_type="state",
            temporal_status="current",
            day=1,
            state=MemoryState.CONFIRMED,
        ),
    )
    relation_index = _RelationIndex(
        [
            RelationCandidate(
                scope=SCOPE,
                memory_id="owner-employer",
                source="graphiti_relation",
                score=0.95,
                relation_type="EMPLOYED_BY",
                edge_id="edge-employer",
                episode_ids=["episode-employer"],
            )
        ]
    )

    result = await PersonalMemoryQueryEngine(
        store, relation_index=relation_index
    ).query(
        _DraftPlanner(
            intent="current",
            search_text="任职公司",
            entity_mentions=[],
            relation_hints=["任职"],
        ),
        "我目前在哪家公司任职？",
        [SCOPE],
        now=NOW,
    )

    assert [hit.record.memory_id for hit in result.hits] == ["owner-employer"]
    assert relation_index.calls[0][0].entity_mentions == []
    assert relation_index.calls[0][0].subject_id == SCOPE.user_id


async def test_time_range_matches_state_validity_overlap_not_only_start_time() -> None:
    store = InMemoryStore()
    for record in (
        _record(
            "state-overlapping-june",
            "该状态在六月仍然有效。",
            memory_type="state",
            temporal_status="historical",
            day=1,
            valid_from=datetime(2026, 1, 1, tzinfo=UTC),
            valid_to=datetime(2026, 6, 30, 23, 59, tzinfo=UTC),
            state=MemoryState.CONFIRMED,
        ),
        _record(
            "state-starting-july",
            "该状态从七月开始。",
            memory_type="state",
            temporal_status="historical",
            day=2,
            valid_from=datetime(2026, 7, 1, tzinfo=UTC),
            valid_to=datetime(2026, 7, 31, tzinfo=UTC),
            state=MemoryState.CONFIRMED,
        ),
    ):
        await _put(store, record)

    result = await PersonalMemoryQueryEngine(store).query(
        _DraftPlanner(
            intent="history",
            search_text="",
            time_from=datetime(2026, 6, 1, tzinfo=UTC),
            time_to=datetime(2026, 6, 30, 23, 59, tzinfo=UTC),
        ),
        "六月期间是什么状态？",
        [SCOPE],
        now=NOW,
    )

    assert [hit.record.memory_id for hit in result.hits] == [
        "state-overlapping-june"
    ]


async def test_relation_candidates_cannot_bypass_scope_or_authority_gate() -> None:
    store = InMemoryStore()
    await _put(
        store,
        _record(
            "agent-relation",
            "Agent 猜测某个物品属于用户。",
            memory_type="fact",
            temporal_status="current",
            day=1,
            authority=FactAuthority.AGENT_OUTPUT,
            state=MemoryState.CONFIRMED,
        ),
    )
    relation_index = _RelationIndex(
        [
            RelationCandidate(
                scope=SCOPE,
                memory_id="agent-relation",
                source="graphiti_relation",
                score=1.0,
                relation_type="OWNS",
                edge_id="edge-agent",
                episode_ids=["episode-agent"],
            ),
            RelationCandidate(
                scope=OTHER_SCOPE,
                memory_id="other-memory",
                source="graphiti_relation",
                score=1.0,
                relation_type="OWNS",
                edge_id="edge-other",
                episode_ids=["episode-other"],
            ),
        ]
    )

    result = await PersonalMemoryQueryEngine(
        store, relation_index=relation_index
    ).query(
        _DraftPlanner(
            intent="current",
            search_text="物品归属",
            entity_mentions=["物品"],
            subject="owner",
        ),
        "这个物品属于谁？",
        [SCOPE],
        now=NOW,
    )

    assert result.hits == []


async def test_relation_outage_degrades_to_nonrelation_paths() -> None:
    store = InMemoryStore()
    await _put(
        store,
        _record(
            "lexical-fallback",
            "我的相机在书房。",
            memory_type="state",
            temporal_status="current",
            day=1,
            state=MemoryState.CONFIRMED,
        ),
    )

    result = await PersonalMemoryQueryEngine(
        store, relation_index=_FailingRelationIndex()
    ).query(
        _DraftPlanner(
            intent="current",
            search_text="相机",
            entity_mentions=["相机"],
            relation_hints=["位于"],
            subject="owner",
        ),
        "相机在哪里？",
        [SCOPE],
        now=NOW,
    )

    assert [hit.record.memory_id for hit in result.hits] == ["lexical-fallback"]
    assert any("relation index unavailable" in item for item in result.warnings)


async def test_current_query_uses_temporal_semantic_index_at_bound_now() -> None:
    store = InMemoryStore()
    await _put(
        store,
        _record(
            "temporal-candidate",
            "用户临时住在另一个城市。",
            memory_type="state",
            temporal_status="current",
            topic_key="location.current",
            valid_from=datetime(2026, 7, 1, tzinfo=UTC),
            valid_to=datetime(2026, 9, 1, tzinfo=UTC),
            day=1,
        ),
    )
    semantic_index = _TemporalSemanticIndex()

    result = await PersonalMemoryQueryEngine(
        store, semantic_index=semantic_index
    ).query(
        DeterministicPersonalMemoryQueryPlanner(),
        "我现在身处何地？",
        [SCOPE],
        now=NOW,
    )

    assert semantic_index.search_calls == 0
    assert semantic_index.search_at_calls == [NOW]
    assert [hit.record.memory_id for hit in result.hits] == ["temporal-candidate"]


async def test_as_of_query_passes_the_requested_instant_to_temporal_index() -> None:
    store = InMemoryStore()
    await _put(
        store,
        _record(
            "temporal-candidate",
            "用户当时住在另一个城市。",
            memory_type="state",
            temporal_status="historical",
            topic_key="location.current",
            valid_from=datetime(2024, 1, 1, tzinfo=UTC),
            valid_to=datetime(2024, 12, 31, 23, 59, tzinfo=UTC),
            day=1,
            state=MemoryState.CONFIRMED,
        ),
    )
    semantic_index = _TemporalSemanticIndex()

    result = await PersonalMemoryQueryEngine(
        store, semantic_index=semantic_index
    ).query(
        DeterministicPersonalMemoryQueryPlanner(),
        "我在2024年06月01日身处何地？",
        [SCOPE],
        now=NOW,
    )

    expected = datetime(2024, 6, 1, 12, tzinfo=UTC)
    assert semantic_index.search_calls == 0
    assert semantic_index.search_at_calls == [expected]
    assert result.plan.intent == PersonalMemoryQueryIntent.AS_OF
    assert [hit.record.memory_id for hit in result.hits] == ["temporal-candidate"]


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


async def test_semantic_candidate_cannot_bypass_agent_output_authority_gate() -> None:
    store = InMemoryStore()
    await _put(
        store,
        _record(
            "semantic-agent-output",
            "Agent 猜测用户现在住在某个城市。",
            memory_type="state",
            temporal_status="current",
            day=1,
            actor=Actor.AGENT,
            authority=FactAuthority.AGENT_OUTPUT,
            state=MemoryState.CONFIRMED,
        ),
    )

    result = await PersonalMemoryQueryEngine(
        store, semantic_index=_AgentOutputSemanticIndex()
    ).query(
        DeterministicPersonalMemoryQueryPlanner(),
        "我现在住在哪里？",
        [SCOPE],
        now=NOW,
    )

    assert result.hits == []
    assert result.matched_record_count == 0


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


async def test_composite_semantic_sources_are_exposed_as_query_reasons() -> None:
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
    )
    composite = CompositeSemanticIndex(
        {"vector": _SemanticIndex(), "graph": _SemanticIndex()}, rrf_k=10
    )

    result = await PersonalMemoryQueryEngine(
        store, semantic_index=composite
    ).query(
        DeterministicPersonalMemoryQueryPlanner(),
        "蓉城之旅",
        [SCOPE],
        now=NOW,
    )

    assert [hit.record.memory_id for hit in result.hits] == ["semantic-chengdu"]
    assert "semantic_source:vector" in result.hits[0].reasons
    assert "semantic_source:graph" in result.hits[0].reasons


async def test_reference_planner_gets_schema_but_cannot_choose_read_scopes() -> None:
    model = _StubStructuredModel(
        {
            "intent": "current",
            "memory_types": ["state"],
            "topic_keys": ["residence.primary"],
            "temporal_statuses": ["current"],
            "subject": "豆包",
            "subject_id": "untrusted-pet",
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
    assert draft.subject == "owner"
    assert draft.subject_id == "owner"
    request = model.requests[0]
    assert "never choose read scopes" in request.instructions
    assert "known or unknown endpoint" in request.instructions
    assert "already bound outside entity_mentions" in request.instructions
    assert "interrogative endpoint from the hint" in request.instructions
    assert "Echo them unchanged" in request.instructions
    assert request.output_schema["title"] == "PersonalMemoryQueryDraft"
    assert "scopes" not in request.output_schema["properties"]


def test_query_draft_normalizes_common_temporal_status_aliases() -> None:
    draft = PersonalMemoryQueryDraft(
        temporal_statuses=["past", "history", "present", "future"]
    )

    assert draft.temporal_statuses == ["historical", "current", "planned"]


async def test_explicit_historical_window_uses_validity_not_status_label() -> None:
    engine = PersonalMemoryQueryEngine(InMemoryStore())
    plan = await engine.plan(
        _DraftPlanner(
            intent="history",
            temporal_statuses=["historical"],
            time_from=datetime(2026, 6, 1, tzinfo=UTC),
            time_to=datetime(2026, 6, 30, 23, 59, tzinfo=UTC),
        ),
        "六月时是什么状态？",
        [SCOPE],
        now=NOW,
    )

    assert plan.temporal_statuses == []
