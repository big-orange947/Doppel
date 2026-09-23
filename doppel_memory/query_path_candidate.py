"""Experimental, retrieval-only model observation of candidate relation paths.

This module does not choose scopes, query a graph, or decide whether a returned
candidate supports an answer. The host compiles and executes paths separately.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field, model_validator

from doppel_memory.intelligence import (
    StructuredGenerationRequest,
    StructuredOutputModel,
)
from doppel_memory.relation import RelationTypeDefinition
from doppel_memory.relation_path_retrieval import CandidateRelationTopology


class CandidateRelationGenerationRequest(BaseModel):
    """Question, fixed start entity, and host-owned relation vocabulary only."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    query: str = Field(min_length=1)
    anchor: str = Field(min_length=1)
    relation_type_definitions: list[RelationTypeDefinition] = Field(min_length=1)

    @model_validator(mode="after")
    def _unique_definitions(self) -> CandidateRelationGenerationRequest:
        names = [item.name for item in self.relation_type_definitions]
        if len(names) != len(set(names)):
            raise ValueError("relation definitions must be unique")
        return self


class CandidateRelationObservation(BaseModel):
    """Non-authoritative alternatives; an empty list is a valid observation."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    topologies: list[CandidateRelationTopology] = Field(
        default_factory=list, max_length=8
    )


@runtime_checkable
class CandidateRelationPathGenerator(Protocol):
    name: str
    version: str

    async def generate(
        self, request: CandidateRelationGenerationRequest
    ) -> CandidateRelationObservation: ...


REFERENCE_CANDIDATE_RELATION_PATH_INSTRUCTIONS = """\
Generate bounded graph retrieval candidates from the question and the supplied host
relation definitions. This is for finding possibly relevant evidence, not for proving
the answer. Return {"topologies": []} for a question with no useful relation path.

The host fixed the start entity as "anchor" and the requested endpoint as "answer".
Every individual topology MUST contain both fixed references and form one complete,
connected one- or two-edge path from anchor to answer. The answer reference is the
final requested endpoint, never an intermediate result. Use one shared lowercase role
name for an intermediate entity. Never split the hops of one required chain across
separate topologies and never return a partial prefix of the requested path.

For each atom, first decide which semantic role the entity at each endpoint fills.
Then bind source_ref and target_ref to the definition's source_description and
target_description. The anchor is not automatically the source: it may fill either
definition endpoint. Do not follow grammatical order or default every traversal to
outbound. Do not output traversal direction; trusted host code derives it from the
endpoint bindings.

Return the smallest candidate set justified by the actual question, normally one
topology. When one relation definition uniquely matches an explicitly requested
meaning, select only that relation. Relations that commonly co-occur, imply one
another, or concern the same entities are not alternatives. Do not add ownership,
custody, location, acquisition, employment, or other neighboring meanings unless the
question itself leaves those meanings genuinely unresolved. A contrast or negation
explicitly excludes the rejected meaning.

If the wording genuinely cannot distinguish a small number of definitions with the
same endpoint structure, put those relation_types on the SAME atom. Do not emit
separate topologies that differ only by a relation label between identical endpoint
roles. Use separate topologies only when the question genuinely permits different
connected structures. At most four types per atom and eight topologies overall.

Do not invent relation types, stored facts, entity IDs, node IDs, memory IDs, scopes,
Cypher, factual answers, or a decision to answer. Do not infer a path from a shared
topic alone. The host will validate ontology membership, path shape, temporal/scope
authority, and Store provenance before any retrieved candidate is exposed.
"""


class ReferenceCandidateRelationPathGenerator:
    """One structured model observation, with no runtime scenario rules."""

    name = "doppel.reference-candidate-relation-path-generator"
    version = "2"

    def __init__(self, model: StructuredOutputModel) -> None:
        self.model = model
        self.version = f"2:{model.name}:{model.version}"

    async def generate(
        self, request: CandidateRelationGenerationRequest
    ) -> CandidateRelationObservation:
        bound = CandidateRelationGenerationRequest.model_validate(request)
        raw = await self.model.generate(
            StructuredGenerationRequest(
                instructions=REFERENCE_CANDIDATE_RELATION_PATH_INSTRUCTIONS,
                input=bound.model_dump(mode="json"),
                output_schema=CandidateRelationObservation.model_json_schema(),
            )
        )
        observation = CandidateRelationObservation.model_validate(raw)
        allowed = {item.name for item in bound.relation_type_definitions}
        unknown = sorted(
            {
                relation_type
                for topology in observation.topologies
                for atom in topology.atoms
                for relation_type in atom.relation_types
            }
            - allowed
        )
        if unknown:
            raise ValueError(
                f"candidate path selected unknown relation types: {unknown}"
            )
        return observation
