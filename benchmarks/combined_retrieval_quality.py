"""Schema and invariant checks for the sealed combined retrieval corpus."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from doppel_memory.relation import RelationPathStep


class CombinedScope(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    user_id: str
    agent_id: str


class CombinedMemory(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    memory_id: str
    scope: str
    content: str
    valid_from: str
    valid_to: str = ""
    authority: Literal["human_self", "peer_statement", "agent_output"] = "human_self"
    state: Literal["candidate", "confirmed", "superseded", "expired"] = "confirmed"
    tags: list[str] = Field(default_factory=lambda: ["personal-memory"])
    evidence_id: str


class CombinedEntity(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    entity_id: str
    scope: str
    name: str


class CombinedEdge(BaseModel):
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


class CombinedQuery(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    case_id: str
    partition: Literal["sealed", "adversarial"]
    category: Literal[
        "one_hop_relation",
        "two_hop_relation",
        "semantic_nonrelation",
        "temporal_incomplete_path",
    ]
    scope: str
    query: str
    anchor: str
    entity_mentions: list[str] = Field(default_factory=list)
    valid_at: str
    required_routes: list[list[RelationPathStep]] = Field(default_factory=list)
    required_memory_ids: list[str] = Field(default_factory=list)
    related_memory_ids: list[str] = Field(default_factory=list)
    hard_forbidden_memory_ids: list[str] = Field(default_factory=list)
    answerable: bool


class CombinedRetrievalDataset(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    suite: str
    version: str
    language: Literal["zh-CN"]
    status: Literal["frozen"]
    frozen: Literal[True]
    publication_ready: Literal[False]
    seed: int
    description: str
    relation_catalog: str
    relation_types: list[str]
    scopes: dict[str, CombinedScope]
    fixtures: list[CombinedMemory]
    entities: list[CombinedEntity]
    edges: list[CombinedEdge]
    queries: list[CombinedQuery]
    requirements: dict[str, Any]

    @model_validator(mode="after")
    def _validate_corpus(self) -> CombinedRetrievalDataset:
        scope_names = set(self.scopes)
        memories = _unique_by("memory", self.fixtures, "memory_id")
        entities = _unique_by("entity", self.entities, "entity_id")
        _unique_by("edge", self.edges, "edge_id")
        _unique_by("query", self.queries, "case_id")
        if len(self.relation_types) != len(set(self.relation_types)):
            raise ValueError("relation types must be unique")
        ontology = set(self.relation_types)

        for memory in self.fixtures:
            if memory.scope not in scope_names:
                raise ValueError(f"{memory.memory_id}: unknown scope")
            _parse_time(memory.valid_from)
            if memory.valid_to and _parse_time(memory.valid_to) < _parse_time(
                memory.valid_from
            ):
                raise ValueError(f"{memory.memory_id}: reversed validity")
            if not memory.evidence_id:
                raise ValueError(f"{memory.memory_id}: evidence is required")
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
                raise ValueError(f"{edge.edge_id}: type outside ontology")
            _parse_time(edge.valid_at)
            if edge.invalid_at:
                _parse_time(edge.invalid_at)

        category_counts: Counter[str] = Counter()
        queries_per_scope: Counter[str] = Counter()
        for query in self.queries:
            if query.scope not in scope_names:
                raise ValueError(f"{query.case_id}: unknown scope")
            _parse_time(query.valid_at)
            category_counts[query.category] += 1
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
                raise ValueError(f"{query.case_id}: routes must be one or two hops")
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
            if query.answerable != bool(query.required_memory_ids):
                raise ValueError(f"{query.case_id}: answerability mismatch")
            if query.category == "semantic_nonrelation" and query.required_routes:
                raise ValueError(f"{query.case_id}: semantic query must not require path")
            if query.category != "semantic_nonrelation" and not query.required_routes:
                raise ValueError(f"{query.case_id}: relation query requires path gold")
            if query.category == "temporal_incomplete_path" and (
                query.answerable or not query.hard_forbidden_memory_ids
            ):
                raise ValueError(
                    f"{query.case_id}: incomplete path needs forbidden evidence"
                )

        minimums = self.requirements
        _require_at_least("scopes", len(self.scopes), minimums)
        _require_at_least("queries", len(self.queries), minimums)
        _require_at_least("memories", len(self.fixtures), minimums)
        _require_at_least(
            "memories_per_scope",
            min(Counter(item.scope for item in self.fixtures).values()),
            minimums,
        )
        _require_at_least(
            "queries_per_scope", min(queries_per_scope.values()), minimums
        )
        for category in (
            "one_hop_relation",
            "two_hop_relation",
            "semantic_nonrelation",
            "temporal_incomplete_path",
        ):
            _require_at_least(
                f"category_{category}", category_counts[category], minimums
            )
        return self

    @property
    def fingerprint(self) -> str:
        payload = json.dumps(
            self.model_dump(mode="json"), ensure_ascii=False, sort_keys=True
        ).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()


def load_dataset(path: Path) -> CombinedRetrievalDataset:
    return CombinedRetrievalDataset.model_validate_json(path.read_text("utf-8"))


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
