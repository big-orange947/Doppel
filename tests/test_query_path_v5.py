"""Contracts for the two-stage V5 relation-path Planner."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from pydantic import ValidationError

from doppel_memory.intelligence import StructuredGenerationRequest
from doppel_memory.query import (
    PersonalMemoryQueryPlanningError,
    PersonalMemoryQueryRequest,
)
from doppel_memory.query_path import (
    PersonalMemoryRelationPathObservationV5,
    ReferencePersonalMemoryRelationPathPlannerV5,
)
from doppel_memory.relation import RelationTypeDefinition


class _StaticModel:
    name = "tests.static-path-v5-model"
    version = "1"

    def __init__(self, response: dict[str, Any]) -> None:
        self.response = response
        self.requests: list[StructuredGenerationRequest] = []

    async def generate(self, request: StructuredGenerationRequest) -> dict[str, Any]:
        self.requests.append(request)
        return self.response


def _definitions() -> list[RelationTypeDefinition]:
    return [
        RelationTypeDefinition(
            name="HELD_BY",
            description="The target has custody of the source.",
            source_description="item",
            target_description="custodian",
        ),
        RelationTypeDefinition(
            name="EMPLOYED_BY",
            description="The source is employed by the target.",
            source_description="person",
            target_description="organization",
        ),
        RelationTypeDefinition(
            name="LOCATED_AT",
            description="The source is physically at the target.",
            source_description="entity",
            target_description="place",
        ),
    ]


def _request(*, definitions: bool = True) -> PersonalMemoryQueryRequest:
    catalog = _definitions() if definitions else []
    return PersonalMemoryQueryRequest(
        query="从物品查保管人，再查保管人的位置",
        now=datetime(2026, 9, 22, tzinfo=UTC),
        default_subject="owner",
        default_subject_id="owner-v5",
        available_relation_types=[item.name for item in catalog],
        relation_type_definitions=catalog,
    )


def _observation(*, steps: int = 2) -> dict[str, Any]:
    path = [
        {"relation_types": ["HELD_BY"], "direction": "outbound"},
        {"relation_types": ["LOCATED_AT"], "direction": "outbound"},
        {"relation_types": ["EMPLOYED_BY"], "direction": "inbound"},
    ][:steps]
    return {
        "schema_version": 5,
        "operation": "lookup",
        "temporal_view": "current",
        "search_text": "物品 保管人 位置",
        "entity_mentions": ["物品"],
        "relation_types": [],
        "subject": "contact",
        "subject_id": "untrusted",
        "observed_path_semantics": "exact",
        "observed_path_steps": path,
        "observed_path_truncated": False,
        "path_confidence": 0.9,
    }


@pytest.mark.asyncio
async def test_v5_host_executes_exact_two_step_observation() -> None:
    planner = ReferencePersonalMemoryRelationPathPlannerV5(
        _StaticModel(_observation())
    )

    draft = await planner.plan(_request())

    assert draft.path_decision == "execute"
    assert draft.path_reason == "exact"
    assert len(draft.path_steps) == 2
    assert draft.subject == "owner"
    assert draft.subject_id == "owner-v5"


@pytest.mark.asyncio
async def test_v5_host_abstains_when_observed_path_has_three_steps() -> None:
    draft = await ReferencePersonalMemoryRelationPathPlannerV5(
        _StaticModel(_observation(steps=3))
    ).plan(_request())

    assert draft.path_decision == "abstain"
    assert draft.path_reason == "over_bound"
    assert draft.path_steps == []
    assert draft.path_confidence == 0


@pytest.mark.asyncio
async def test_v5_host_abstains_when_observation_is_truncated() -> None:
    response = _observation(steps=3)
    response["observed_path_truncated"] = True

    draft = await ReferencePersonalMemoryRelationPathPlannerV5(
        _StaticModel(response)
    ).plan(_request())

    assert draft.path_decision == "abstain"
    assert draft.path_reason == "over_bound"


@pytest.mark.asyncio
async def test_v5_non_exact_semantics_map_to_safe_abstention() -> None:
    response = {
        **_observation(steps=0),
        "observed_path_semantics": "ambiguous",
        "path_confidence": 0,
        "relation_types": ["HELD_BY"],
    }

    draft = await ReferencePersonalMemoryRelationPathPlannerV5(
        _StaticModel(response)
    ).plan(_request())

    assert draft.path_decision == "abstain"
    assert draft.path_reason == "ambiguous"
    assert draft.relation_types == ["HELD_BY"]


@pytest.mark.asyncio
async def test_v5_ignores_soft_candidates_when_exact_path_executes() -> None:
    response = {**_observation(steps=1), "relation_types": ["HELD_BY"]}

    draft = await ReferencePersonalMemoryRelationPathPlannerV5(
        _StaticModel(response)
    ).plan(_request())

    assert draft.path_decision == "execute"
    assert draft.relation_types == []
    assert [step.relation_types for step in draft.path_steps] == [["HELD_BY"]]


def test_v5_observation_rejects_inconsistent_non_exact_shape() -> None:
    response = {
        **_observation(steps=1),
        "observed_path_semantics": "unsupported",
        "path_confidence": 0,
    }

    with pytest.raises(ValidationError, match="non-exact observation"):
        PersonalMemoryRelationPathObservationV5.model_validate(response)


@pytest.mark.asyncio
async def test_v5_rejects_unknown_observed_ontology_type() -> None:
    response = _observation(steps=1)
    response["observed_path_steps"] = [
        {"relation_types": ["UNKNOWN"], "direction": "outbound"}
    ]

    with pytest.raises(
        PersonalMemoryQueryPlanningError, match="outside host definitions"
    ):
        await ReferencePersonalMemoryRelationPathPlannerV5(
            _StaticModel(response)
        ).plan(_request())


@pytest.mark.asyncio
async def test_v5_model_only_observes_and_receives_no_execution_limit() -> None:
    model = _StaticModel(_observation())

    await ReferencePersonalMemoryRelationPathPlannerV5(model).plan(_request())

    generated = model.requests[0]
    properties = generated.output_schema["properties"]
    assert properties["schema_version"]["const"] == 5
    assert properties["observed_path_steps"]["maxItems"] == 8
    assert "path_decision" not in properties
    assert "path_reason" not in properties
    normalized = " ".join(generated.instructions.split())
    assert "do not decide whether it may execute" in normalized
    assert "do not shorten a path" in normalized
    assert "at most two" not in normalized.lower()
