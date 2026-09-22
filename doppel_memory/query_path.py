"""Experimental additive Planner protocols for bounded typed relation paths.

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

Grammatical voice and the semantic role of the requested answer do not override the
stored endpoint roles. In particular, when a definition says its source is an entity
that an action concerns and its target is the actor, a question that starts from that
entity and asks for the actor still traverses source to target, so it is outbound.
Conversely, a question that starts from the actor and asks for affected entities is
inbound. Apply this role comparison generically; do not assume that a human actor is
always the source of an edge.

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
    version = "3"

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


PathDecision = Literal["execute", "abstain"]
PathDecisionReason = Literal[
    "exact", "ambiguous", "unsupported", "over_bound", "nonrelation"
]


class PersonalMemoryRelationPathDraftV4(PersonalMemoryRelationPathDraftV3):
    """V3 path shape plus an explicit execute/abstain decision.

    ``abstain`` is a valid, structured Planner result rather than a validation
    failure. It never authorizes a graph operation. Host validation still rejects
    malformed or over-bound step arrays instead of silently truncating them.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal[4] = 4
    path_decision: PathDecision = Field(
        description=(
            "Execute only an exact one/two-hop path; otherwise abstain with empty "
            "path_steps and a reason."
        )
    )
    path_reason: PathDecisionReason = Field(
        description=(
            "Use exact only with execute. Abstention reasons are ambiguous, "
            "unsupported, over_bound, or nonrelation."
        )
    )

    @model_validator(mode="after")
    def _validate_path_decision(self) -> PersonalMemoryRelationPathDraftV4:
        if self.path_decision == "execute":
            if self.path_reason != "exact":
                raise ValueError("execute requires path_reason='exact'")
            if not self.path_steps:
                raise ValueError("execute requires one or two path_steps")
        else:
            if self.path_reason == "exact":
                raise ValueError("abstain requires a non-exact path_reason")
            if self.path_steps:
                raise ValueError("abstain requires empty path_steps")
            if self.path_confidence != 0:
                raise ValueError("abstain requires zero path_confidence")
        return self


@runtime_checkable
class PersonalMemoryRelationPathPlannerV4(Protocol):
    """Produce a scope-free V4 decision without executing or authorizing a path."""

    name: str
    version: str

    async def plan(
        self, request: PersonalMemoryQueryRequest
    ) -> PersonalMemoryRelationPathDraftV4: ...


REFERENCE_PERSONAL_MEMORY_RELATION_PATH_V4_INSTRUCTIONS = """\
V4 requires an explicit path_decision and path_reason in addition to the V3 fields.
These fields describe whether a complete path is safe to execute; they never grant
execution authority.

Use path_decision execute only when the complete requested traversal consists of one
or two exact directed relationships supported by relation_type_definitions. Then use
path_reason exact, emit every required step in order, set positive path_confidence,
and leave the older relation_types field empty.

Use path_decision abstain for every other case. Abstention must have empty path_steps,
and zero path_confidence. Choose exactly one reason:
- over_bound: the complete requested traversal needs more than two relationships;
- ambiguous: direction, relationship meaning, or the required chain is unresolved;
- unsupported: the requested relationship has no matching host definition;
- nonrelation: no exact graph relationship traversal is requested.

Never emit a prefix of an over-bound chain, never truncate it to two steps, and never
emit three or more steps. Recognizing a longer chain is not permission to represent or
execute it: report over_bound and abstain. Do not use unsupported merely because the
underlying fact may be absent; planning concerns the requested relation semantics, not
whether an answer is known. All V3 endpoint-role, direction, temporal, authority, and
ontology rules remain in force.

Count hops as directed relationship edges, not entities, noun phrases, clauses, or
requested outputs. A start anchor followed by one relationship to an intermediate
entity and a second relationship to the requested endpoint is exactly two hops and may
execute. It becomes over_bound only when reaching the requested endpoint requires a
third relationship edge.

Ambiguous means the requested relation type, direction, or chain cannot be determined;
it does not mean that retrieved evidence might later prove insufficient for the final
answer. If one definition uniquely represents the requested predicate but stored facts
may or may not establish completion, current validity, or another answer-level nuance,
the path may still execute so retrieval can return evidence for the caller to assess.

When abstaining from an exact path, relation_types may retain V2 soft unordered
candidate suggestions for ordinary recall. They never become path_steps, exact graph
filters, proof, or execution authority. Leave them empty when no candidate meaning is
supported; do not add neighboring types merely to widen recall.
"""


