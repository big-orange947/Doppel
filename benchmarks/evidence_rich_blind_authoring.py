"""Authority-preserving surface authoring for the evidence-rich blind corpus.

The provider is deliberately limited to natural-language surface text.  Scope,
identifiers, topology, time, lifecycle, authority, answerability, and evidence gold
remain in the host manifest and are never represented in the provider output schema.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from doppel_memory.intelligence import (
    StructuredGenerationRequest,
    StructuredOutputModel,
)

MAX_AUTHORING_ATTEMPTS = 3


class HostEntitySlot(BaseModel):
    """One host-owned entity identity with a provider-visible surface brief."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    surface_key: str
    entity_id: str
    scope: str
    entity_type: str
    semantic_brief: str
    shared_name_group: str = ""
    required_display_name: str = ""


class HostMemorySlot(BaseModel):
    """One host-owned memory identity; only its wording may be authored."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    surface_key: str
    memory_id: str
    scope: str
    conversation_id: str
    source_kind: Literal["chat", "group_chat", "document", "system"]
    kind: Literal["fact", "episode", "relation", "document_fact", "preference"]
    semantic_brief: str
    subject_id: str
    fact_key: str
    event_key: str = ""
    temporal_status: Literal[
        "current", "historical", "planned", "cancelled", "timeless"
    ]
    authority: Literal["human_self", "peer_statement", "agent_output"]
    state: Literal["candidate", "confirmed", "superseded", "expired"]
    valid_from: str
    valid_to: str = ""
    evidence_id: str
    corpus_role: Literal["required", "related", "forbidden", "support", "distractor"]
    tags: list[str] = Field(default_factory=lambda: ["personal-memory"])
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
        if self.kind == "episode" and not self.event_key:
            raise ValueError("episode memories require an event key")
        if self.kind != "episode" and self.event_key:
            raise ValueError("only episode memories may use an event key")
        return self


class HostQuerySlot(BaseModel):
    """One host-owned query and its private evaluation labels."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    surface_key: str
    case_id: str
    scope: str
    category: str
    domain: Literal[
        "residence",
        "career",
        "travel",
        "possessions",
        "documents",
        "preferences",
        "health",
    ]
    query_style: Literal["explicit", "paraphrase", "elliptical"]
    conversation_id: str
    intent: Literal["lookup", "count"]
    temporal_view: Literal["current", "as_of", "history"]
    semantic_brief: str
    valid_at: str
    subject_id: str
    entity_mentions: list[str] = Field(default_factory=list)
    answerable: bool
    required_memory_keys: list[str] = Field(default_factory=list)
    related_memory_keys: list[str] = Field(default_factory=list)
    hard_forbidden_memory_keys: list[str] = Field(default_factory=list)
    required_relation_routes: list[list[str]] = Field(default_factory=list)
    expected_count: int | None = Field(default=None, ge=0)

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
        if self.intent == "count" and self.expected_count != len(
            self.required_memory_keys
        ):
            raise ValueError("count query must match required evidence count")
        if self.intent == "lookup" and self.expected_count is not None:
            raise ValueError("lookup query cannot declare an expected count")
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


