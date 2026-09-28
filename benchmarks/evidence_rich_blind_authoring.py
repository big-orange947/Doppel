"""Authority-preserving surface authoring for the evidence-rich blind corpus.

The provider is deliberately limited to natural-language surface text.  Scope,
identifiers, topology, time, lifecycle, authority, answerability, and evidence gold
remain in the host manifest and are never represented in the provider output schema.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from doppel_memory.intelligence import (
    StructuredGenerationRequest,
    StructuredOutputModel,
)


class HostEntitySlot(BaseModel):
    """One host-owned entity identity with a provider-visible surface brief."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    surface_key: str
    entity_id: str
    scope: str
    entity_type: str
    semantic_brief: str
    shared_name_group: str = ""


class HostMemorySlot(BaseModel):
    """One host-owned memory identity; only its wording may be authored."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    surface_key: str
    memory_id: str
    scope: str
    kind: str
    semantic_brief: str
    subject_id: str
    authority: str
    state: str
    valid_from: str
    valid_to: str = ""
    relation_type: str = ""
    source_entity_key: str = ""
    target_entity_key: str = ""

    @model_validator(mode="after")
    def _validate_relation_shape(self) -> HostMemorySlot:
        relation_fields = (
            self.relation_type,
            self.source_entity_key,
            self.target_entity_key,
        )
        if any(relation_fields) and not all(relation_fields):
            raise ValueError("relation memories require type and both entity keys")
        return self


class HostQuerySlot(BaseModel):
    """One host-owned query and its private evaluation labels."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    surface_key: str
    case_id: str
    scope: str
    category: str
    query_style: str
    intent: Literal["lookup", "count"]
    temporal_view: Literal["current", "as_of", "history"]
    semantic_brief: str
    valid_at: str
    answerable: bool
    required_memory_keys: list[str] = Field(default_factory=list)
    related_memory_keys: list[str] = Field(default_factory=list)
    hard_forbidden_memory_keys: list[str] = Field(default_factory=list)
    required_relation_routes: list[list[str]] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_private_gold(self) -> HostQuerySlot:
        labels = (
            self.required_memory_keys
            + self.related_memory_keys
            + self.hard_forbidden_memory_keys
        )
        if len(labels) != len(set(labels)):
            raise ValueError("query evidence labels must not overlap")
        if self.answerable != bool(self.required_memory_keys):
            raise ValueError("query answerability must match required evidence")
        if any(not 1 <= len(route) <= 2 for route in self.required_relation_routes):
            raise ValueError("relation routes must contain one or two hops")
        return self


class OwnerAuthoringManifest(BaseModel):
    """Host-authoritative inputs for exactly one owner-scoped authoring call."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    owner_key: str
    scope: str
    partition: Literal["dev", "sealed", "adversarial"]
    entities: list[HostEntitySlot] = Field(min_length=1)
    memories: list[HostMemorySlot] = Field(min_length=1)
    queries: list[HostQuerySlot] = Field(min_length=1)

    @model_validator(mode="after")
    def _validate_owner_boundary(self) -> OwnerAuthoringManifest:
        entity_keys = _unique_values(self.entities, "surface_key", "entity surface key")
        _unique_values(self.entities, "entity_id", "entity ID")
        memory_keys = _unique_values(self.memories, "surface_key", "memory surface key")
        _unique_values(self.memories, "memory_id", "memory ID")
        _unique_values(self.queries, "surface_key", "query surface key")
        _unique_values(self.queries, "case_id", "case ID")
        for item in [*self.entities, *self.memories, *self.queries]:
            if item.scope != self.scope:
                raise ValueError("authoring manifest must contain one exact scope")
        for memory in self.memories:
            referenced = {memory.source_entity_key, memory.target_entity_key} - {""}
            if not referenced.issubset(entity_keys):
                raise ValueError("memory relation references an unknown entity key")
        for query in self.queries:
            labels = {
                *query.required_memory_keys,
                *query.related_memory_keys,
                *query.hard_forbidden_memory_keys,
            }
            if not labels.issubset(memory_keys):
                raise ValueError("query labels reference an unknown memory key")
        return self


class AuthoredEntitySurface(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    surface_key: str
    name: str

    @field_validator("name", mode="before")
    @classmethod
    def _require_name(cls, value: Any) -> str:
        return _required_surface(value, "entity name")


class AuthoredMemorySurface(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    surface_key: str
    content: str
    edge_fact: str = ""

    @field_validator("content", mode="before")
    @classmethod
    def _require_content(cls, value: Any) -> str:
        return _required_surface(value, "memory content")

    @field_validator("edge_fact", mode="before")
    @classmethod
    def _normalize_edge_fact(cls, value: Any) -> str:
        return str(value or "").strip()


class AuthoredQuerySurface(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    surface_key: str
    query: str

    @field_validator("query", mode="before")
    @classmethod
    def _require_query(cls, value: Any) -> str:
        return _required_surface(value, "query text")


class OwnerSurfaceDraft(BaseModel):
    """The complete and intentionally authority-free provider output."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    entities: list[AuthoredEntitySurface]
    memories: list[AuthoredMemorySurface]
    queries: list[AuthoredQuerySurface]