class ReferencePersonalMemoryRelationPathPlannerV4:
    """Schema-constrained experimental V4 decision Planner."""

    name = "doppel.reference-personal-memory-relation-path-planner-v4"
    version = "2"

    def __init__(self, model: StructuredOutputModel) -> None:
        self.model = model
        _require_identity(model, "structured output model")
        self.version = _model_bound_version(self.version, model)

    async def plan(
        self, request: PersonalMemoryQueryRequest
    ) -> PersonalMemoryRelationPathDraftV4:
        bound = PersonalMemoryQueryRequest.model_validate(request)
        instructions = (
            REFERENCE_PERSONAL_MEMORY_QUERY_V2_INSTRUCTIONS
            + REFERENCE_RELATION_DEFINITION_INSTRUCTIONS
            + REFERENCE_PERSONAL_MEMORY_RELATION_PATH_V3_INSTRUCTIONS
            + REFERENCE_PERSONAL_MEMORY_RELATION_PATH_V4_INSTRUCTIONS
        )
        raw = await self.model.generate(
            StructuredGenerationRequest(
                instructions=instructions,
                input=bound.to_planner_input(),
                output_schema=PersonalMemoryRelationPathDraftV4.model_json_schema(),
            )
        )
        if isinstance(raw, BaseModel):
            raw = raw.model_dump(warnings=False)
        draft = _project_reference_relation_path_draft_v4(
            raw, allow_incomplete_time_view=True
        )
        grounded = _ground_explicit_query_time_v2(draft, bound)
        draft = PersonalMemoryRelationPathDraftV4.model_validate(
            grounded.model_dump(mode="python")
        )
        _validate_path_ontology(draft, bound)
        return draft.model_copy(
            update={
                "subject": bound.default_subject,
                "subject_id": bound.default_subject_id,
            }
        )


def _project_reference_relation_path_draft_v4(
    raw: Any, *, allow_incomplete_time_view: bool = False
) -> PersonalMemoryRelationPathDraftV4:
    """Make unknown JSON-object provider fields inert, preserving strict values."""

    validation_context = (
        {"allow_incomplete_time_view": True} if allow_incomplete_time_view else None
    )
    if not isinstance(raw, Mapping):
        return PersonalMemoryRelationPathDraftV4.model_validate(
            raw, context=validation_context
        )
    known = PersonalMemoryRelationPathDraftV4.model_fields.keys()
    projected = {name: raw[name] for name in known if name in raw}
    unknown_count = len(raw) - len(projected)
    if not projected:
        return PersonalMemoryRelationPathDraftV4.model_validate(
            raw, context=validation_context
        )
    if unknown_count:
        logger.warning(
            "reference relation path planner v4 discarded %d unknown output field(s)",
            unknown_count,
        )
    return PersonalMemoryRelationPathDraftV4.model_validate(
        projected, context=validation_context
    )


ObservedPathSemantics = Literal["exact", "ambiguous", "unsupported", "nonrelation"]


class PersonalMemoryRelationPathObservationV5(PersonalMemoryQueryDraftV2):
    """Non-authoritative description of the complete relation path in a query.

    This model intentionally has no execute/abstain field.  The model describes the
    requested traversal, while trusted host code applies the executable two-hop bound.
    Longer paths can therefore be observed without ever becoming executable drafts.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal[5] = 5
    observed_path_semantics: ObservedPathSemantics
    observed_path_steps: list[RelationPathStep] = Field(
        default_factory=list,
        max_length=8,
        description=(
            "Complete ordered relation edges requested from the explicit starting "
            "anchor. This is an observation only and grants no execution authority."
        ),
    )
    observed_path_truncated: bool = Field(
        default=False,
        description=(
            "True only when the complete exact path contains more than eight edges; "
            "observed_path_steps then contains its first eight edges."
        ),
    )
    path_confidence: float = Field(default=0.0, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def _validate_observation(self) -> PersonalMemoryRelationPathObservationV5:
        if self.observed_path_semantics == "exact":
            if not self.observed_path_steps:
                raise ValueError("an exact observation requires path steps")
            if self.path_confidence <= 0:
                raise ValueError("an exact observation requires positive confidence")
        else:
            if self.observed_path_steps:
                raise ValueError("a non-exact observation requires empty path steps")
            if self.observed_path_truncated:
                raise ValueError("only an exact observation may be truncated")
            if self.path_confidence != 0:
                raise ValueError("a non-exact observation requires zero confidence")
        return self


@runtime_checkable
class PersonalMemoryRelationPathPlannerV5(Protocol):
    """Produce the safe V4 execution draft through a two-stage V5 observation."""

    name: str
    version: str

    async def plan(
        self, request: PersonalMemoryQueryRequest
    ) -> PersonalMemoryRelationPathDraftV4: ...


REFERENCE_PERSONAL_MEMORY_RELATION_PATH_V5_INSTRUCTIONS = """\
Describe the complete directed relationship traversal requested by the question in
observed_path_steps. This is a non-authoritative observation: do not decide whether it
may execute, do not emit path_decision/path_reason, and do not shorten a path to fit an
execution limit. Trusted host code makes that decision after validating your output.

