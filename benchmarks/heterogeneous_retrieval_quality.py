"""Schema and invariants for the frozen heterogeneous personal-memory corpus."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from doppel_memory.relation import RelationPathStep

Partition = Literal["dev", "sealed", "adversarial"]
Category = Literal[
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
]


class HeterogeneousScope(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    user_id: str
    agent_id: str
    partition: Partition


class HeterogeneousMemory(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    memory_id: str
    scope: str
    conversation_id: str
    source_kind: Literal["chat", "group_chat", "document", "system"]
    kind: Literal["fact", "episode", "relation", "document_fact", "preference"]
    content: str
    subject_id: str
    fact_key: str
    event_key: str = ""
    temporal_status: Literal[
        "current", "historical", "planned", "cancelled", "timeless"
    ] = "current"
    valid_from: str
    valid_to: str = ""
    authority: Literal["human_self", "peer_statement", "agent_output"] = (
        "human_self"
    )
    state: Literal["candidate", "confirmed", "superseded", "expired"] = (
        "confirmed"
    )
    tags: list[str] = Field(default_factory=lambda: ["personal-memory"])
    evidence_id: str


class HeterogeneousEntity(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    entity_id: str
    scope: str
    name: str
    entity_type: str


class HeterogeneousEdge(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    edge_id: str
    scope: str
    source_entity_id: str
    target_entity_id: str
    relation_type: str
    fact: str
    memory_id: str
    valid_at: str
    invalid_at: str = ""


class HeterogeneousQuery(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    case_id: str
    partition: Partition
    category: Category
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
    scope: str
    conversation_id: str
    query: str
    intent: Literal["lookup", "count"]
    temporal_view: Literal["current", "as_of", "history"]
    valid_at: str
    subject_id: str
    entity_mentions: list[str] = Field(default_factory=list)
    required_routes: list[list[RelationPathStep]] = Field(default_factory=list)
    required_memory_ids: list[str] = Field(default_factory=list)
    related_memory_ids: list[str] = Field(default_factory=list)
    hard_forbidden_memory_ids: list[str] = Field(default_factory=list)
    expected_count: int | None = Field(default=None, ge=0)
    answerable: bool


class HeterogeneousRetrievalDataset(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    suite: str
    version: str
    language: Literal["zh-CN"]
    status: Literal["frozen"]
    frozen: Literal[True]
    publication_ready: Literal[False]
    seed: int
    description: str
    relation_types: list[str]
    scopes: dict[str, HeterogeneousScope]
    memories: list[HeterogeneousMemory]
    entities: list[HeterogeneousEntity]
    edges: list[HeterogeneousEdge]
    queries: list[HeterogeneousQuery]
    requirements: dict[str, Any]

    @model_validator(mode="after")
    def _validate_corpus(self) -> HeterogeneousRetrievalDataset:
        scope_names = set(self.scopes)
        memories = _unique_by("memory", self.memories, "memory_id")
        entities = _unique_by("entity", self.entities, "entity_id")
        _unique_by("edge", self.edges, "edge_id")
        _unique_by("query", self.queries, "case_id")
        if len(self.relation_types) != len(set(self.relation_types)):
            raise ValueError("relation types must be unique")
        ontology = set(self.relation_types)

        for memory in self.memories:
            if memory.scope not in scope_names:
                raise ValueError(f"{memory.memory_id}: unknown scope")
            _parse_time(memory.valid_from)
            if memory.valid_to and _parse_time(memory.valid_to) < _parse_time(
                memory.valid_from
            ):
                raise ValueError(f"{memory.memory_id}: reversed validity")
            if not memory.evidence_id or not memory.fact_key:
                raise ValueError(f"{memory.memory_id}: provenance and fact key required")
            if memory.kind == "episode" and not memory.event_key:
                raise ValueError(f"{memory.memory_id}: episode event key required")

        for entity in self.entities:
            if entity.scope not in scope_names:
                raise ValueError(f"{entity.entity_id}: unknown scope")
        for edge in self.edges:
            source = entities.get(edge.source_entity_id)
            target = entities.get(edge.target_entity_id)
            memory = memories.get(edge.memory_id)
            if source is None or target is None:
                raise ValueError(f"{edge.edge_id}: unknown endpoint")
            if (
                edge.scope not in scope_names
                or source.scope != edge.scope
                or target.scope != edge.scope
            ):
                raise ValueError(f"{edge.edge_id}: cross-scope topology")
            if memory is None or memory.scope != edge.scope:
                raise ValueError(f"{edge.edge_id}: invalid memory provenance")
            if edge.relation_type not in ontology:
                raise ValueError(f"{edge.edge_id}: relation type outside ontology")
            _parse_time(edge.valid_at)
            if edge.invalid_at and _parse_time(edge.invalid_at) < _parse_time(
                edge.valid_at
            ):
                raise ValueError(f"{edge.edge_id}: reversed validity")

        query_texts: set[str] = set()
        categories: Counter[str] = Counter()
        domains: Counter[str] = Counter()
        partitions: Counter[str] = Counter()
        queries_per_scope: Counter[str] = Counter()
        for query in self.queries:
            if query.scope not in scope_names:
                raise ValueError(f"{query.case_id}: unknown scope")
            if query.partition != self.scopes[query.scope].partition:
                raise ValueError(f"{query.case_id}: partition crosses owner scope")
            if query.query in query_texts:
                raise ValueError(f"{query.case_id}: duplicate full query text")
            query_texts.add(query.query)
            valid_at = _parse_time(query.valid_at)
            categories[query.category] += 1
            domains[query.domain] += 1
            partitions[query.partition] += 1
            queries_per_scope[query.scope] += 1
            selected_types = {
                relation_type
                for route in query.required_routes
                for step in route
                for relation_type in step.relation_types
            }
            if not selected_types.issubset(ontology):
                raise ValueError(f"{query.case_id}: route outside ontology")
            if any(not 1 <= len(route) <= 2 for route in query.required_routes):
                raise ValueError(f"{query.case_id}: path exceeds two-hop contract")
            labels = (
                query.required_memory_ids
                + query.related_memory_ids
                + query.hard_forbidden_memory_ids
            )
            if len(labels) != len(set(labels)):
                raise ValueError(f"{query.case_id}: evidence labels overlap")
            for memory_id in labels:
                memory = memories.get(memory_id)
                if memory is None or memory.scope != query.scope:
                    raise ValueError(f"{query.case_id}: invalid evidence label")
            for memory_id in query.required_memory_ids:
                memory = memories[memory_id]
                if memory.subject_id != query.subject_id:
                    raise ValueError(f"{query.case_id}: required subject mismatch")
                if not _effective(memory, valid_at):
                    raise ValueError(f"{query.case_id}: required memory not effective")
            if query.answerable != bool(query.required_memory_ids):
                raise ValueError(f"{query.case_id}: answerability mismatch")
            if query.intent == "count":
                if query.expected_count != len(query.required_memory_ids):
                    raise ValueError(f"{query.case_id}: count evidence mismatch")
            elif query.expected_count is not None:
                raise ValueError(f"{query.case_id}: lookup cannot declare count")
            if query.category in {"one_hop_relation", "two_hop_relation"}:
                expected_hops = 1 if query.category == "one_hop_relation" else 2
                if not query.required_routes or any(
                    len(route) != expected_hops for route in query.required_routes
                ):
                    raise ValueError(f"{query.case_id}: invalid relation route gold")
            elif query.required_routes:
                raise ValueError(f"{query.case_id}: nonrelation query has route gold")
            if query.category == "cross_conversation" and (
                not query.required_memory_ids
                or any(
                    memories[memory_id].conversation_id == query.conversation_id
                    for memory_id in query.required_memory_ids
                )
            ):
                raise ValueError(f"{query.case_id}: not cross-conversation")
            if query.category == "no_answer_related" and (
                query.answerable or not query.related_memory_ids
            ):
                raise ValueError(f"{query.case_id}: invalid related-only abstention")
            if query.category == "episode_count" and any(
                memories[memory_id].temporal_status != "cancelled"
                for memory_id in query.hard_forbidden_memory_ids
            ):
                raise ValueError(f"{query.case_id}: cancelled episode label required")

        memory_counts = Counter(item.scope for item in self.memories)
        if set(memory_counts) != scope_names:
            raise ValueError("every scope must contain memories")
        if set(queries_per_scope) != scope_names:
            raise ValueError("every scope must contain queries")

        minimums = self.requirements
        _require_at_least("scopes", len(self.scopes), minimums)
        _require_at_least("queries", len(self.queries), minimums)
        _require_at_least("memories", len(self.memories), minimums)
        _require_at_least(
            "memories_per_scope",
            min(memory_counts.values()),
            minimums,
        )
        _require_at_least(
            "queries_per_scope", min(queries_per_scope.values()), minimums
        )
        for category in Category.__args__:  # pyright: ignore[reportAttributeAccessIssue]
            _require_at_least(f"category_{category}", categories[category], minimums)
        for domain in (
            "residence",
            "career",
            "travel",
            "possessions",
            "documents",
            "preferences",
            "health",
        ):
            _require_at_least(f"domain_{domain}", domains[domain], minimums)
        for partition in ("dev", "sealed", "adversarial"):
            _require_at_least(
                f"partition_{partition}", partitions[partition], minimums
            )
        return self

    @property
    def fingerprint(self) -> str:
        payload = json.dumps(
            self.model_dump(mode="json"), ensure_ascii=False, sort_keys=True
        ).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()


def load_dataset(path: Path) -> HeterogeneousRetrievalDataset:
    return HeterogeneousRetrievalDataset.model_validate_json(path.read_text("utf-8"))


def _effective(memory: HeterogeneousMemory, valid_at: datetime) -> bool:
    start = _parse_time(memory.valid_from)
    end = _parse_time(memory.valid_to) if memory.valid_to else None
    return start <= valid_at and (end is None or valid_at < end)


def _unique_by(label: str, values: list[Any], field: str) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for item in values:
        key = str(getattr(item, field))
        if key in result:
            raise ValueError(f"duplicate {label}: {key}")
        result[key] = item
    return result


def _parse_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError("dataset times must include timezone")
    return parsed.astimezone(UTC)


def _require_at_least(name: str, actual: int, requirements: dict[str, Any]) -> None:
    expected = int(requirements[f"min_{name}"])
    if actual < expected:
        raise ValueError(f"dataset {name} below minimum: {actual} < {expected}")
