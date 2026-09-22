"""Contracts for two-pass V7 relation-atom review and trusted compilation."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from doppel_memory.intelligence import StructuredGenerationRequest
from doppel_memory.query import (
    PersonalMemoryQueryPlanningError,
    PersonalMemoryQueryRequest,
)
from doppel_memory.query_path import ReferencePersonalMemoryRelationPathPlannerV7
from doppel_memory.relation import RelationTypeDefinition


class _SequenceModel:
    name = "tests.sequence-path-v7-model"
    version = "1"

    def __init__(self, responses: list[dict[str, Any]]) -> None:
        self.responses = responses
        self.requests: list[StructuredGenerationRequest] = []

    async def generate(self, request: StructuredGenerationRequest) -> dict[str, Any]:
        self.requests.append(request)
        return self.responses[len(self.requests) - 1]


def _definitions() -> list[RelationTypeDefinition]:
    return [
        RelationTypeDefinition(
            name="PURCHASED_AT",
            description="The source was purchased at the target.",
            source_description="item",
            target_description="venue",
        ),
        RelationTypeDefinition(
            name="EMPLOYED_BY",
            description="The source is employed by the target.",
            source_description="employee",
            target_description="employer",
        ),
        RelationTypeDefinition(
            name="CARED_FOR_BY",
            description="The source receives care from the target.",
            source_description="care recipient",
            target_description="caregiver",
        ),
    ]


def _request() -> PersonalMemoryQueryRequest:
    definitions = _definitions()
    return PersonalMemoryQueryRequest(
        query="与起点有指定关系的是谁？",
        now=datetime(2026, 9, 22, tzinfo=UTC),
        default_subject="owner",
        default_subject_id="owner-v7",
        available_relation_types=[item.name for item in definitions],
        relation_type_definitions=definitions,
    )


def _observation(
    *,
    semantics: str,
    atoms: list[dict[str, str]],
    confidence: float,
) -> dict[str, Any]:
    return {
        "schema_version": 6,
        "operation": "lookup",
        "temporal_view": "unbounded",
        "search_text": "关系查询",
        "entity_mentions": ["起点"],
        "relation_types": [],
        "observed_path_semantics": semantics,
        "anchor_ref": "anchor",
        "answer_ref": "answer",
        "relation_atoms": atoms,
        "relation_atoms_truncated": False,
        "path_confidence": confidence,
    }


@pytest.mark.asyncio
async def test_v7_review_repairs_initial_ambiguity_and_shared_endpoint() -> None:
    initial = _observation(semantics="ambiguous", atoms=[], confidence=0)
    reviewed = _observation(
        semantics="exact",
        atoms=[
            {
                "relation_type": "PURCHASED_AT",
                "source_ref": "anchor",
                "target_ref": "venue",
            },
            {
                "relation_type": "PURCHASED_AT",
                "source_ref": "answer",
                "target_ref": "venue",
            },
        ],
        confidence=0.9,
    )
    model = _SequenceModel([initial, reviewed])

    draft = await ReferencePersonalMemoryRelationPathPlannerV7(model).plan(_request())

    assert draft.path_decision == "execute"
    assert [step.direction for step in draft.path_steps] == ["outbound", "inbound"]
    assert len(model.requests) == 2
    candidate = model.requests[1].input["candidate_observation"]
    assert candidate["observed_path_semantics"] == "ambiguous"
    assert candidate["relation_atoms"] == []
    assert candidate["entity_mentions"] == ["起点"]
    normalized = " ".join(model.requests[1].instructions.split())
    assert "candidate is only a fallible first-pass analysis" in normalized
    assert "Possible absence of matching evidence" in normalized


@pytest.mark.asyncio
async def test_v7_review_adds_missing_atom_then_host_orders_double_inbound() -> None:
    initial = _observation(
        semantics="exact",
        atoms=[
            {
                "relation_type": "CARED_FOR_BY",
                "source_ref": "answer",
                "target_ref": "employee",
            }
        ],
        confidence=0.7,
    )
    reviewed = _observation(
        semantics="exact",
        atoms=[
            {
                "relation_type": "CARED_FOR_BY",
                "source_ref": "answer",
                "target_ref": "employee",
            },
            {
                "relation_type": "EMPLOYED_BY",
                "source_ref": "employee",
                "target_ref": "anchor",
            },
        ],
        confidence=0.9,
    )

    draft = await ReferencePersonalMemoryRelationPathPlannerV7(
        _SequenceModel([initial, reviewed])
    ).plan(_request())

    assert [step.relation_types for step in draft.path_steps] == [
        ["EMPLOYED_BY"],
        ["CARED_FOR_BY"],
    ]
    assert [step.direction for step in draft.path_steps] == ["inbound", "inbound"]


@pytest.mark.asyncio
async def test_v7_rejects_unknown_type_from_review() -> None:
    initial = _observation(semantics="nonrelation", atoms=[], confidence=0)
    reviewed = _observation(
        semantics="exact",
        atoms=[
            {
                "relation_type": "UNKNOWN",
                "source_ref": "anchor",
                "target_ref": "answer",
            }
        ],
        confidence=0.9,
    )

    with pytest.raises(PersonalMemoryQueryPlanningError, match="outside host definitions"):
        await ReferencePersonalMemoryRelationPathPlannerV7(
            _SequenceModel([initial, reviewed])
        ).plan(_request())


@pytest.mark.asyncio
async def test_v7_review_schema_grants_no_direction_or_execution_authority() -> None:
    response = _observation(semantics="nonrelation", atoms=[], confidence=0)
    model = _SequenceModel([response, response])

    await ReferencePersonalMemoryRelationPathPlannerV7(model).plan(_request())

    generated = model.requests[1]
    properties = generated.output_schema["properties"]
    atom_properties = generated.output_schema["$defs"]["RelationPathAtomV6"][
        "properties"
    ]
    assert "direction" not in atom_properties
    assert "path_steps" not in properties
    assert "path_decision" not in properties
    assert "path_reason" not in properties