Set observed_path_semantics to exact when the requested relation meanings, endpoint
roles, directions, and complete traversal are all determined by the question and
relation_type_definitions. Emit every required relationship edge in traversal order.
An anchor followed by a relationship to an intermediate entity and another relationship
to the requested endpoint has two observed steps. Count relationship edges, not entities,
noun phrases, clauses, or requested outputs.

Never infer semantics from a machine label alone and never invent a relation type,
Cypher fragment, node ID, memory ID, scope, hidden intermediate entity, or answer. Each
observed type must come from relation_type_definitions. Direction is relative to
traversal from the question's starting anchor: outbound follows a definition's source
to target and inbound traverses target to source. Determine it from endpoint roles, not
sentence word order or grammatical voice. The next step begins at the endpoint reached
by the previous step. Use either only when the definition and question genuinely leave
orientation unresolved.

entity_mentions must retain the explicit non-trusted-subject starting anchor. The
trusted owner or agent may be the start without an entity mention because the host binds
that authority outside the model. Ordinary semantic similarity, enumeration, or counting
questions that do not request a relationship traversal are nonrelation.

The observation schema can represent at most eight edges. If an exact requested path is
longer, emit its first eight edges and set observed_path_truncated true. Otherwise set it
false. Never omit an edge merely because the path is long. A truncated observation is
diagnostic only and can never authorize execution.

Use ambiguous when the requested relationship meaning, direction, or chain is genuinely
underdetermined; unsupported when a requested relationship has no matching host
definition; and nonrelation when no exact graph traversal is requested. For those three
states leave observed_path_steps empty, observed_path_truncated false, and path_confidence
zero. Whether matching facts exist in storage is an answer-evidence question, not path
ambiguity. For an exact observation use positive confidence.

