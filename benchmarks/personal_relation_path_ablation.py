"""Zero-model live Neo4j ablation for bounded typed relation paths."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import statistics
import time
from collections import Counter
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

from doppel_memory import InMemoryStore, MemoryFilter, MemoryRecord, MemoryScope
from doppel_memory.graphiti_store import (
    GraphitiRelationIndex,
    _graph_query_records,
    _graphiti_episode_name,
)
from doppel_memory.relation import RelationPathQuery, RelationPathStep, RelationQuery


class PathScope(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    user_id: str
    agent_id: str


class PathMemory(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    memory_id: str
    scope: str
    content: str
    valid_from: str = ""
    valid_to: str = ""


class PathEntity(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    entity_id: str
    scope: str
    name: str


class PathEdge(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    edge_id: str
    scope: str
    source_entity_id: str
    target_entity_id: str
    relation_type: str
    fact: str
    memory_id: str = ""
    valid_at: str = ""
    invalid_at: str = ""


class PathQueryCase(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    query_id: str
    partition: Literal["dev", "heldout", "adversarial"]
    category: str
    scope: str
    query: str
    entity_mentions: list[str] = Field(min_length=1)
    steps: list[RelationPathStep] = Field(min_length=1, max_length=2)
    valid_at: str
    required_hop_memory_ids: list[list[str]]
    forbidden_memory_ids: list[str]
    expected_end_entity: str = ""
    expected_path_count: int = Field(ge=0, le=10)


class PathDataset(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    suite: str
    suite_version: str
    language: str
    status: str
    frozen: bool
    publication_ready: bool
    description: str
    relation_types: list[str]
    scopes: dict[str, PathScope]
    fixtures: list[PathMemory]
    entities: list[PathEntity]
    edges: list[PathEdge]
    queries: list[PathQueryCase]
    requirements: dict[str, Any]

    @model_validator(mode="after")
    def _validate_references(self) -> PathDataset:
        known_scopes = set(self.scopes)
        memory_by_id = {item.memory_id: item for item in self.fixtures}
        entity_by_id = {item.entity_id: item for item in self.entities}
        for label, values in (
            ("memory", [item.memory_id for item in self.fixtures]),
            ("entity", [item.entity_id for item in self.entities]),
            ("edge", [item.edge_id for item in self.edges]),
            ("query", [item.query_id for item in self.queries]),
            (
                "scope/query",
                [f"{item.scope}\u0000{item.query}" for item in self.queries],
            ),
        ):
            duplicates = sorted(
                value for value, count in Counter(values).items() if count > 1
            )
            if duplicates:
                raise ValueError(f"duplicate {label} values: {duplicates}")
        ontology = set(self.relation_types)
        for item in self.fixtures:
            if item.scope not in known_scopes:
                raise ValueError(f"unknown fixture scope: {item.scope}")
        for entity in self.entities:
            if entity.scope not in known_scopes:
                raise ValueError(f"unknown entity scope: {entity.scope}")
        for edge in self.edges:
            source = entity_by_id.get(edge.source_entity_id)
            target = entity_by_id.get(edge.target_entity_id)
            if source is None or target is None:
                raise ValueError(f"{edge.edge_id}: unknown endpoint")
            if (
                edge.scope not in known_scopes
                or source.scope != edge.scope
                or target.scope != edge.scope
            ):
                raise ValueError(f"{edge.edge_id}: cross-scope topology")
            if edge.relation_type not in ontology:
                raise ValueError(f"{edge.edge_id}: type outside ontology")
            if edge.memory_id:
                memory = memory_by_id.get(edge.memory_id)
                if memory is None or memory.scope != edge.scope:
                    raise ValueError(f"{edge.edge_id}: invalid memory provenance")
        for query in self.queries:
            if query.scope not in known_scopes:
                raise ValueError(f"{query.query_id}: unknown scope")
            for step in query.steps:
                if not set(step.relation_types).issubset(ontology):
                    raise ValueError(f"{query.query_id}: type outside ontology")
            for memory_id in {
                value for hop in query.required_hop_memory_ids for value in hop
            } | set(query.forbidden_memory_ids):
                memory = memory_by_id.get(memory_id)
                if memory is None or memory.scope != query.scope:
                    raise ValueError(f"{query.query_id}: invalid evidence label")
            if query.required_hop_memory_ids and len(
                query.required_hop_memory_ids
            ) != len(query.steps):
                raise ValueError(f"{query.query_id}: hop evidence shape mismatch")
        if len(self.queries) < int(self.requirements.get("min_queries", 0)):
            raise ValueError("dataset does not meet min_queries")
        if len(self.scopes) < int(self.requirements.get("min_scopes", 0)):
            raise ValueError("dataset does not meet min_scopes")
        return self

    @property
    def fingerprint(self) -> str:
        payload = json.dumps(
            self.model_dump(mode="json"), ensure_ascii=False, sort_keys=True
        ).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()


class _LiveGraphClient:
    def __init__(self, driver: Any) -> None:
        self.driver = driver

    async def get_episodes_by_uuids(self, episode_ids: list[str]) -> list[Any]:
        raw = await self.driver.execute_query(
            "MATCH (episode) WHERE episode.uuid IN $episode_ids "
            "RETURN episode.uuid AS uuid, episode.name AS name, "
            "episode.group_id AS group_id",
            episode_ids=episode_ids,
        )
        return [
            SimpleNamespace(
                uuid=str(row["uuid"] or ""),
                name=str(row["name"] or ""),
                group_id=str(row["group_id"] or ""),
            )
            for row in _graph_query_records(raw)
        ]


def load_dataset(path: Path) -> PathDataset:
    return PathDataset.model_validate_json(path.read_text(encoding="utf-8"))


def _timestamp(value: str) -> Any:
    from datetime import datetime

    return datetime.fromisoformat(value) if value else None


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = round((len(ordered) - 1) * percentile)
    return round(ordered[index], 3)


async def run_ablation(
    dataset: PathDataset,
    *,
    uri: str,
    user: str,
    password: str,
) -> dict[str, Any]:
    from neo4j import AsyncGraphDatabase

    run_id = f"doppel-path-ablation-{uuid4().hex}"
    driver = AsyncGraphDatabase.driver(
        uri,
        auth=(user, password),
        connection_timeout=3.0,
        connection_acquisition_timeout=3.0,
        max_transaction_retry_time=0.0,
    )
    store = InMemoryStore()
    scope_by_name = {
        name: MemoryScope(user_id=f"{scope.user_id}:{run_id}", agent_id=scope.agent_id)
        for name, scope in dataset.scopes.items()
    }
    graph = _LiveGraphClient(driver)
    relation = GraphitiRelationIndex(store, graphiti_client=graph)
    memory_by_id: dict[str, MemoryRecord] = {}
    groups = [scope.scope_key for scope in scope_by_name.values()]
    cleaned = False
    fixture_write_attempted = False
    cleanup_errors: list[str] = []
    profile_rows: dict[str, list[dict[str, Any]]] = {
        "typed_one_hop": [],
        "typed_bounded_path": [],
        "typed_one_hop_path_union": [],
    }
    try:
        await driver.verify_connectivity()
        for item in dataset.fixtures:
            metadata: dict[str, Any] = {
                "subject": "owner",
                "subject_id": scope_by_name[item.scope].user_id,
                "evidence": [{"evidence_id": f"dataset:{item.memory_id}"}],
            }
            if item.valid_from:
                metadata["valid_from"] = item.valid_from
            if item.valid_to:
                metadata["valid_to"] = item.valid_to
            record = MemoryRecord(
                memory_id=item.memory_id,
                scope=scope_by_name[item.scope],
                content=item.content,
                tags=["personal-memory"],
                metadata=metadata,
            )
            assert (await store.put(record)).accepted
            memory_by_id[item.memory_id] = record
        nodes = [
            {
                "uuid": f"{run_id}:{item.entity_id}",
                "name": item.name,
                "group_id": scope_by_name[item.scope].scope_key,
            }
            for item in dataset.entities
        ]
        episodes = []
        edges = []
        for item in dataset.edges:
            episode_id = f"{run_id}:episode:{item.edge_id}"
            if item.memory_id:
                record = memory_by_id[item.memory_id]
                episodes.append(
                    {
                        "uuid": episode_id,
                        "name": _graphiti_episode_name(
                            item.memory_id, "b" * 64, record.version
                        ),
                        "group_id": record.scope.scope_key,
                    }
                )
            edges.append(
                {
                    "source_uuid": f"{run_id}:{item.source_entity_id}",
                    "target_uuid": f"{run_id}:{item.target_entity_id}",
                    "group_id": scope_by_name[item.scope].scope_key,
                    "uuid": f"{run_id}:{item.edge_id}",
                    "name": item.relation_type,
                    "fact": item.fact,
                    "episodes": [episode_id],
                    "valid_at": _timestamp(item.valid_at),
                    "invalid_at": _timestamp(item.invalid_at),
                    "created_at": _timestamp(item.valid_at),
                }
            )
        fixture_write_attempted = True
        await driver.execute_query(
            "UNWIND $nodes AS item CREATE (:Entity {uuid: item.uuid, "
            "name: item.name, group_id: item.group_id})",
            nodes=nodes,
        )
        await driver.execute_query(
            "UNWIND $episodes AS item CREATE (:Episodic {uuid: item.uuid, "
            "name: item.name, group_id: item.group_id})",
            episodes=episodes,
        )
        await driver.execute_query(
            "UNWIND $edges AS item "
            "MATCH (source:Entity {uuid: item.source_uuid, group_id: item.group_id}) "
            "MATCH (target:Entity {uuid: item.target_uuid, group_id: item.group_id}) "
            "CREATE (source)-[edge:RELATES_TO]->(target) "
            "SET edge.group_id = item.group_id, edge.uuid = item.uuid, "
            "edge.name = item.name, edge.fact = item.fact, "
            "edge.episodes = item.episodes, edge.valid_at = item.valid_at, "
            "edge.invalid_at = item.invalid_at, edge.created_at = item.created_at",
            edges=edges,
        )
        for case in dataset.queries:
            scope = scope_by_name[case.scope]
            valid_at = _timestamp(case.valid_at)
            started = time.perf_counter()
            one_hop_candidates = await relation.search_relations(
                RelationQuery(
                    query_text=case.query,
                    entity_mentions=case.entity_mentions,
                    relation_types=case.steps[0].relation_types,
                    subject="owner",
                    subject_id=scope.user_id,
                    valid_at=valid_at,
                ),
                [scope],
                filters=MemoryFilter(tags={"personal-memory"}),
                limit=20,
            )
            one_hop_latency = (time.perf_counter() - started) * 1000
            started = time.perf_counter()
            path_candidates = await relation.search_relation_paths(
                RelationPathQuery(
                    query_text=case.query,
                    entity_mentions=case.entity_mentions,
                    steps=case.steps,
                    subject="owner",
                    subject_id=scope.user_id,
                    valid_at=valid_at,
                ),
                [scope],
                filters=MemoryFilter(tags={"personal-memory"}),
                limit=20,
            )
            path_latency = (time.perf_counter() - started) * 1000
            one_ids = list(dict.fromkeys(item.memory_id for item in one_hop_candidates))
            path_ids = list(
                dict.fromkeys(
                    memory_id
                    for candidate in path_candidates
                    for memory_id in candidate.supporting_memory_ids
                )
            )
            endpoints = list(
                dict.fromkeys(item.end_entity_name for item in path_candidates)
            )
            common = {
                "query_id": case.query_id,
                "authorized_scope_key": scope.scope_key,
                "required_hop_memory_ids": case.required_hop_memory_ids,
                "forbidden_memory_ids": case.forbidden_memory_ids,
                "expected_end_entity": case.expected_end_entity,
                "expected_path_count": case.expected_path_count,
                "actual_path_count": len(path_candidates),
                "path_endpoints": endpoints,
                "category": case.category,
                "partition": case.partition,
            }
            profile_rows["typed_one_hop"].append(
                {
                    **common,
                    "memory_ids": one_ids,
                    "scope_keys": [item.scope.scope_key for item in one_hop_candidates],
                    "latency_ms": one_hop_latency,
                }
            )
            profile_rows["typed_bounded_path"].append(
                {
                    **common,
                    "memory_ids": path_ids,
                    "scope_keys": [item.scope.scope_key for item in path_candidates],
                    "latency_ms": path_latency,
                }
            )
            profile_rows["typed_one_hop_path_union"].append(
                {
                    **common,
                    "memory_ids": list(dict.fromkeys([*one_ids, *path_ids])),
                    "scope_keys": list(
                        dict.fromkeys(
                            item.scope.scope_key
                            for item in [*one_hop_candidates, *path_candidates]
                        )
                    ),
                    "latency_ms": one_hop_latency + path_latency,
                }
            )
    finally:
        try:
            if fixture_write_attempted:
                try:
                    await driver.execute_query(
                        "MATCH (node) WHERE node.group_id IN $groups "
                        "DETACH DELETE node",
                        groups=groups,
                    )
                    raw = await driver.execute_query(
                        "MATCH (node) WHERE node.group_id IN $groups "
                        "RETURN count(node) AS remaining",
                        groups=groups,
                    )
                    rows = _graph_query_records(raw)
                    cleaned = bool(rows and int(rows[0]["remaining"] or 0) == 0)
                except Exception as exc:  # noqa: BLE001 - preserve primary failure
                    cleanup_errors.append(type(exc).__name__)
            else:
                cleaned = True
        finally:
            try:
                await driver.close()
            except Exception as exc:  # noqa: BLE001 - preserve primary failure
                cleanup_errors.append(f"close:{type(exc).__name__}")

    profiles = {
        name: _summarize_profile(rows, includes_path=name != "typed_one_hop")
        for name, rows in profile_rows.items()
    }
    path_metrics = profiles["typed_bounded_path"]
    one_metrics = profiles["typed_one_hop"]
    gate_failures = [
        label
        for label, value in (
            ("missing_required_evidence", path_metrics["missing_required_evidence"]),
            ("forbidden_hits", path_metrics["forbidden_hits"]),
            ("scope_leakage", path_metrics["scope_leakage"]),
            ("path_count_failures", path_metrics["path_count_failures"]),
            ("endpoint_failures", path_metrics["endpoint_failures"]),
        )
        if value
    ]
    if not cleaned:
        gate_failures.append("fixture_cleanup")
    return {
        "runner": "doppel.personal-relation-path-ablation.v1",
        "dataset": {
            "suite": dataset.suite,
            "version": dataset.suite_version,
            "fingerprint": dataset.fingerprint,
            "queries": len(dataset.queries),
            "scopes": len(dataset.scopes),
            "memories": len(dataset.fixtures),
            "edges": len(dataset.edges),
            "frozen": dataset.frozen,
            "publication_ready": dataset.publication_ready,
        },
        "runtime": {
            "backend": "neo4j",
            "llm_calls": 0,
            "external_http_calls": 0,
            "provider_tokens": 0,
            "credentials_persisted": False,
            "fixture_cleanup_performed": cleaned,
            "cleanup_errors": cleanup_errors,
        },
        "profiles": profiles,
        "bounded_path_gain": {
            "evidence_recall": round(
                path_metrics["evidence_recall"] - one_metrics["evidence_recall"], 6
            ),
            "complete_evidence_rate": round(
                path_metrics["complete_evidence_rate"]
                - one_metrics["complete_evidence_rate"],
                6,
            ),
        },
        "gate": {"ok": not gate_failures, "failures": gate_failures},
    }


def _summarize_profile(
    rows: list[dict[str, Any]], *, includes_path: bool
) -> dict[str, Any]:
    required_total = 0
    required_found = 0
    complete_cases = 0
    answerable_cases = 0
    missing_required = 0
    forbidden_hits = 0
    scope_leakage = 0
    path_count_failures = 0
    endpoint_failures = 0
    latencies = []
    details = []
    for row in rows:
        expected = {value for hop in row["required_hop_memory_ids"] for value in hop}
        actual = set(row["memory_ids"])
        forbidden = set(row["forbidden_memory_ids"])
        required_total += len(expected)
        required_found += len(expected & actual)
        if expected:
            answerable_cases += 1
            if expected.issubset(actual):
                complete_cases += 1
            else:
                missing_required += len(expected - actual)
        forbidden_hits += len(forbidden & actual)
        scope_leakage += sum(
            scope_key != row["authorized_scope_key"] for scope_key in row["scope_keys"]
        )
        path_count_ok = row["actual_path_count"] == row["expected_path_count"]
        endpoint_ok = (
            not row["expected_end_entity"]
            or row["expected_end_entity"] in row["path_endpoints"]
        )
        if includes_path:
            path_count_failures += int(not path_count_ok)
            endpoint_failures += int(not endpoint_ok)
        latencies.append(float(row["latency_ms"]))
        details.append(
            {
                "query_id": row["query_id"],
                "memory_ids": row["memory_ids"],
                "missing_required": sorted(expected - actual),
                "forbidden_hits": sorted(forbidden & actual),
                "path_count_ok": path_count_ok if includes_path else None,
                "endpoint_ok": endpoint_ok if includes_path else None,
            }
        )
    return {
        "queries": len(rows),
        "evidence_recall": round(required_found / required_total, 6),
        "complete_evidence_rate": round(complete_cases / answerable_cases, 6),
        "missing_required_evidence": missing_required,
        "forbidden_hits": forbidden_hits,
        "scope_leakage": scope_leakage,
        "path_count_failures": path_count_failures if includes_path else None,
        "endpoint_failures": endpoint_failures if includes_path else None,
        "average_candidates": round(
            statistics.mean(len(row["memory_ids"]) for row in rows), 6
        ),
        "latency_ms": {
            "p50": _percentile(latencies, 0.5),
            "p95": _percentile(latencies, 0.95),
        },
        "details": details,
    }


async def _main_async(args: argparse.Namespace) -> int:
    dataset = load_dataset(args.dataset)
    password = os.environ.get(args.password_env, "")
    if not password:
        raise RuntimeError(f"{args.password_env} is required")
    try:
        report = await run_ablation(
            dataset, uri=args.neo4j_uri, user=args.neo4j_user, password=password
        )
    except Exception as exc:  # noqa: BLE001 - benchmark emits a safe failure artifact
        report = {
            "runner": "doppel.personal-relation-path-ablation.v1",
            "dataset": {
                "suite": dataset.suite,
                "version": dataset.suite_version,
                "fingerprint": dataset.fingerprint,
            },
            "runtime": {
                "backend": "neo4j",
                "llm_calls": 0,
                "external_http_calls": 0,
                "provider_tokens": 0,
                "credentials_persisted": False,
            },
            "hard_failure": type(exc).__name__,
            "gate": {"ok": False, "failures": ["runtime_unavailable"]},
        }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["gate"]["ok"] else 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--dataset",
        type=Path,
        default=Path("benchmarks/datasets/personal-relation-path-ablation-zh-v1.json"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/doppel/personal-relation-path-ablation.json"),
    )
    parser.add_argument(
        "--neo4j-uri",
        default=os.environ.get("DOPPEL_NEO4J_URI", "bolt://127.0.0.1:7687"),
    )
    parser.add_argument(
        "--neo4j-user", default=os.environ.get("DOPPEL_NEO4J_USER", "neo4j")
    )
    parser.add_argument("--password-env", default="DOPPEL_NEO4J_PASSWORD")
    return asyncio.run(_main_async(parser.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
