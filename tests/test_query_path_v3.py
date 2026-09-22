"""Contracts for the additive, non-executing relation-path Planner v3 draft."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from pydantic import ValidationError

from doppel_memory.intelligence import StructuredGenerationRequest
from doppel_memory.models import Actor
from doppel_memory.query import (
    PersonalMemoryQueryPlanningError,
    PersonalMemoryQueryRequest,
)
from doppel_memory.query_path import (
    PersonalMemoryRelationPathDraftV3,
    ReferencePersonalMemoryRelationPathPlannerV3,
)
from doppel_memory.relation import RelationPathStep, RelationTypeDefinition


class _StaticStructuredModel:
    name = "tests.static-path-model"
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
            description="An item is currently held by a person.",
            source_description="item",
            target_description="person",
        ),
        RelationTypeDefinition(
            name="LOCATED_AT",
            description="A person or item is located at a place.",
            source_description="person or item",
            target_description="place",
        ),
    ]


def _request(*, with_definitions: bool = True) -> PersonalMemoryQueryRequest:
    definitions = _definitions() if with_definitions else []
    return PersonalMemoryQueryRequest(
        query="我的相机在谁那里，那个人现在在哪里？",
        now=datetime(2026, 9, 19, tzinfo=UTC),
        default_subject=Actor.OWNER,
        default_subject_id="owner-1",
        available_relation_types=["HELD_BY", "LOCATED_AT"],
        relation_type_definitions=definitions,
    )


def _two_hop_response() -> dict[str, Any]:
    return {
        "schema_version": 3,
        "operation": "lookup",
        "temporal_view": "current",
        "search_text": "相机 保管人 位置",
        "entity_mentions": ["相机"],
        "relation_hints": ["在谁那里", "在哪里"],
        "relation_types": [],
        "subject": "contact",
        "subject_id": "malicious-model-value",
        "path_steps": [
            {"relation_types": ["held_by"], "direction": "outbound"},
            {"relation_types": ["located_at"], "direction": "outbound"},
        ],
        "path_confidence": 0.91,
    }


def test_v3_draft_normalizes_bounded_path_without_changing_v2() -> None:
    draft = PersonalMemoryRelationPathDraftV3.model_validate(_two_hop_response())

    assert draft.schema_version == 3
    assert draft.path_steps == [
        RelationPathStep(relation_types=["HELD_BY"], direction="outbound"),
        RelationPathStep(relation_types=["LOCATED_AT"], direction="outbound"),
    ]
    assert PersonalMemoryRelationPathDraftV3.model_fields["schema_version"].default == 3


@pytest.mark.parametrize(
    "updates, message",
    [
        ({"path_confidence": 0}, "positive path_confidence"),
        ({"path_steps": [], "path_confidence": 0.5}, "must be zero"),
        ({"relation_types": ["HELD_BY"]}, "relation_types must be empty"),
        (
            {
                "path_steps": [
                    {"relation_types": ["HELD_BY"]},
                    {"relation_types": ["LOCATED_AT"]},
                    {"relation_types": ["OWNED_BY"]},
                ]
            },
            "at most 2",
        ),
    ],
)
def test_v3_draft_rejects_ambiguous_or_unbounded_path_shapes(
    updates: dict[str, Any], message: str
) -> None:
    payload = {**_two_hop_response(), **updates}

    with pytest.raises(ValidationError, match=message):
        PersonalMemoryRelationPathDraftV3.model_validate(payload)


@pytest.mark.asyncio
async def test_reference_v3_binds_subject_and_emits_only_schema_fields() -> None:
    response = {**_two_hop_response(), "cypher": "MATCH (n) RETURN n"}
    model = _StaticStructuredModel(response)
    planner = ReferencePersonalMemoryRelationPathPlannerV3(model)

    draft = await planner.plan(_request())

    assert draft.subject == Actor.OWNER
    assert draft.subject_id == "owner-1"
    assert [step.relation_types for step in draft.path_steps] == [
        ["HELD_BY"],
        ["LOCATED_AT"],
    ]
    assert "cypher" not in PersonalMemoryRelationPathDraftV3.model_fields
    generated = model.requests[0]
    assert generated.output_schema["properties"]["schema_version"]["const"] == 3
    assert generated.output_schema["properties"]["path_steps"]["maxItems"] == 2
    assert "Use exactly one step" in generated.output_schema["properties"][
        "path_steps"
    ]["description"]
    assert "Soft unordered candidate types only" in generated.output_schema[
        "properties"
    ]["relation_types"]["description"]
    assert "Never infer path semantics from a machine label alone" in (
        generated.instructions
    )
    assert "Do not downgrade an exact one-hop traversal" in generated.instructions
    assert "Determine each direction from traversal topology" in generated.instructions
    assert "invalid boundless interval" in generated.instructions
    assert generated.input["relation_type_definitions"][0]["name"] == "HELD_BY"


@pytest.mark.asyncio
async def test_reference_v3_refuses_exact_path_without_definitions() -> None:
    planner = ReferencePersonalMemoryRelationPathPlannerV3(
        _StaticStructuredModel(_two_hop_response())
    )

    with pytest.raises(
        PersonalMemoryQueryPlanningError,
        match="require host relation type definitions",
    ):
        await planner.plan(_request(with_definitions=False))


@pytest.mark.asyncio
async def test_reference_v3_refuses_model_type_outside_definitions() -> None:
    response = _two_hop_response()
    response["path_steps"][1] = {
        "relation_types": ["OWNED_BY"],
        "direction": "outbound",
    }
    planner = ReferencePersonalMemoryRelationPathPlannerV3(
        _StaticStructuredModel(response)
    )

    with pytest.raises(
        PersonalMemoryQueryPlanningError,
        match="outside host definitions.*OWNED_BY",
    ):
        await planner.plan(_request())


@pytest.mark.asyncio
async def test_reference_v3_allows_explicit_no_path_decision() -> None:
    model = _StaticStructuredModel(
        {
            "schema_version": 3,
            "operation": "lookup",
            "temporal_view": "unbounded",
            "search_text": "最近看的书",
            "subject": "owner",
            "subject_id": "owner-1",
            "path_steps": [],
            "path_confidence": 0,
        }
    )

    draft = await ReferencePersonalMemoryRelationPathPlannerV3(model).plan(_request())

    assert draft.path_steps == []
    assert draft.path_confidence == 0


@pytest.mark.asyncio
async def test_reference_v3_calendar_grounding_preserves_exact_path() -> None:
    response = _two_hop_response()
    response.update(
        {
            "temporal_view": "unbounded",
            "as_of": None,
            "time_from": None,
            "time_to": None,
        }
    )
    request = _request().model_copy(
        update={"query": "2026年3月15日相机经由保管人最终在哪里？"}
    )

    draft = await ReferencePersonalMemoryRelationPathPlannerV3(
        _StaticStructuredModel(response)
    ).plan(request)

    assert draft.temporal_view == "as_of"
    assert draft.as_of == datetime(2026, 3, 15, 12, tzinfo=UTC)
    assert [step.relation_types for step in draft.path_steps] == [
        ["HELD_BY"],
        ["LOCATED_AT"],
    ]