relation_types remains an optional soft unordered V2 candidate field. It is not part of
the observed traversal and grants no authority. Prefer it only for non-exact ordinary
recall. If it is also emitted with an exact observation, the host ignores it rather than
mixing soft candidates with an executable path. All V2 temporal and authority rules
remain in force.
"""


class ReferencePersonalMemoryRelationPathPlannerV5:
    """Two-stage Planner: model observes a path; host decides execution deterministically."""

    name = "doppel.reference-personal-memory-relation-path-planner-v5"
    version = "1"

    def __init__(self, model: StructuredOutputModel) -> None:
        self.model = model
        _require_identity(model, "structured output model")
        self.version = _model_bound_version(self.version, model)

    async def plan(
        self, request: PersonalMemoryQueryRequest
    ) -> PersonalMemoryRelationPathDraftV4:
        bound = PersonalMemoryQueryRequest.model_validate(request)
        instructions = (
            REFERENCE_PERSONAL_MEMORY_QUERY_V2_INSTRUCTIONS
            + REFERENCE_RELATION_DEFINITION_INSTRUCTIONS
            + REFERENCE_PERSONAL_MEMORY_RELATION_PATH_V5_INSTRUCTIONS
        )
        raw = await self.model.generate(
            StructuredGenerationRequest(
                instructions=instructions,
                input=bound.to_planner_input(),
                output_schema=PersonalMemoryRelationPathObservationV5.model_json_schema(),
            )
        )
        if isinstance(raw, BaseModel):
            raw = raw.model_dump(warnings=False)
        observation = _project_reference_relation_path_observation_v5(
            raw, allow_incomplete_time_view=True
        )
        grounded = _ground_explicit_query_time_v2(observation, bound)
        observation = PersonalMemoryRelationPathObservationV5.model_validate(
            grounded.model_dump(mode="python")
        )
        _validate_observed_path_ontology(observation, bound)
        return _decide_observed_path_v5(observation, bound)


def _project_reference_relation_path_observation_v5(
    raw: Any, *, allow_incomplete_time_view: bool = False
) -> PersonalMemoryRelationPathObservationV5:
    """Project JSON-object output onto the strict non-authoritative V5 schema."""

    validation_context = (
        {"allow_incomplete_time_view": True} if allow_incomplete_time_view else None
    )
    if not isinstance(raw, Mapping):
        return PersonalMemoryRelationPathObservationV5.model_validate(
            raw, context=validation_context
        )
    known = PersonalMemoryRelationPathObservationV5.model_fields.keys()
    projected = {name: raw[name] for name in known if name in raw}
    unknown_count = len(raw) - len(projected)
    if not projected:
        return PersonalMemoryRelationPathObservationV5.model_validate(
            raw, context=validation_context
        )
    if unknown_count:
        logger.warning(
            "reference relation path planner v5 discarded %d unknown output field(s)",
            unknown_count,
        )
    return PersonalMemoryRelationPathObservationV5.model_validate(
        projected, context=validation_context
    )


def _validate_observed_path_ontology(
    observation: PersonalMemoryRelationPathObservationV5,
    request: PersonalMemoryQueryRequest,
) -> None:
    if not observation.observed_path_steps:
        return
    defined = {definition.name for definition in request.relation_type_definitions}
    if not defined:
        raise PersonalMemoryQueryPlanningError(
            "observed relation paths require host relation type definitions"
        )
    selected = {
        relation_type
        for step in observation.observed_path_steps
        for relation_type in step.relation_types
    }
    unknown = sorted(selected.difference(defined))
    if unknown:
        raise PersonalMemoryQueryPlanningError(
            f"planner observed path relation types outside host definitions: {unknown}"
        )


def _decide_observed_path_v5(
    observation: PersonalMemoryRelationPathObservationV5,
    request: PersonalMemoryQueryRequest,
) -> PersonalMemoryRelationPathDraftV4:
    """Apply the executable bound without trusting a model-authored decision."""

    exact = observation.observed_path_semantics == "exact"
    over_bound = exact and (
        observation.observed_path_truncated
        or len(observation.observed_path_steps) > 2
    )
    execute = exact and not over_bound
    if execute:
        reason: PathDecisionReason = "exact"
        path_steps = observation.observed_path_steps
        confidence = observation.path_confidence
        relation_types: list[str] = []
    else:
        reason = (
            "over_bound"
            if over_bound
            else observation.observed_path_semantics
        )
        path_steps = []
        confidence = 0.0
        relation_types = observation.relation_types

    payload = observation.model_dump(mode="python")
    for field in (
        "observed_path_semantics",
        "observed_path_steps",
        "observed_path_truncated",
        "path_confidence",
    ):
        payload.pop(field, None)
    payload.update(
        {
            "schema_version": 4,
            "subject": request.default_subject,
            "subject_id": request.default_subject_id,
            "relation_types": relation_types,
            "path_decision": "execute" if execute else "abstain",
            "path_reason": reason,
            "path_steps": path_steps,
            "path_confidence": confidence,
        }
    )
    return PersonalMemoryRelationPathDraftV4.model_validate(payload)


class RelationPathAtomV6(BaseModel):
    """One declarative relation with definition-oriented endpoint bindings."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    relation_type: str = Field(min_length=1)
    source_ref: str = Field(pattern=r"^[a-z][a-z0-9_]{0,31}$")
    target_ref: str = Field(pattern=r"^[a-z][a-z0-9_]{0,31}$")

    @model_validator(mode="after")
    def _validate_atom(self) -> RelationPathAtomV6:
        if self.source_ref == self.target_ref:
            raise ValueError("relation atom endpoints must differ")
        canonical = self.relation_type.strip().upper()
        if not canonical:
            raise ValueError("relation atom type must not be empty")
        object.__setattr__(self, "relation_type", canonical)
        return self


