"""Domain-neutral point-in-time candidates; no timestamps invented from observation."""

from datetime import UTC, datetime, timedelta

import pytest

from doppel_memory import (
    FactAuthority,
    InMemoryStore,
    MemoryRecord,
    MemoryScope,
    MemoryState,
    PersonalMemoryQueryDraft,
    PersonalMemoryQueryDraftV2,
    PersonalMemoryQueryEngine,
)

SCOPE = MemoryScope(user_id="owner", agent_id="test")
NOW = datetime(2026, 6, 1, tzinfo=UTC)
POINT = NOW - timedelta(days=30)


class Planner:
    name, version = "test.explicit-fields", "1"

    def __init__(self, *, legacy=False, **fields):
        self.draft = (
            PersonalMemoryQueryDraft(intent="as_of", **fields)
            if legacy
            else PersonalMemoryQueryDraftV2(temporal_view="as_of", **fields)
        )

    async def plan(self, request):
        return self.draft


def record(identity="a", status="current", **metadata):
    return MemoryRecord(
        memory_id=identity,
        scope=SCOPE,
        kind="fact",
        actor="owner",
        authority=FactAuthority.HUMAN_SELF,
        state=MemoryState.CONFIRMED,
        content="opaque claim",
        tags=["personal-memory"],
        created_at=NOW - timedelta(days=1),
        metadata={
            "subject": "owner",
            "subject_id": "owner",
            "personal_memory_type": "fact",
            "topic_key": "opaque.slot",
            "temporal_status": status,
            **metadata,
        },
    )


@pytest.mark.parametrize("legacy", [False, True])
@pytest.mark.parametrize(
    "status", ["current", "historical", "unknown", "custom-status"]
)
async def test_undated_active_evidence_is_retained_but_not_certified(legacy, status):
    store = InMemoryStore()
    original = record(status=status)
    await store.put(original)
    result = await PersonalMemoryQueryEngine(store).query(
        Planner(legacy=legacy, as_of=POINT, search_text="opaque"),
        "opaque",
        [SCOPE],
        now=NOW,
    )
    assert [hit.record.memory_id for hit in result.hits] == ["a"]
    hit = result.hits[0]
    assert hit.candidate_evidence.as_of_match == "uncertain"
    assert "valid_at_as_of" not in hit.reasons
    assert "validity_time_uncertain" in hit.reasons
    assert any(w.startswith("validity_time_uncertain:") for w in result.warnings)
    assert hit.record.metadata.get("valid_from") is None
    assert (await store.get(SCOPE, "a")).model_dump() == original.model_dump()


@pytest.mark.parametrize(
    "bounds",
    [
        {"valid_from": POINT.isoformat()},
        {"valid_to": POINT.isoformat()},
        {
            "valid_from": (POINT - timedelta(days=1)).isoformat(),
            "valid_to": (POINT + timedelta(days=1)).isoformat(),
        },
    ],
)
async def test_known_bounds_keep_open_interval_contract(bounds):
    store = InMemoryStore()
    await store.put(record(status="historical", **bounds))
    result = await PersonalMemoryQueryEngine(store).query(
        Planner(as_of=POINT), "opaque", [SCOPE], now=NOW
    )
    assert result.hits[0].candidate_evidence.as_of_match == "validity_match"
    assert "valid_at_as_of" in result.hits[0].reasons
    assert not any(w.startswith("validity_time_uncertain:") for w in result.warnings)


async def test_timeless_is_separate_from_explicit_validity():
    store = InMemoryStore()
    await store.put(record(status="timeless"))
    result = await PersonalMemoryQueryEngine(store).query(
        Planner(as_of=POINT), "opaque", [SCOPE], now=NOW
    )
    assert result.hits[0].candidate_evidence.as_of_match == "timeless"
    assert "valid_at_as_of" not in result.hits[0].reasons


@pytest.mark.parametrize(
    "change",
    [
        {"valid_from": (POINT + timedelta(days=1)).isoformat()},
        {"valid_to": (POINT - timedelta(days=1)).isoformat()},
        {"state": MemoryState.SUPERSEDED},
        {"state": MemoryState.EXPIRED},
        {"authority": FactAuthority.AGENT_OUTPUT},
        {"scope": MemoryScope(user_id="foreign", agent_id="test")},
        {"created_at": NOW + timedelta(days=1)},
    ],
)
async def test_retention_does_not_relax_known_mismatch_or_authority(change):
    store = InMemoryStore()
    meta = {key: value for key, value in change.items() if key.startswith("valid_")}
    row = record(**meta).model_copy(
        update={key: value for key, value in change.items() if key not in meta}
    )
    await store.put(row)
    result = await PersonalMemoryQueryEngine(store).query(
        Planner(as_of=POINT), "opaque", [SCOPE], now=NOW
    )
    assert result.hits == []


async def test_uncertain_membership_does_not_become_exact_count():
    store = InMemoryStore()
    row = record(
        status="historical", personal_memory_type="episode", event_key="event-a"
    )
    await store.put(row)
    result = await PersonalMemoryQueryEngine(store).query(
        Planner(operation="count", as_of=POINT), "count", [SCOPE], now=NOW
    )
    assert len(result.hits) == 1
    assert result.count.status == "indeterminate" and result.count.value is None
    assert "uncertain validity" in result.count.reason


async def test_invalid_bound_is_uncertain_not_silently_open_ended():
    store = InMemoryStore()
    await store.put(record(valid_from="not-a-date", valid_to=NOW.isoformat()))
    result = await PersonalMemoryQueryEngine(store).query(
        Planner(as_of=POINT), "opaque", [SCOPE], now=NOW
    )
    assert result.hits[0].candidate_evidence.as_of_match == "uncertain"


async def test_semantic_index_time_hint_cannot_certify_store_validity():
    from doppel_memory import PersonalMemoryQueryConfig, RecallResult

    class Index:
        async def search(self, query, scopes, **kwargs):
            return [
                RecallResult(
                    memory_id="a",
                    scope=SCOPE,
                    fact="index payload",
                    valid_at=POINT,
                    similarity=0.99,
                )
            ]

    store = InMemoryStore()
    await store.put(record(status="historical"))
    result = await PersonalMemoryQueryEngine(
        store,
        PersonalMemoryQueryConfig(candidate_fusion="union"),
        semantic_index=Index(),
    ).query(Planner(as_of=POINT, search_text="opaque"), "opaque", [SCOPE], now=NOW)
    assert result.hits[0].record.content == "opaque claim"
    assert result.hits[0].candidate_evidence.as_of_match == "uncertain"
    assert result.hits[0].candidate_evidence.store_revalidated


def test_old_candidate_evidence_defaults_to_unassessed_point_in_time():
    from doppel_memory import PersonalMemoryCandidateEvidence

    assert (
        PersonalMemoryCandidateEvidence.model_validate(
            {"store_revalidated": True}
        ).as_of_match
        == "not_requested"
    )
