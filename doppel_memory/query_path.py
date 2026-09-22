"""Experimental additive Planner v3 protocol for bounded typed relation paths.

This module deliberately does not change the stable query Planner v1/v2 wire models
or connect path execution to :class:`PersonalMemoryQueryEngine`.  It defines the
scope-free model output needed to evaluate natural-language path planning before that
capability is granted execution authority.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any, Literal, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field, model_validator

from doppel_memory.intelligence import (
    StructuredGenerationRequest,
    StructuredOutputModel,
)
from doppel_memory.query import (
    REFERENCE_PERSONAL_MEMORY_QUERY_V2_INSTRUCTIONS,
    REFERENCE_RELATION_DEFINITION_INSTRUCTIONS,
    PersonalMemoryQueryDraftV2,
    PersonalMemoryQueryPlanningError,
    PersonalMemoryQueryRequest,
    _ground_explicit_query_time_v2,
    _model_bound_version,
    _require_identity,
)
from doppel_memory.relation import RelationPathStep

logger = logging.getLogger(__name__)


class PersonalMemoryRelationPathDraftV3(PersonalMemoryQueryDraftV2):
    """Scope-free V2 query draft with an optional exact one/two-hop path.

    ``path_steps`` are hard structural constraints.  They are not soft candidate
    labels and never contain Cypher, node IDs, memory IDs, scopes, or answers.  An
    empty list means the Planner did not establish a safe path.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal[3] = 3
    relation_types: list[str] = Field(
        default_factory=list,
        description=(
            "Soft unordered candidate types only. For an exact directed one-hop or "
            "two-hop traversal, use path_steps and leave relation_types empty."
        ),
    )
    path_steps: list[RelationPathStep] = Field(
        default_factory=list,
        max_length=2,
        description=(
            "Complete ordered traversal from the question's explicit starting "
            "anchor. Use exactly one step for one exact directed relationship and "
            "two steps for an explicit two-relation chain."
        ),
    )
    path_confidence: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description=(
            "Confidence in the complete ordered path; positive only when path_steps "
            "is nonempty and exactly zero otherwise."
        ),
    )

    @model_validator(mode="after")
    def _validate_path_contract(self) -> PersonalMemoryRelationPathDraftV3:
        if self.path_steps and self.path_confidence <= 0:
            raise ValueError("a relation path requires positive path_confidence")
        if not self.path_steps and self.path_confidence != 0:
            raise ValueError("path_confidence must be zero when no path is selected")
        if self.path_steps and self.relation_types:
            raise ValueError(
                "relation_types must be empty when exact path_steps are selected"
            )
        return self


@runtime_checkable
class PersonalMemoryRelationPathPlannerV3(Protocol):
    """Produce a scope-free V3 draft without executing or authorizing a path."""

    name: str
    version: str

    async def plan(
        self, request: PersonalMemoryQueryRequest
    ) -> PersonalMemoryRelationPathDraftV3: ...


REFERENCE_PERSONAL_MEMORY_RELATION_PATH_V3_INSTRUCTIONS = """\
The output schema also offers path_steps for an exact, bounded relation path. This is
an experimental planning field, not permission to query a graph. Leave path_steps
empty and path_confidence exactly 0 unless the requested answer structurally depends
on one or two directed relations whose meanings and endpoint roles are explicitly
defined in relation_type_definitions.

Never infer path semantics from a machine label alone. Never invent a relation type,
Cypher fragment, node ID, memory ID, scope, hidden intermediate entity, or answer.
Every selected relation type must come from relation_type_definitions. Direction is
relative to traversal from the question's starting anchor: outbound follows the
definition's source to target, inbound traverses target to source, and either is only
valid when the question and definition genuinely do not determine orientation.

Use one step when one exact relation is requested. Use two steps only when reaching
the requested endpoint necessarily composes two distinct stated relationships, in
their traversal order. Do not add a second step merely because related context might
exist. When the intermediate relationship is omitted, ambiguous, unsupported by the
definitions, or would require more than two hops, return no path instead of guessing.

Apply this V3 decision order before filling the older V2 relation_types field:
1. If the question asks for one exact relationship and a definition establishes its
   meaning and endpoint roles, emit exactly one path_steps item and leave
   relation_types empty. Do not downgrade an exact one-hop traversal into the soft
   relation_types field merely because that field can name the same relation.
2. If the question explicitly composes two such relationships, emit exactly two
   ordered path_steps items and leave relation_types empty.
3. Otherwise leave path_steps empty. relation_types may then contain only genuinely
   soft, unordered candidate types allowed by the V2 contract; it is not a substitute
   representation for a known directed path.

Determine each direction from traversal topology, not sentence word order. First
identify the explicit starting anchor retained in entity_mentions. For each step,
compare the entity being traversed from with the definition's source and target roles:
outbound traverses source to target and inbound traverses target to source. The next
step starts at the endpoint reached by the previous step. Use either only when the
definition and question genuinely leave orientation unresolved.

entity_mentions must retain the explicit non-trusted-subject starting anchor. The
trusted owner/agent may be the start with no entity mention because the host binds it
outside the model. path_steps must remain empty for ordinary semantic similarity,
enumeration, or counting queries that do not specify a relation chain.

path_confidence describes confidence in the complete ordered path, not confidence
that the underlying facts exist. Use a positive value only with nonempty path_steps;
otherwise use exactly 0. When path_steps is nonempty, leave the V2 relation_types field
empty so exact path constraints and soft one-hop candidates cannot contradict each
other. The other V2 operation, temporal, subject, and search fields retain their
existing meanings.

Qualitative recency wording without a resolvable calendar boundary does not authorize
invented interval coordinates. When no concrete interval bound can be grounded from
the question and host calendar, keep temporal_view unbounded and preserve the recency
meaning in search_text instead of emitting an invalid boundless interval.
"""


