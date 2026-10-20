from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from doppel_memory import (
    EventTimeCoordinate,
    InMemoryStore,
    MemoryScope,
    PersonalMemoryExtractor,
    PersonalMemoryExtractorConfig,
    PersonalMemoryQueryEngine,
    ReferencePersonalMemoryAnalyzerV11,
    ReferencePersonalMemoryQueryPlannerV3,
)
from doppel_memory.consolidation import (
    ConsolidationPlanningError,
    _validate_episode_merge,
)
from doppel_memory.event_time import bind_event_time
from doppel_memory.intelligence import (
    PersonalMemoryAnalysisRequest,
    PersonalMemoryDraft,
    PersonalMemoryEvidenceError,
)
from doppel_memory.models import ChatMessage, MemoryState
from doppel_memory.query import PersonalMemoryQueryDraftV2
from doppel_memory.transient import TransientMemoryViewBuilder, TransientViewError

SCOPE = MemoryScope(user_id="u", agent_id="a")
NOW = datetime(2025, 2, 10, tzinfo=UTC)


def coordinate(**updates):
    return EventTimeCoordinate.model_validate(
        {
            "start": "2024-12-08T00:00:00Z",
            "end": "2024-12-08T23:59:59.999999Z",
            "precision": "day",
            "basis": "explicit",
            "expression": "2024-12-08",
            "evidence_id": "m",
            **updates,
        }
    )


class Model:
    name, version = "test-event-time", "1"

    def __init__(self, event_time):
        self.event_time = event_time

    async def generate(self, request):
        return {
            "memories": [
                {
                    "content": "Attended an event",
                    "memory_type": "episode",
                    "kind": "event",
                    "event_key": "event-one",
                    "subject": "owner",
                    "temporal_status": "historical",
                    "evidence_ids": ["m"],
                    "event_time": self.event_time,
                }
            ]
        }


async def proposal(event_time, *, actor="owner", text="I attended on 2024-12-08."):
    message = ChatMessage(message_id="m", actor=actor, text=text, at=NOW)
    extractor = PersonalMemoryExtractor(
        ReferencePersonalMemoryAnalyzerV11(Model(event_time)),
        PersonalMemoryExtractorConfig(owner_target_scope="conversation"),
    )
    return message, (await extractor.process(SCOPE, message))[0]


class Planner:
    name, version = "test-query", "1"

    def __init__(self, *, operation="lookup", **updates):
        self.values = {
            "operation": operation,
            "temporal_view": "interval",
            "time_from": "2024-12-01T00:00:00Z",
            "time_to": "2024-12-31T23:59:59.999999Z",
            **updates,
        }

    async def plan(self, request):
        return PersonalMemoryQueryDraftV2.model_validate(self.values)


async def query(record, planner=None, *, now=NOW, scopes=None):
    store = InMemoryStore()
    await store.put(record)
    return await PersonalMemoryQueryEngine(store).query(
        planner or Planner(), "events", scopes or [SCOPE], now=now, trace_limit=50
    )


async def test_late_recollection_uses_occurrence_date_not_observation_or_state_validity():
    message, p = await proposal(coordinate().model_dump(mode="json"))
    record = p.to_record()
    original = deepcopy(record)
    result = await query(record)
    assert len(result.hits) == 1
    assert result.hits[0].effective_at.date().isoformat() == "2024-12-08"
    assert "event_time_coordinate" in result.hits[0].reasons
    assert record.created_at == NOW
    assert record.metadata["valid_from"] is None and record.metadata["valid_to"] is None
    assert record == original and record.state == MemoryState.CANDIDATE
    assert record.metadata["event_time"][
        "anchor_observed_at"
    ] == NOW.isoformat().replace("+00:00", "Z")
    view = await TransientMemoryViewBuilder().build(
        PersonalMemoryAnalysisRequest(scope=SCOPE, messages=[message]),
        [p],
        reference_time=NOW,
    )
    assert view.claims[0].event_time is not None
    assert not view.claims[0].event_time.normalization_verified


async def test_removing_new_metadata_restores_unchanged_legacy_fallback():
    _, p = await proposal(coordinate().model_dump(mode="json"))
    record = p.to_record()
    record.metadata.pop("event_time")
    result = await query(record)
    assert result.hits == []
    assert result.trace is not None
    assert result.trace.counts["structural_gate:engine:outside_time_interval"] == 1


async def test_invalid_quote_fails_batch_instead_of_repairing_date():
    with pytest.raises(PersonalMemoryEvidenceError, match="occurrence"):
        await proposal(coordinate(expression="2020-01-01").model_dump(mode="json"))


async def test_merge_cannot_discard_different_or_missing_occurrence_coordinates():
    _, p = await proposal(coordinate().model_dump(mode="json"))
    record = p.to_record()
    _validate_episode_merge("merge", [record, deepcopy(record)])
    other = deepcopy(record)
    other.metadata["event_time"]["start"] = "2024-12-09T00:00:00Z"
    other.metadata["event_time"]["end"] = "2024-12-09T23:59:59.999999Z"
    with pytest.raises(ConsolidationPlanningError, match="temporal metadata"):
        _validate_episode_merge("merge", [record, other])
    other.metadata.pop("event_time")
    with pytest.raises(ConsolidationPlanningError, match="temporal metadata"):
        _validate_episode_merge("merge", [record, other])
    legacy = deepcopy(other)
    _validate_episode_merge("merge", [legacy, other])