class OwnerAuthoringBatch(BaseModel):
    """One bounded surface-authoring request derived from a complete owner manifest."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    owner_key: str
    scope: str
    partition: Literal["dev", "sealed", "adversarial"]
    batch_id: str
    entities: list[HostEntitySlot] = Field(default_factory=list)
    memories: list[HostMemorySlot] = Field(default_factory=list)
    queries: list[HostQuerySlot] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_batch_boundary(self) -> OwnerAuthoringBatch:
        if not self.entities and not self.memories and not self.queries:
            raise ValueError("authoring batch must not be empty")
        entity_keys = _unique_values(self.entities, "surface_key", "entity surface key")
        memory_keys = _unique_values(self.memories, "surface_key", "memory surface key")
        _unique_values(self.queries, "surface_key", "query surface key")
        for item in [*self.entities, *self.memories, *self.queries]:
            if item.scope != self.scope:
                raise ValueError("authoring batch must contain one exact scope")
        for memory in self.memories:
            referenced = {memory.source_entity_key, memory.target_entity_key} - {""}
            if not referenced.issubset(entity_keys):
                raise ValueError("batch relation references an unavailable entity key")
        for query in self.queries:
            labels = {
                *query.required_memory_keys,
                *query.related_memory_keys,
                *query.hard_forbidden_memory_keys,
            }
            if not labels.issubset(memory_keys):
                raise ValueError(
                    "batch query labels reference an unavailable memory key"
                )
        return self


class BlindCorpusAuthoringManifest(BaseModel):
    """Frozen multi-owner authority manifest before any surface authoring."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    suite: str
    version: str
    language: Literal["zh-CN"]
    status: Literal["structure_frozen"]
    authoring_contract_version: Literal[3]
    implementation_baseline: str
    relation_types: list[str]
    owners: list[OwnerAuthoringManifest]
    requirements: dict[str, int]

    @model_validator(mode="after")
    def _validate_frozen_minimums(self) -> BlindCorpusAuthoringManifest:
        if len(self.relation_types) != len(set(self.relation_types)):
            raise ValueError("relation types must be unique")
        ontology = set(self.relation_types)
        _unique_values(self.owners, "owner_key", "owner key")
        _unique_values(self.owners, "scope", "owner scope")
        all_entities = [item for owner in self.owners for item in owner.entities]
        all_memories = [item for owner in self.owners for item in owner.memories]
        all_queries = [item for owner in self.owners for item in owner.queries]
        _unique_values(all_entities, "entity_id", "global entity ID")
        _unique_values(all_memories, "memory_id", "global memory ID")
        _unique_values(all_queries, "case_id", "global case ID")
        if any(
            memory.relation_type and memory.relation_type not in ontology
            for memory in all_memories
        ):
            raise ValueError("memory relation type outside the frozen ontology")
        if any(
            relation not in ontology
            for query in all_queries
            for route in query.required_relation_routes
            for relation in route
        ):
            raise ValueError("query route type outside the frozen ontology")
        for owner in self.owners:
            memories = {item.surface_key: item for item in owner.memories}
            for memory in owner.memories:
                start = _parse_time(memory.valid_from)
                if memory.valid_to and _parse_time(memory.valid_to) < start:
                    raise ValueError("memory validity interval is reversed")
            for query in owner.queries:
                at = _parse_time(query.valid_at)
                for key in query.required_memory_keys:
                    memory = memories[key]
                    if memory.subject_id != query.subject_id:
                        raise ValueError("required memory subject does not match query")
                    start = _parse_time(memory.valid_from)
                    end = _parse_time(memory.valid_to) if memory.valid_to else None
                    if at < start or (end is not None and at >= end):
                        raise ValueError(
                            "required memory is not effective at query time"
                        )
        pairs = {
            tuple(route)
            for query in all_queries
            for route in query.required_relation_routes
            if len(route) == 2
        }
        non_default_pairs = pairs - {("HELD_BY", "LIVES_IN")}
        counts = {
            "owners": len(self.owners),
            "queries": len(all_queries),
            "memories": len(all_memories),
            "relation_types": len(ontology),
            "two_hop_pairs": len(pairs),
            "non_default_two_hop_pairs": len(non_default_pairs),
        }
        per_owner_queries = Counter(query.scope for query in all_queries)
        per_owner_memories = Counter(memory.scope for memory in all_memories)
        per_owner_distractors = Counter(
            memory.scope
            for memory in all_memories
            if memory.corpus_role == "distractor"
        )
        counts.update(
            {
                "queries_per_owner": min(per_owner_queries.values(), default=0),
                "memories_per_owner": min(per_owner_memories.values(), default=0),
                "distractors_per_owner": min(per_owner_distractors.values(), default=0),
            }
        )
        for name, actual in counts.items():
            expected = int(self.requirements[f"min_{name}"])
            if actual < expected:
                raise ValueError(
                    f"manifest {name} below minimum: {actual} < {expected}"
                )
        partition_counts = Counter(owner.partition for owner in self.owners)
        for partition in ("dev", "sealed", "adversarial"):
            expected = int(self.requirements[f"min_partition_{partition}"])
            if partition_counts[partition] < expected:
                raise ValueError(
                    f"manifest partition {partition} below minimum: "
                    f"{partition_counts[partition]} < {expected}"
                )
        category_counts = Counter(query.category for query in all_queries)
        for category in (
            "current_residence",
            "temporary_residence_as_of",
            "corrected_fact",
            "episode_count",
            "one_hop_relation",
            "two_hop_relation",
            "document_fact",
            "cross_conversation",
            "subject_correction",
            "no_answer_related",
        ):
            expected = int(self.requirements[f"min_category_{category}"])
            if category_counts[category] < expected:
                raise ValueError(
                    f"manifest category {category} below minimum: "
                    f"{category_counts[category]} < {expected}"
                )
        return self

    @property
    def fingerprint(self) -> str:
        payload = json.dumps(
            self.model_dump(mode="json"),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()


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


class SurfaceReviewIssue(BaseModel):
    """One reviewer finding; it cannot change the authored surface or host gold."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    surface_key: str
    issue_code: Literal[
        "semantic_drift",
        "entity_inconsistent",
        "relation_mismatch",
        "temporal_mismatch",
        "answer_leak",
        "unnatural_language",
        "duplicate_surface",
        "malformed_surface",
    ]
    detail: str

    @field_validator("detail", mode="before")
    @classmethod
    def _require_detail(cls, value: Any) -> str:
        return _required_surface(value, "review issue detail")


class OwnerSurfaceReview(BaseModel):
    """Independent semantic review output with explicit coverage."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    reviewed_surface_keys: list[str]
    issues: list[SurfaceReviewIssue] = Field(default_factory=list)

    @field_validator("reviewed_surface_keys")
    @classmethod
    def _require_unique_review_keys(cls, value: list[str]) -> list[str]:
        normalized = [str(item or "").strip() for item in value]
        if any(not item for item in normalized):
            raise ValueError("reviewed surface keys must not be empty")
        if len(normalized) != len(set(normalized)):
            raise ValueError("reviewed surface keys must be unique")
        return normalized


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
Use authoring_nonce only as a variation seed so different synthetic owners do not share
verbatim wording; never quote, decode, or mention the nonce in any authored surface.
When required_display_name is non-empty, return that exact entity name. All other
entity names must be distinct within this owner request, including from required names.
Except for an explicitly required shared display name, entity names, memory content,
relation edge facts, and questions must not repeat exact wording used for another
synthetic owner. When must_change_surface_keys is non-empty, an earlier sealed attempt
collided with already accepted wording at those opaque keys. Use the new variation seed
to rewrite those surfaces naturally; do not mention the retry, key, or seed in output.
Return every supplied surface_key exactly once and invent no keys. For relation memories,
content must state the supplied relation and edge_fact must be a concise expression of
that same relation. For non-relation memories edge_fact must be empty. Questions must
match the supplied intent, temporal view, query style, and semantic brief. Do not add
answers to questions. Do not emit IDs, scope, authority, lifecycle, validity intervals,
evidence labels, answerability, relation types, or any field outside the output schema.
"""

REVIEW_INSTRUCTIONS = """\
Independently review synthetic Chinese surface text against each supplied semantic
brief. Review every surface_key exactly once. Do not rewrite any text and do not infer
hidden labels. Entity names must fit their type and remain internally consistent.
Memory content must express the semantic brief without adding contradictory facts; a
relation edge_fact must express exactly the supplied relation and endpoints. Questions
must match their intent, temporal view, style, and semantic brief without stating an
answer. Report only concrete issues using the allowed issue codes. If a surface is
acceptable or not, include its key in reviewed_surface_keys exactly once; report any
problem separately in issues.
Do not emit scope, identity, authority, lifecycle, evidence, answerability, rankings,
retrieval judgments, rewritten surfaces, or fields outside the output schema.
"""


def split_owner_authoring_batches(
    manifest: OwnerAuthoringManifest, *, memory_batch_size: int = 96
) -> list[OwnerAuthoringBatch]:
    """Split one owner without separating queries from their private evidence slots."""

    bound = OwnerAuthoringManifest.model_validate(manifest)
    if memory_batch_size < 1:
        raise ValueError("memory batch size must be positive")
    labelled = {
        key
        for query in bound.queries
        for key in (
            query.required_memory_keys
            + query.related_memory_keys
            + query.hard_forbidden_memory_keys
        )
    }
    first = [item for item in bound.memories if item.surface_key in labelled]
    first.extend(
        item
        for item in bound.memories
        if item.surface_key not in labelled and len(first) < memory_batch_size
    )
    first_keys = {item.surface_key for item in first}
    remaining = [item for item in bound.memories if item.surface_key not in first_keys]
    batches = [
        OwnerAuthoringBatch(
            owner_key=bound.owner_key,
            scope=bound.scope,
            partition=bound.partition,
            batch_id=f"{bound.owner_key}:01",
            entities=bound.entities,
            memories=first,
            queries=bound.queries,
        )
    ]
    for offset in range(0, len(remaining), memory_batch_size):
        batch_number = len(batches) + 1
        batches.append(
            OwnerAuthoringBatch(
                owner_key=bound.owner_key,
                scope=bound.scope,
                partition=bound.partition,
                batch_id=f"{bound.owner_key}:{batch_number:02d}",
                memories=remaining[offset : offset + memory_batch_size],
            )
        )
    return batches


def build_authoring_request(
    manifest: OwnerAuthoringManifest | OwnerAuthoringBatch,
    *,
    variation_attempt: int = 0,
    must_change_surface_keys: tuple[str, ...] = (),
) -> StructuredGenerationRequest:
    """Build a surface-only request without exposing authority-bearing host fields."""

    bound = manifest
    if variation_attempt < 0:
        raise ValueError("variation_attempt must not be negative")
    available_keys = {
        item.surface_key for item in [*bound.entities, *bound.memories, *bound.queries]
    }
    change_keys = tuple(sorted(set(must_change_surface_keys)))
    if not set(change_keys).issubset(available_keys):
        raise ValueError("must-change surface key is not present in the authoring batch")
    return StructuredGenerationRequest(
        instructions=AUTHORING_INSTRUCTIONS,
        input={
            "language": "zh-CN",
            "authoring_nonce": _authoring_nonce(
                bound, variation_attempt=variation_attempt
            ),
            "variation_attempt": variation_attempt,
            "must_change_surface_keys": list(change_keys),
            "partition_style": _partition_style(bound.partition),
            "entities": [
                {
                    "surface_key": item.surface_key,
                    "entity_type": item.entity_type,
                    "semantic_brief": item.semantic_brief,
                    "shared_name_group": item.shared_name_group,
                    "required_display_name": item.required_display_name,
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


def build_review_request(
    manifest: OwnerAuthoringManifest | OwnerAuthoringBatch,
    draft: OwnerSurfaceDraft | Mapping[str, Any],
) -> StructuredGenerationRequest:
    """Build an authority-free request for an independent semantic review pass."""

    bound = manifest
    authored = OwnerSurfaceDraft.model_validate(draft)
    # Validate coverage and relation shape before asking a reviewer to assess meaning.
    project_owner_surfaces(bound, authored)
    entities = {item.surface_key: item for item in authored.entities}
    memories = {item.surface_key: item for item in authored.memories}
    queries = {item.surface_key: item for item in authored.queries}
    return StructuredGenerationRequest(
        instructions=REVIEW_INSTRUCTIONS,
        input={
            "language": "zh-CN",
            "review_nonce": _review_nonce(bound),
            "entities": [
                {
                    "surface_key": item.surface_key,
                    "entity_type": item.entity_type,
                    "semantic_brief": item.semantic_brief,
                    "shared_name_group": item.shared_name_group,
                    "required_display_name": item.required_display_name,
                    "authored_name": entities[item.surface_key].name,
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
                    "authored_content": memories[item.surface_key].content,
                    "authored_edge_fact": memories[item.surface_key].edge_fact,
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
                    "authored_query": queries[item.surface_key].query,
                }
                for item in bound.queries
            ],
        },
        output_schema=OwnerSurfaceReview.model_json_schema(),
    )


def validate_surface_review(
    manifest: OwnerAuthoringManifest | OwnerAuthoringBatch,
    review: OwnerSurfaceReview | Mapping[str, Any],
) -> OwnerSurfaceReview:
    """Require complete review coverage and issue references inside the batch."""

    bound = manifest
    checked = OwnerSurfaceReview.model_validate(review)
    expected = {
        item.surface_key for item in [*bound.entities, *bound.memories, *bound.queries]
    }
    if set(checked.reviewed_surface_keys) != expected:
        missing = sorted(expected - set(checked.reviewed_surface_keys))
        extra = sorted(set(checked.reviewed_surface_keys) - expected)
        raise ValueError(
            f"reviewed surface keys mismatch: missing={missing}, extra={extra}"
        )
    issue_keys = [item.surface_key for item in checked.issues]
    if not set(issue_keys).issubset(expected):
        raise ValueError("review issue references an unknown surface key")
    issue_identities = [(item.surface_key, item.issue_code) for item in checked.issues]
    if len(issue_identities) != len(set(issue_identities)):
        raise ValueError("review issue code must be unique per surface key")
    return checked


async def review_owner_surfaces(
    manifest: OwnerAuthoringManifest | OwnerAuthoringBatch,
    draft: OwnerSurfaceDraft | Mapping[str, Any],
    model: StructuredOutputModel,
) -> OwnerSurfaceReview:
    """Run the independent structured reviewer and enforce complete coverage."""

    raw = await model.generate(build_review_request(manifest, draft))
    if isinstance(raw, BaseModel):
        raw = raw.model_dump(mode="json", warnings=False)
    return validate_surface_review(manifest, raw)


async def author_owner_surfaces(
    manifest: OwnerAuthoringManifest | OwnerAuthoringBatch,
    model: StructuredOutputModel,
    *,
    variation_attempt: int = 0,
    must_change_surface_keys: tuple[str, ...] = (),
) -> ProjectedOwnerSurfaces:
    """Generate, strictly validate, and project one owner's surface-only draft."""

    raw = await model.generate(
        build_authoring_request(
            manifest,
            variation_attempt=variation_attempt,
            must_change_surface_keys=must_change_surface_keys,
        )
    )
    if isinstance(raw, BaseModel):
        raw = raw.model_dump(mode="json", warnings=False)
    draft = OwnerSurfaceDraft.model_validate(raw)
    return project_owner_surfaces(manifest, draft)


def project_owner_surfaces(
    manifest: OwnerAuthoringManifest | OwnerAuthoringBatch,
    draft: OwnerSurfaceDraft | Mapping[str, Any],
) -> ProjectedOwnerSurfaces:
    """Reject partial/extra drafts and bind surface text to private host identifiers."""

    bound = manifest
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
    for item in bound.entities:
        required = item.required_display_name.strip()
        if required and entities[item.surface_key].name != required:
            raise ValueError("entity display name does not match the host requirement")
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


def _authoring_nonce(
    manifest: OwnerAuthoringManifest | OwnerAuthoringBatch,
    *,
    variation_attempt: int = 0,
) -> str:
    batch_id = (
        manifest.batch_id if isinstance(manifest, OwnerAuthoringBatch) else "full"
    )
    payload = (
        f"doppel-blind-surface-v3:{manifest.owner_key}:{batch_id}:"
        f"attempt-{variation_attempt}"
    ).encode()
    return hashlib.sha256(payload).hexdigest()[:24]


def _review_nonce(manifest: OwnerAuthoringManifest | OwnerAuthoringBatch) -> str:
    batch_id = (
        manifest.batch_id if isinstance(manifest, OwnerAuthoringBatch) else "full"
    )
    payload = f"doppel-blind-review-v1:{manifest.owner_key}:{batch_id}".encode()
    return hashlib.sha256(payload).hexdigest()[:24]


def _unique_values(values: list[Any], field: str, label: str) -> set[str]:
    result = [str(getattr(item, field)) for item in values]
    if any(not value for value in result):
        raise ValueError(f"{label} must not be empty")
    if len(result) != len(set(result)):
        raise ValueError(f"duplicate {label}")
    return set(result)


def _surface_map(values: list[Any], label: str) -> dict[str, Any]:
    keys = _unique_values(values, "surface_key", f"{label} key")
    return {
        key: next(item for item in values if item.surface_key == key) for key in keys
    }


def _require_exact_keys(
    actual: dict[str, Any], expected: list[Any], label: str
) -> None:
    required = {item.surface_key for item in expected}
    if set(actual) != required:
        missing = sorted(required - set(actual))
        extra = sorted(set(actual) - required)
        raise ValueError(
            f"{label} surface keys mismatch: missing={missing}, extra={extra}"
        )


def _required_surface(value: Any, label: str) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise ValueError(f"{label} is required")
    return normalized


def _parse_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError("manifest times must include a timezone")
    return parsed.astimezone(UTC)