class ProjectedOwnerSurfaces(BaseModel):
    """Validated surface maps keyed by host-only stable identifiers."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    entity_names_by_id: dict[str, str]
    memory_content_by_id: dict[str, str]
    edge_fact_by_memory_id: dict[str, str]
    query_text_by_case_id: dict[str, str]


AUTHORING_INSTRUCTIONS = """\
Write natural Chinese surface text for the supplied synthetic personal-memory slots.
Follow each semantic brief exactly and keep entity names consistent within this request.
Return every supplied surface_key exactly once and invent no keys. For relation memories,
content must state the supplied relation and edge_fact must be a concise expression of
that same relation. For non-relation memories edge_fact must be empty. Questions must
match the supplied intent, temporal view, query style, and semantic brief. Do not add
answers to questions. Do not emit IDs, scope, authority, lifecycle, validity intervals,
evidence labels, answerability, relation types, or any field outside the output schema.
"""


def build_authoring_request(manifest: OwnerAuthoringManifest) -> StructuredGenerationRequest:
    """Build a surface-only request without exposing authority-bearing host fields."""

    bound = OwnerAuthoringManifest.model_validate(manifest)
    return StructuredGenerationRequest(
        instructions=AUTHORING_INSTRUCTIONS,
        input={
            "language": "zh-CN",
            "partition_style": _partition_style(bound.partition),
            "entities": [
                {
                    "surface_key": item.surface_key,
                    "entity_type": item.entity_type,
                    "semantic_brief": item.semantic_brief,
                    "shared_name_group": item.shared_name_group,
                }
                for item in bound.entities
            ],
            "memories": [
                {
                    "surface_key": item.surface_key,
                    "kind": item.kind,
                    "semantic_brief": item.semantic_brief,
                    "relation": (
                        {
                            "type": item.relation_type,
                            "source_entity_key": item.source_entity_key,
                            "target_entity_key": item.target_entity_key,
                        }
                        if item.relation_type
                        else None
                    ),
                }
                for item in bound.memories
            ],
            "queries": [
                {
                    "surface_key": item.surface_key,
                    "category": item.category,
                    "query_style": item.query_style,
                    "intent": item.intent,
                    "temporal_view": item.temporal_view,
                    "semantic_brief": item.semantic_brief,
                    "required_route_shape": [
                        [f"hop-{index + 1}" for index, _ in enumerate(route)]
                        for route in item.required_relation_routes
                    ],
                }
                for item in bound.queries
            ],
        },
        output_schema=OwnerSurfaceDraft.model_json_schema(),
    )


async def author_owner_surfaces(
    manifest: OwnerAuthoringManifest, model: StructuredOutputModel
) -> ProjectedOwnerSurfaces:
    """Generate, strictly validate, and project one owner's surface-only draft."""

    raw = await model.generate(build_authoring_request(manifest))
    if isinstance(raw, BaseModel):
        raw = raw.model_dump(mode="json", warnings=False)
    draft = OwnerSurfaceDraft.model_validate(raw)
    return project_owner_surfaces(manifest, draft)


def project_owner_surfaces(
    manifest: OwnerAuthoringManifest,
    draft: OwnerSurfaceDraft | Mapping[str, Any],
) -> ProjectedOwnerSurfaces:
    """Reject partial/extra drafts and bind surface text to private host identifiers."""

    bound = OwnerAuthoringManifest.model_validate(manifest)
    authored = OwnerSurfaceDraft.model_validate(draft)
    entities = _surface_map(authored.entities, "authored entity")
    memories = _surface_map(authored.memories, "authored memory")
    queries = _surface_map(authored.queries, "authored query")
    _require_exact_keys(entities, bound.entities, "entity")
    _require_exact_keys(memories, bound.memories, "memory")
    _require_exact_keys(queries, bound.queries, "query")

    entity_names = [item.name for item in authored.entities]
    if len(entity_names) != len(set(entity_names)):
        raise ValueError("entity display names must be unique within one owner")
    query_texts = [item.query for item in authored.queries]
    if len(query_texts) != len(set(query_texts)):
        raise ValueError("query text must be unique within one owner")

    entity_names_by_id = {
        item.entity_id: entities[item.surface_key].name for item in bound.entities
    }
    memory_content_by_id: dict[str, str] = {}
    edge_fact_by_memory_id: dict[str, str] = {}
    for item in bound.memories:
        surface = memories[item.surface_key]
        if item.relation_type and not surface.edge_fact:
            raise ValueError("relation memory requires an authored edge fact")
        if not item.relation_type and surface.edge_fact:
            raise ValueError("non-relation memory cannot author an edge fact")
        memory_content_by_id[item.memory_id] = surface.content
        edge_fact_by_memory_id[item.memory_id] = surface.edge_fact
    return ProjectedOwnerSurfaces(
        entity_names_by_id=entity_names_by_id,
        memory_content_by_id=memory_content_by_id,
        edge_fact_by_memory_id=edge_fact_by_memory_id,
        query_text_by_case_id={
            item.case_id: queries[item.surface_key].query for item in bound.queries
        },
    )


def _partition_style(partition: str) -> str:
    return {
        "dev": "natural explicit wording with ordinary paraphrases",
        "sealed": "natural wording with indirect but unambiguous references",
        "adversarial": "elliptical wording with dense same-domain distractors",
    }[partition]


def _unique_values(values: list[Any], field: str, label: str) -> set[str]:
    result = [str(getattr(item, field)) for item in values]
    if any(not value for value in result):
        raise ValueError(f"{label} must not be empty")
    if len(result) != len(set(result)):
        raise ValueError(f"duplicate {label}")
    return set(result)


def _surface_map(values: list[Any], label: str) -> dict[str, Any]:
    keys = _unique_values(values, "surface_key", f"{label} key")
    return {key: next(item for item in values if item.surface_key == key) for key in keys}


def _require_exact_keys(actual: dict[str, Any], expected: list[Any], label: str) -> None:
    required = {item.surface_key for item in expected}
    if set(actual) != required:
        missing = sorted(required - set(actual))
        extra = sorted(set(actual) - required)
        raise ValueError(f"{label} surface keys mismatch: missing={missing}, extra={extra}")


def _required_surface(value: Any, label: str) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise ValueError(f"{label} is required")
    return normalized