async def test_merge_rejects_invalid_occurrence_anchor_even_if_both_copies_agree():
    _, p = await proposal(coordinate().model_dump(mode="json"))
    record = p.to_record()
    record.metadata["event_time"]["anchor_observed_at"] = "2020-01-01T00:00:00Z"
    with pytest.raises(ConsolidationPlanningError, match="temporal metadata"):
        _validate_episode_merge("merge", [record, deepcopy(record)])


async def test_arbitrary_metadata_cannot_inject_unbound_event_time():
    class MetadataModel(Model):
        async def generate(self, request):
            result = await super().generate(request)
            result["memories"][0]["metadata"] = {
                "event_time": coordinate().model_dump(mode="json")
            }
            return result

    extractor = PersonalMemoryExtractor(
        ReferencePersonalMemoryAnalyzerV11(MetadataModel(None)),
        PersonalMemoryExtractorConfig(owner_target_scope="conversation"),
    )
    proposals = await extractor.process(
        SCOPE,
        ChatMessage(
            message_id="m", actor="owner", text="I attended on 2024-12-08.", at=NOW
        ),
    )
    assert "event_time" not in proposals[0].metadata


async def test_unknown_time_is_retained_but_cannot_certify_an_exact_interval_count():
    unknown = coordinate(
        start=None,
        end=None,
        precision="unknown",
        basis="unresolved",
        expression="attended",
    )
    _, p = await proposal(unknown.model_dump(mode="json"))
    result = await query(p.to_record(), Planner(operation="count"))
    assert len(result.hits) == 1
    assert "event_time_uncertain" in result.hits[0].reasons
    assert result.count.status == "indeterminate" and result.count.value is None
    assert any("interval membership" in w for w in result.warnings)


async def test_partial_overlap_is_candidate_not_exact_membership():
    month = coordinate(
        start="2024-12-01T00:00:00Z",
        end="2024-12-31T23:59:59.999999Z",
        precision="month",
        expression="December",
    )
    _, p = await proposal(month.model_dump(mode="json"), text="I attended in December.")
    result = await query(
        p.to_record(),
        Planner(
            operation="count",
            time_from="2024-12-08T00:00:00Z",
            time_to="2024-12-08T23:59:59.999999Z",
        ),
    )
    assert len(result.hits) == 1
    assert result.count.status == "indeterminate"


async def test_disjoint_occurrence_is_filtered_even_if_observed_in_query_interval():
    _, p = await proposal(coordinate().model_dump(mode="json"))
    result = await query(
        p.to_record(),
        Planner(time_from="2025-02-01T00:00:00Z", time_to="2025-02-28T23:59:59Z"),
    )
    assert not result.hits


async def test_occurrence_does_not_bypass_observation_cutoff_or_scope():
    _, p = await proposal(coordinate().model_dump(mode="json"))
    assert not (await query(p.to_record(), now=datetime(2024, 12, 30, tzinfo=UTC))).hits
    assert not (
        await query(p.to_record(), scopes=[MemoryScope(user_id="other", agent_id="a")])
    ).hits


async def test_mutated_time_anchor_rejected_in_transient_builder_and_query():
    message, p = await proposal(coordinate().model_dump(mode="json"))
    altered = p.model_copy(deep=True)
    altered.metadata["event_time"]["anchor_observed_at"] = "2020-01-01T00:00:00Z"
    with pytest.raises(TransientViewError, match="occurrence"):
        await TransientMemoryViewBuilder().build(
            PersonalMemoryAnalysisRequest(scope=SCOPE, messages=[message]),
            [altered],
            reference_time=NOW,
        )
    result = await query(altered.to_record())
    assert not result.hits
    assert result.trace is not None
    assert result.trace.counts["structural_gate:engine:invalid_event_time"] == 1


@pytest.mark.parametrize(
    "updates",
    [
        {"start": "2024-01-01T00:00:00"},
        {"end": "2020-01-01T00:00:00Z"},
        {"precision": "instant"},
        {"basis": "unresolved"},
        {"start": None},
        {"expression": "   "},
    ],
)
def test_invalid_shape_is_not_repaired(updates):
    with pytest.raises(ValidationError):
        coordinate(**updates)


@pytest.mark.parametrize(
    "updates",
    [
        {"expression": "a date that was not said"},
        {"evidence_id": "unknown"},
    ],
)
def test_time_quote_must_belong_to_its_exact_supporting_message(updates):
    m = ChatMessage(message_id="m", text="2024-12-08", at=NOW)
    with pytest.raises(ValueError, match="bound original"):
        bind_event_time(coordinate(**updates), [m])


def test_event_date_cannot_be_attached_to_plan_or_state():
    for kind in ("plan", "state", "fact"):
        with pytest.raises(ValidationError, match="episode"):
            PersonalMemoryDraft(
                content="x",
                memory_type=kind,
                evidence_ids=["m"],
                event_time=coordinate(),
            )


async def test_v3_prompt_routes_quantities_without_keywords_or_new_count_semantics():
    class Capture:
        name, version = "capture", "1"

        async def generate(self, request):
            self.request = request
            return {"operation": "lookup", "temporal_view": "unbounded"}

    from doppel_memory.query import PersonalMemoryQueryRequest

    model = Capture()
    result = await ReferencePersonalMemoryQueryPlannerV3(model).plan(
        PersonalMemoryQueryRequest(
            query="opaque domain", now=NOW, default_subject_id="u"
        )
    )
    assert result.operation == "lookup" and not result.memory_types
    assert "elapsed duration" in model.request.instructions
    assert "previously reported" in model.request.instructions
    assert model.request.input["query"] == "opaque domain"