class PersonalMemoryRelationPathObservationV6(PersonalMemoryQueryDraftV2):
    """A declarative relation graph whose traversal is compiled by the host."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal[6] = 6
    observed_path_semantics: ObservedPathSemantics
    anchor_ref: Literal["anchor"] = "anchor"
    answer_ref: Literal["answer"] = "answer"
    relation_atoms: list[RelationPathAtomV6] = Field(default_factory=list, max_length=8)
    relation_atoms_truncated: bool = False
    path_confidence: float = Field(default=0.0, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def _validate_observation(self) -> PersonalMemoryRelationPathObservationV6:
        if self.observed_path_semantics == "exact":
            if not self.relation_atoms:
                raise ValueError("an exact atom observation requires relation atoms")
            if self.path_confidence <= 0:
                raise ValueError("an exact atom observation requires positive confidence")
        else:
            if self.relation_atoms:
                raise ValueError("a non-exact atom observation requires empty atoms")
            if self.relation_atoms_truncated:
                raise ValueError("only an exact atom observation may be truncated")
            if self.path_confidence != 0:
                raise ValueError("a non-exact atom observation requires zero confidence")
        return self


REFERENCE_PERSONAL_MEMORY_RELATION_PATH_V6_INSTRUCTIONS = """\
Describe the requested relationship topology as declarative relation_atoms. This is a
non-authoritative observation. Do not emit path_steps, direction, path_decision, or
path_reason. Trusted host code orders the atoms, derives traversal direction, and decides
whether the resulting path may execute.

Use the fixed reference anchor for the explicit starting entity retained in
entity_mentions, and answer for the entity requested by the question. Use short
lowercase references such as middle, person, organization, place, or container for
intermediate entities. Reuse the exact same reference wherever two atoms share an
entity. References identify semantic roles only; they are not database IDs, node IDs,
memory IDs, scopes, or answers.

For each atom, relation_type must be one host definition. source_ref names the entity
that fills that definition's source_description role and target_ref names the entity
that fills its target_description role. Bind definition endpoint roles regardless of
sentence order, grammatical voice, or the order in which predicates are mentioned. Do
not encode traversal direction: the host derives outbound when traversing source to
target and inbound when traversing target to source.

Set observed_path_semantics exact only when all requested predicates and their endpoint
bindings form one complete, unambiguous relationship path from anchor to answer. Emit
every required atom, including both sides of shared-endpoint comparisons. Do not omit an
implicit atom merely because the intermediate entity is unnamed. Whether matching facts
exist in storage is an evidence question, not topology ambiguity.

Use ambiguous when the requested predicate or endpoint binding is genuinely unresolved;
unsupported when a requested predicate has no host definition; and nonrelation when the
question requests no graph relationship topology. Those states require no atoms and zero
path confidence. Exact observations use positive confidence.

