"""Contracts for declarative V6 relation atoms and host path compilation."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from doppel_memory.intelligence import StructuredGenerationRequest
from doppel_memory.query import (
    PersonalMemoryQueryPlanningError,
    PersonalMemoryQueryRequest,
)
from doppel_memory.query_path import ReferencePersonalMemoryRelationPathPlannerV6
from doppel_memory.relation import RelationTypeDefinition


class _StaticModel:
    name = "tests.static-path-v6-model"
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
            source_description="employee",
            target_description="employer",
        ),
        RelationTypeDefinition(
            name="CARED_FOR_BY",
            description="The source receives care from the target.",
            source_description="care recipient",
            target_description="caregiver",
        ),
        RelationTypeDefinition(
            name="PURCHASED_AT",
            description="The source was purchased at the target.",
            source_description="item",
            target_description="venue",
        ),
        RelationTypeDefinition(
            name="LOCATED_AT",
            description="The source is located at the target.",
            source_description="entity",
            target_description="place",
        ),
    ]


def _request() -> PersonalMemoryQueryRequest:
    definitions = _definitions()
    return PersonalMemoryQueryRequest(
        query="关系查询",
        now=datetime(2026, 9, 22, tzinfo=UTC),
        default_subject="owner",
        default_subject_id="owner-v6",
        available_relation_types=[item.name for item in definitions],
        relation_type_definitions=definitions,
    )


def _response(atoms: list[dict[str, str]]) -> dict[str, Any]:
    return {
        "schema_version": 6,
        "operation": "lookup",
        "temporal_view": "unbounded",
        "search_text": "关系查询",
        "entity_mentions": ["起点"],
        "relation_types": [],
        "observed_path_semantics": "exact",
        "anchor_ref": "anchor",
        "answer_ref": "answer",
        "relation_atoms": atoms,
        "relation_atoms_truncated": False,
        "path_confidence": 0.9,
    }


@pytest.mark.asyncio
async def test_v6_derives_shared_endpoint_outbound_then_inbound() -> None:
    raw = _response(
        [
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
        ]
    )

    draft = await ReferencePersonalMemoryRelationPathPlannerV6(
        _StaticModel(raw)
    ).plan(_request())

    assert [step.direction for step in draft.path_steps] == ["outbound", "inbound"]
    assert draft.path_decision == "execute"


@pytest.mark.asyncio
async def test_v6_orders_sentence_order_atoms_from_anchor_topology() -> None:
    raw = _response(
        [
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
        ]
    )

    draft = await ReferencePersonalMemoryRelationPathPlannerV6(
        _StaticModel(raw)
    ).plan(_request())

    assert [step.relation_types for step in draft.path_steps] == [
        ["EMPLOYED_BY"],
        ["CARED_FOR_BY"],
    ]
    assert [step.direction for step in draft.path_steps] == ["inbound", "inbound"]


@pytest.mark.asyncio
async def test_v6_host_marks_three_atoms_over_bound() -> None:
    raw = _response(
        [
            {"relation_type": "HELD_BY", "source_ref": "anchor", "target_ref": "a"},
            {"relation_type": "EMPLOYED_BY", "source_ref": "a", "target_ref": "b"},
            {"relation_type": "LOCATED_AT", "source_ref": "b", "target_ref": "answer"},
        ]
    )

    draft = await ReferencePersonalMemoryRelationPathPlannerV6(
        _StaticModel(raw)
    ).plan(_request())

    assert draft.path_decision == "abstain"
    assert draft.path_reason == "over_bound"
    assert draft.path_steps == []


@pytest.mark.asyncio
async def test_v6_host_abstains_on_disconnected_or_branched_atoms() -> None:
    raw = _response(
        [
            {"relation_type": "HELD_BY", "source_ref": "anchor", "target_ref": "middle"},
            {"relation_type": "LOCATED_AT", "source_ref": "other", "target_ref": "answer"},
        ]
    )

    draft = await ReferencePersonalMemoryRelationPathPlannerV6(
        _StaticModel(raw)
    ).plan(_request())

    assert draft.path_decision == "abstain"
    assert draft.path_reason == "ambiguous"


@pytest.mark.asyncio
async def test_v6_preserves_model_nonexact_semantics_as_abstention() -> None:
    raw = {
        **_response([]),
        "observed_path_semantics": "unsupported",
        "path_confidence": 0,
        "relation_types": ["HELD_BY"],
    }

    draft = await ReferencePersonalMemoryRelationPathPlannerV6(
        _StaticModel(raw)
    ).plan(_request())

    assert draft.path_decision == "abstain"
    assert draft.path_reason == "unsupported"
    assert draft.relation_types == ["HELD_BY"]


@pytest.mark.asyncio
async def test_v6_rejects_unknown_atom_type() -> None:
    raw = _response(
        [
            {
                "relation_type": "UNKNOWN",
                "source_ref": "anchor",
                "target_ref": "answer",
            }
        ]
    )

    with pytest.raises(PersonalMemoryQueryPlanningError, match="outside host definitions"):
        await ReferencePersonalMemoryRelationPathPlannerV6(
            _StaticModel(raw)
        ).plan(_request())


@pytest.mark.asyncio
async def test_v6_model_schema_has_atoms_but_no_direction_or_execution_fields() -> None:
    model = _StaticModel(
        _response(
            [
                {
                    "relation_type": "HELD_BY",
                    "source_ref": "anchor",
                    "target_ref": "answer",
                }
            ]
        )
    )

    await ReferencePersonalMemoryRelationPathPlannerV6(model).plan(_request())

    generated = model.requests[0]
    properties = generated.output_schema["properties"]
    atom_properties = generated.output_schema["$defs"]["RelationPathAtomV6"]["properties"]
    assert "relation_atoms" in properties
    assert "direction" not in atom_properties
    assert "path_decision" not in properties
    assert "path_reason" not in properties
    normalized = " ".join(generated.instructions.split())
    assert "host code orders the atoms" in normalized
    assert "Reuse the exact same reference" in normalized
