"""Contracts for explicit V4 execute/abstain relation-path decisions."""

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
    PersonalMemoryRelationPathDraftV4,
    ReferencePersonalMemoryRelationPathPlannerV4,
)
from doppel_memory.relation import RelationTypeDefinition


class _StaticModel:
    name = "tests.static-path-v4-model"
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
            name="LOCATED_AT",
            description="The source is physically at the target.",
            source_description="entity",
            target_description="place",
        ),
    ]


def _request(*, definitions: bool = True) -> PersonalMemoryQueryRequest:
    catalog = _definitions() if definitions else []
    return PersonalMemoryQueryRequest(
        query="先找到物品的保管人，再查保管人的位置",
        now=datetime(2026, 9, 22, tzinfo=UTC),
        default_subject="owner",
        default_subject_id="owner-v4",
        available_relation_types=[item.name for item in catalog],
        relation_type_definitions=catalog,
    )


def _execute_response() -> dict[str, Any]:
    return {
        "schema_version": 4,
        "operation": "lookup",
        "temporal_view": "current",
        "search_text": "物品 保管人 位置",
        "entity_mentions": ["物品"],
        "relation_types": [],
        "subject": "contact",
        "subject_id": "untrusted",
        "path_decision": "execute",
        "path_reason": "exact",
        "path_steps": [
            {"relation_types": ["HELD_BY"], "direction": "outbound"},
            {"relation_types": ["LOCATED_AT"], "direction": "outbound"},
        ],
        "path_confidence": 0.9,
    }


def _abstain_response(reason: str = "over_bound") -> dict[str, Any]:
    return {
        "schema_version": 4,
        "operation": "lookup",
        "temporal_view": "unbounded",
        "search_text": "关系链",
        "entity_mentions": ["物品"],
        "relation_types": [],
        "subject": "owner",
        "subject_id": "owner-v4",
        "path_decision": "abstain",
        "path_reason": reason,
        "path_steps": [],
        "path_confidence": 0,
    }


def test_v4_accepts_exact_execution_and_explicit_over_bound_abstention() -> None:
    execute = PersonalMemoryRelationPathDraftV4.model_validate(_execute_response())
    abstain = PersonalMemoryRelationPathDraftV4.model_validate(_abstain_response())

    assert execute.path_decision == "execute"
    assert len(execute.path_steps) == 2
    assert abstain.path_decision == "abstain"
    assert abstain.path_reason == "over_bound"
    assert abstain.path_steps == []


@pytest.mark.parametrize(
    "payload, message",
    [
        (
            {**_abstain_response(), "path_decision": "execute", "path_reason": "exact"},
            "execute requires one or two path_steps",
        ),
        (
            {**_execute_response(), "path_reason": "ambiguous"},
            "execute requires path_reason='exact'",
        ),
        (
            {**_abstain_response(), "path_reason": "exact"},
            "abstain requires a non-exact path_reason",
        ),
        (
            {
                **_abstain_response(),
                "path_steps": [
                    {"relation_types": ["HELD_BY"], "direction": "outbound"}
                ],
                "path_confidence": 0.5,
            },
            "abstain requires empty path_steps",
        ),
    ],
)
def test_v4_rejects_inconsistent_decisions(
    payload: dict[str, Any], message: str
) -> None:
    with pytest.raises(ValidationError, match=message):
        PersonalMemoryRelationPathDraftV4.model_validate(payload)


def test_v4_still_rejects_three_steps_instead_of_silently_truncating() -> None:
    payload = _execute_response()
    payload["path_steps"] = [
        *payload["path_steps"],
        {"relation_types": ["LOCATED_AT"], "direction": "outbound"},
    ]

    with pytest.raises(ValidationError, match="at most 2"):
        PersonalMemoryRelationPathDraftV4.model_validate(payload)


def test_v4_abstention_may_retain_non_executing_soft_candidates() -> None:
    payload = {**_abstain_response("ambiguous"), "relation_types": ["HELD_BY"]}

    draft = PersonalMemoryRelationPathDraftV4.model_validate(payload)

    assert draft.path_decision == "abstain"
    assert draft.path_steps == []
    assert draft.path_confidence == 0
    assert draft.relation_types == ["HELD_BY"]


@pytest.mark.asyncio
async def test_reference_v4_binds_authority_and_emits_decision_schema() -> None:
    raw = {**_execute_response(), "cypher": "MATCH (n) RETURN n"}
    model = _StaticModel(raw)

    draft = await ReferencePersonalMemoryRelationPathPlannerV4(model).plan(_request())

    assert draft.subject == "owner"
    assert draft.subject_id == "owner-v4"
    assert draft.path_decision == "execute"
    generated = model.requests[0]
    properties = generated.output_schema["properties"]
    assert properties["schema_version"]["const"] == 4
    assert properties["path_steps"]["maxItems"] == 2
    assert set(properties["path_decision"]["enum"]) == {"execute", "abstain"}
    assert "Never emit a prefix of an over-bound chain" in generated.instructions
    assert "report over_bound and abstain" in generated.instructions
    assert "Count hops as directed relationship edges" in generated.instructions
    assert "evidence might later prove insufficient" in generated.instructions
    assert "V2 soft unordered" in generated.instructions
    assert "cypher" not in PersonalMemoryRelationPathDraftV4.model_fields


@pytest.mark.asyncio
async def test_reference_v4_returns_structured_abstention_without_definitions() -> None:
    draft = await ReferencePersonalMemoryRelationPathPlannerV4(
        _StaticModel(_abstain_response("unsupported"))
    ).plan(_request(definitions=False))

    assert draft.path_decision == "abstain"
    assert draft.path_reason == "unsupported"
    assert draft.path_steps == []


@pytest.mark.asyncio
async def test_reference_v4_rejects_executable_unknown_ontology_type() -> None:
    raw = _execute_response()
    raw["path_steps"][1] = {
        "relation_types": ["UNKNOWN_TYPE"],
        "direction": "outbound",
    }

    with pytest.raises(
        PersonalMemoryQueryPlanningError, match="outside host definitions"
    ):
        await ReferencePersonalMemoryRelationPathPlannerV4(_StaticModel(raw)).plan(
            _request()
        )