The schema represents at most eight atoms. For a longer exact path, emit the first eight
connected atoms and set relation_atoms_truncated true. Otherwise set it false. Never
shorten a relation graph to an execution limit. All V2 temporal and authority rules
remain in force. The older relation_types field is only a soft ordinary-recall hint and
never participates in topology compilation.
"""


class ReferencePersonalMemoryRelationPathPlannerV6:
    """Model relation atoms, then compile their traversal entirely in trusted code."""

    name = "doppel.reference-personal-memory-relation-path-planner-v6"
    version = "1"

    def __init__(self, model: StructuredOutputModel) -> None:
        self.model = model
        _require_identity(model, "structured output model")
        self.version = _model_bound_version(self.version, model)

    async def plan(
        self, request: PersonalMemoryQueryRequest
    ) -> PersonalMemoryRelationPathDraftV4:
        bound = PersonalMemoryQueryRequest.model_validate(request)
        raw = await self.model.generate(
            StructuredGenerationRequest(
                instructions=(
                    REFERENCE_PERSONAL_MEMORY_QUERY_V2_INSTRUCTIONS
                    + REFERENCE_RELATION_DEFINITION_INSTRUCTIONS
                    + REFERENCE_PERSONAL_MEMORY_RELATION_PATH_V6_INSTRUCTIONS
                ),
                input=bound.to_planner_input(),
                output_schema=PersonalMemoryRelationPathObservationV6.model_json_schema(),
            )
        )
        if isinstance(raw, BaseModel):
            raw = raw.model_dump(warnings=False)
        observation = _project_reference_relation_path_observation_v6(
            raw, allow_incomplete_time_view=True
        )
        grounded = _ground_explicit_query_time_v2(observation, bound)
        observation = PersonalMemoryRelationPathObservationV6.model_validate(
            grounded.model_dump(mode="python")
        )
        _validate_atom_ontology_v6(observation, bound)
        return _compile_relation_atoms_v6(observation, bound)


def _project_reference_relation_path_observation_v6(
    raw: Any, *, allow_incomplete_time_view: bool = False
) -> PersonalMemoryRelationPathObservationV6:
    context = (
        {"allow_incomplete_time_view": True} if allow_incomplete_time_view else None
    )
    if not isinstance(raw, Mapping):
        return PersonalMemoryRelationPathObservationV6.model_validate(raw, context=context)
    known = PersonalMemoryRelationPathObservationV6.model_fields.keys()
    projected = {name: raw[name] for name in known if name in raw}
    if not projected:
        return PersonalMemoryRelationPathObservationV6.model_validate(raw, context=context)
    unknown_count = len(raw) - len(projected)
    if unknown_count:
        logger.warning(
            "reference relation path planner v6 discarded %d unknown output field(s)",
            unknown_count,
        )
    return PersonalMemoryRelationPathObservationV6.model_validate(
        projected, context=context
    )


def _validate_atom_ontology_v6(
    observation: PersonalMemoryRelationPathObservationV6,
    request: PersonalMemoryQueryRequest,
) -> None:
    defined = {definition.name for definition in request.relation_type_definitions}
    selected = {atom.relation_type for atom in observation.relation_atoms}
    if selected and not defined:
        raise PersonalMemoryQueryPlanningError(
            "relation atom observations require host relation type definitions"
        )
    unknown = sorted(selected.difference(defined))
    if unknown:
        raise PersonalMemoryQueryPlanningError(
            f"planner observed atom relation types outside host definitions: {unknown}"
        )


def _compile_relation_atoms_v6(
    observation: PersonalMemoryRelationPathObservationV6,
    request: PersonalMemoryQueryRequest,
) -> PersonalMemoryRelationPathDraftV4:
    """Compile one unique anchor-to-answer chain and derive every direction."""

    semantics = observation.observed_path_semantics
    if semantics != "exact":
        return _atom_decision_draft_v6(
            observation, request, decision="abstain", reason=semantics, steps=[]
        )
    if observation.relation_atoms_truncated or len(observation.relation_atoms) > 2:
        return _atom_decision_draft_v6(
            observation, request, decision="abstain", reason="over_bound", steps=[]
        )

    adjacency: dict[str, list[tuple[int, str]]] = {}
    for index, atom in enumerate(observation.relation_atoms):
        adjacency.setdefault(atom.source_ref, []).append((index, atom.target_ref))
        adjacency.setdefault(atom.target_ref, []).append((index, atom.source_ref))
    if (
        "anchor" not in adjacency
        or "answer" not in adjacency
        or any(len(edges) > 2 for edges in adjacency.values())
    ):
        return _atom_decision_draft_v6(
            observation, request, decision="abstain", reason="ambiguous", steps=[]
        )

    current = "anchor"
    used: set[int] = set()
    steps: list[RelationPathStep] = []
    while current != "answer":
        options = [item for item in adjacency[current] if item[0] not in used]
        if len(options) != 1:
            return _atom_decision_draft_v6(
                observation, request, decision="abstain", reason="ambiguous", steps=[]
            )
        index, next_ref = options[0]
        atom = observation.relation_atoms[index]
        direction = "outbound" if current == atom.source_ref else "inbound"
        steps.append(
            RelationPathStep(
                relation_types=[atom.relation_type], direction=direction
            )
        )
        used.add(index)
        current = next_ref
        if len(steps) > len(observation.relation_atoms):
            return _atom_decision_draft_v6(
                observation, request, decision="abstain", reason="ambiguous", steps=[]
            )
    if len(used) != len(observation.relation_atoms):
        return _atom_decision_draft_v6(
            observation, request, decision="abstain", reason="ambiguous", steps=[]
        )
    return _atom_decision_draft_v6(
        observation, request, decision="execute", reason="exact", steps=steps
    )


def _atom_decision_draft_v6(
    observation: PersonalMemoryRelationPathObservationV6,
    request: PersonalMemoryQueryRequest,
    *,
    decision: PathDecision,
    reason: PathDecisionReason,
    steps: list[RelationPathStep],
) -> PersonalMemoryRelationPathDraftV4:
    payload = observation.model_dump(mode="python")
    for field in (
        "anchor_ref",
        "answer_ref",
        "observed_path_semantics",
        "relation_atoms",
        "relation_atoms_truncated",
        "path_confidence",
    ):
        payload.pop(field, None)
    execute = decision == "execute"
    payload.update(
        {
            "schema_version": 4,
            "subject": request.default_subject,
            "subject_id": request.default_subject_id,
            "relation_types": [] if execute else observation.relation_types,
            "path_decision": decision,
            "path_reason": reason,
            "path_steps": steps,
            "path_confidence": observation.path_confidence if execute else 0.0,
        }
    )
    return PersonalMemoryRelationPathDraftV4.model_validate(payload)