class ReferencePersonalMemoryRelationPathPlannerV3:
    """Schema-constrained experimental path Planner using a host-owned model."""

    name = "doppel.reference-personal-memory-relation-path-planner-v3"
    version = "2"

    def __init__(self, model: StructuredOutputModel) -> None:
        self.model = model
        _require_identity(model, "structured output model")
        self.version = _model_bound_version(self.version, model)

    async def plan(
        self, request: PersonalMemoryQueryRequest
    ) -> PersonalMemoryRelationPathDraftV3:
        bound = PersonalMemoryQueryRequest.model_validate(request)
        instructions = (
            REFERENCE_PERSONAL_MEMORY_QUERY_V2_INSTRUCTIONS
            + REFERENCE_RELATION_DEFINITION_INSTRUCTIONS
            + REFERENCE_PERSONAL_MEMORY_RELATION_PATH_V3_INSTRUCTIONS
        )
        raw = await self.model.generate(
            StructuredGenerationRequest(
                instructions=instructions,
                input=bound.to_planner_input(),
                output_schema=PersonalMemoryRelationPathDraftV3.model_json_schema(),
            )
        )
        if isinstance(raw, BaseModel):
            raw = raw.model_dump(warnings=False)
        draft = _project_reference_relation_path_draft_v3(
            raw, allow_incomplete_time_view=True
        )
        grounded = _ground_explicit_query_time_v2(draft, bound)
        draft = PersonalMemoryRelationPathDraftV3.model_validate(
            grounded.model_dump(mode="python")
        )
        _validate_path_ontology(draft, bound)
        return draft.model_copy(
            update={
                "subject": bound.default_subject,
                "subject_id": bound.default_subject_id,
            }
        )


def _project_reference_relation_path_draft_v3(
    raw: Any, *, allow_incomplete_time_view: bool = False
) -> PersonalMemoryRelationPathDraftV3:
    """Make unknown JSON-object provider fields inert, preserving strict values."""

    validation_context = (
        {"allow_incomplete_time_view": True} if allow_incomplete_time_view else None
    )
    if not isinstance(raw, Mapping):
        return PersonalMemoryRelationPathDraftV3.model_validate(
            raw, context=validation_context
        )
    known = PersonalMemoryRelationPathDraftV3.model_fields.keys()
    projected = {name: raw[name] for name in known if name in raw}
    unknown_count = len(raw) - len(projected)
    if not projected:
        return PersonalMemoryRelationPathDraftV3.model_validate(
            raw, context=validation_context
        )
    if unknown_count:
        logger.warning(
            "reference relation path planner v3 discarded %d unknown output field(s)",
            unknown_count,
        )
    return PersonalMemoryRelationPathDraftV3.model_validate(
        projected, context=validation_context
    )


def _validate_path_ontology(
    draft: PersonalMemoryRelationPathDraftV3,
    request: PersonalMemoryQueryRequest,
) -> None:
    if not draft.path_steps:
        return
    defined = {definition.name for definition in request.relation_type_definitions}
    if not defined:
        raise PersonalMemoryQueryPlanningError(
            "exact relation paths require host relation type definitions"
        )
    selected = {
        relation_type
        for step in draft.path_steps
        for relation_type in step.relation_types
    }
    unknown = sorted(selected.difference(defined))
    if unknown:
        raise PersonalMemoryQueryPlanningError(
            f"planner selected path relation types outside host definitions: {unknown}"
        )
