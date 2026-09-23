"""Zero-model live Neo4j ablation for exact-plus-candidate path retrieval."""

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
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

from benchmarks.personal_relation_path_ablation import (
    PathEdge,
    PathEntity,
    PathMemory,
    PathScope,
    _LiveGraphClient,
    _percentile,
    _timestamp,
)
from doppel_memory import InMemoryStore, MemoryFilter, MemoryRecord, MemoryScope
from doppel_memory.graphiti_store import (
    GraphitiRelationIndex,
    _graph_query_records,
    _graphiti_episode_name,
)
from doppel_memory.query_path import PersonalMemoryRelationPathDraftV4
from doppel_memory.relation import RelationPathStep
from doppel_memory.relation_path_retrieval import (
    CandidateRelationTopology,
    RelationPathRetrievalHit,
    RelationPathRetrievalPlan,
    build_relation_path_retrieval_plan,
    search_relation_path_routes,
)


class CandidatePathQueryCase(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    query_id: str
    partition: Literal["dev", "heldout", "adversarial"]
    category: str
    scope: str
    query: str
    entity_mentions: list[str] = Field(min_length=1)
    path_decision: Literal["execute", "abstain"]
    path_reason: Literal[
        "exact", "ambiguous", "unsupported", "over_bound", "nonrelation"
    ]
    exact_steps: list[RelationPathStep] = Field(default_factory=list, max_length=2)
    candidate_topologies: list[CandidateRelationTopology] = Field(default_factory=list)
    valid_at: str
    required_hop_memory_ids: list[list[str]]
    forbidden_memory_ids: list[str]
    candidate_noise_memory_ids: list[str]
    expected_end_entity: str = ""
    recovery_expected: bool = False
    dual_attribution_expected: bool = False
    expected_compilation: dict[
        Literal["compiled", "ambiguous", "over_bound", "duplicates"], int
    ] = Field(default_factory=dict)


class CandidatePathDataset(BaseModel):
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
    queries: list[CandidatePathQueryCase]
    requirements: dict[str, Any]

    @model_validator(mode="after")
    def _validate_references(self) -> CandidatePathDataset:
        known_scopes = set(self.scopes)
        memories = {item.memory_id: item for item in self.fixtures}
        entities = {item.entity_id: item for item in self.entities}
        ontology = set(self.relation_types)
        for label, values in (
            ("memory", [item.memory_id for item in self.fixtures]),
            ("entity", [item.entity_id for item in self.entities]),
            ("edge", [item.edge_id for item in self.edges]),
            ("query", [item.query_id for item in self.queries]),
        ):
            duplicates = sorted(
                value for value, count in Counter(values).items() if count > 1
            )
            if duplicates:
                raise ValueError(f"duplicate {label} values: {duplicates}")
        for memory in self.fixtures:
            if memory.scope not in known_scopes:
                raise ValueError(f"unknown fixture scope: {memory.scope}")
        for entity in self.entities:
            if entity.scope not in known_scopes:
                raise ValueError(f"unknown entity scope: {entity.scope}")
        for edge in self.edges:
            source = entities.get(edge.source_entity_id)
            target = entities.get(edge.target_entity_id)
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
                memory = memories.get(edge.memory_id)
                if memory is None or memory.scope != edge.scope:
                    raise ValueError(f"{edge.edge_id}: invalid memory provenance")
        for case in self.queries:
            if case.scope not in known_scopes:
                raise ValueError(f"{case.query_id}: unknown scope")
            selected = {
                relation_type
                for step in case.exact_steps
                for relation_type in step.relation_types
            } | {
                relation_type
                for topology in case.candidate_topologies
                for atom in topology.atoms
                for relation_type in atom.relation_types
            }
            if not selected.issubset(ontology):
                raise ValueError(f"{case.query_id}: type outside ontology")
            labels = (
                {item for group in case.required_hop_memory_ids for item in group}
                | set(case.forbidden_memory_ids)
                | set(case.candidate_noise_memory_ids)
            )
            for memory_id in labels:
                memory = memories.get(memory_id)
                if memory is None or memory.scope != case.scope:
                    raise ValueError(f"{case.query_id}: invalid evidence label")
            if case.path_decision == "execute" and not case.exact_steps:
                raise ValueError(f"{case.query_id}: execute requires exact steps")
            if case.path_decision == "abstain" and case.exact_steps:
                raise ValueError(f"{case.query_id}: abstain forbids exact steps")
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


def load_dataset(path: Path) -> CandidatePathDataset:
    return CandidatePathDataset.model_validate_json(path.read_text(encoding="utf-8"))


def _draft(
    case: CandidatePathQueryCase, scope: MemoryScope
) -> PersonalMemoryRelationPathDraftV4:
    valid_at = _timestamp(case.valid_at)
    return PersonalMemoryRelationPathDraftV4(
        operation="lookup",
        temporal_view="as_of",
        search_text=case.query,
        entity_mentions=case.entity_mentions,
        subject="owner",
        subject_id=scope.user_id,
        as_of=valid_at,
        path_decision=case.path_decision,
        path_reason=case.path_reason,
        path_steps=case.exact_steps,
        path_confidence=0.9 if case.path_decision == "execute" else 0,
    )


def _profile_plan(
    plan: RelationPathRetrievalPlan, mode: Literal["exact", "candidate", "union"]
) -> RelationPathRetrievalPlan:
    routes = plan.routes
    if mode != "union":
        routes = [route for route in routes if route.mode == mode]
    return plan.model_copy(update={"routes": routes})


def _hit_key(hit: RelationPathRetrievalHit) -> tuple[str, tuple[str, ...]]:
    return (
        hit.candidate.scope.scope_key,
        tuple(hop.edge_id for hop in hit.candidate.hops),
    )


async def run_ablation(
    dataset: CandidatePathDataset,
    *,
    uri: str,
    user: str,
    password: str,
) -> dict[str, Any]:
    from neo4j import AsyncGraphDatabase  # pyright: ignore[reportMissingImports]

    run_id = f"doppel-candidate-path-{uuid4().hex}"
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
    relation = GraphitiRelationIndex(store, graphiti_client=_LiveGraphClient(driver))
    memory_by_id: dict[str, MemoryRecord] = {}
    groups = [scope.scope_key for scope in scope_by_name.values()]
    cleaned = False
    fixture_write_attempted = False
    cleanup_errors: list[str] = []
    compilation_failures: list[str] = []
    compilation_totals: Counter[str] = Counter()
    profile_rows: dict[str, list[dict[str, Any]]] = {
        "strict_path": [],
        "candidate_path": [],
        "exact_candidate_union": [],
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
                            item.memory_id, "c" * 64, record.version
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
            plan = build_relation_path_retrieval_plan(
                _draft(case, scope),
                candidate_topologies=case.candidate_topologies,
                allowed_relation_types=dataset.relation_types,
            )
            actual_compilation = plan.compilation.model_dump()
            compilation_totals.update(actual_compilation)
            for field, expected in case.expected_compilation.items():
                if actual_compilation[field] != expected:
                    compilation_failures.append(
                        f"{case.query_id}:{field}:{actual_compilation[field]}!={expected}"
                    )
            for profile, mode in (
                ("strict_path", "exact"),
                ("candidate_path", "candidate"),
                ("exact_candidate_union", "union"),
            ):
                selected_plan = _profile_plan(plan, mode)  # type: ignore[arg-type]
                started = time.perf_counter()
                hits = await search_relation_path_routes(
                    relation,
                    selected_plan,
                    [scope],
                    filters=MemoryFilter(tags={"personal-memory"}),
                    limit=20,
                )
                latency = (time.perf_counter() - started) * 1000
                memory_ids = list(
                    dict.fromkeys(
                        memory_id
                        for hit in hits
                        for memory_id in hit.candidate.supporting_memory_ids
                    )
                )
                both_attributed = any(
                    {"exact", "candidate"}.issubset(set(hit.route_modes))
                    and bool(
                        set(hit.candidate.supporting_memory_ids)
                        & {
                            item
                            for group in case.required_hop_memory_ids
                            for item in group
                        }
                    )
                    for hit in hits
                )
                profile_rows[profile].append(
                    {
                        "query_id": case.query_id,
                        "category": case.category,
                        "partition": case.partition,
                        "memory_ids": memory_ids,
                        "required_hop_memory_ids": case.required_hop_memory_ids,
                        "forbidden_memory_ids": case.forbidden_memory_ids,
                        "candidate_noise_memory_ids": case.candidate_noise_memory_ids,
                        "authorized_scope_key": scope.scope_key,
                        "scope_keys": [hit.candidate.scope.scope_key for hit in hits],
                        "path_endpoints": [
                            hit.candidate.end_entity_name for hit in hits
                        ],
                        "expected_end_entity": case.expected_end_entity,
                        "recovery_expected": case.recovery_expected,
                        "dual_attribution_expected": (
                            case.dual_attribution_expected
                            and profile == "exact_candidate_union"
                        ),
                        "both_attributed": both_attributed,
                        "dedupe_ok": len({_hit_key(hit) for hit in hits}) == len(hits),
                        "graph_route_queries": len(selected_plan.routes),
                        "latency_ms": latency,
                    }
                )
    finally:
        try:
            if fixture_write_attempted:
                try:
                    await driver.execute_query(
                        "MATCH (node) WHERE node.group_id IN $groups DETACH DELETE node",
                        groups=groups,
                    )
                    raw = await driver.execute_query(
                        "MATCH (node) WHERE node.group_id IN $groups "
                        "RETURN count(node) AS remaining",
                        groups=groups,
                    )
                    rows = _graph_query_records(raw)
                    cleaned = bool(rows and int(rows[0]["remaining"] or 0) == 0)
                except Exception as exc:  # noqa: BLE001
                    cleanup_errors.append(type(exc).__name__)
            else:
                cleaned = True
        finally:
            try:
                await driver.close()
            except Exception as exc:  # noqa: BLE001
                cleanup_errors.append(f"close:{type(exc).__name__}")

    profiles = {name: _summarize_profile(rows) for name, rows in profile_rows.items()}
    strict = profiles["strict_path"]
    union = profiles["exact_candidate_union"]
    required_recovery = float(dataset.requirements["candidate_recovery_rate"])
    gate_failures: list[str] = []
    for label, value in (
        ("union_missing_required_evidence", union["missing_required_evidence"]),
        ("forbidden_hits", union["forbidden_hits"]),
        ("scope_leakage", union["scope_leakage"]),
        ("deduplication_failures", union["deduplication_failures"]),
        ("dual_attribution_failures", union["dual_attribution_failures"]),
        ("compilation_failures", len(compilation_failures)),
    ):
        if value:
            gate_failures.append(label)
    if union["recovery_rate"] < required_recovery:
        gate_failures.append("candidate_recovery_rate")
    if not cleaned:
        gate_failures.append("fixture_cleanup")

    return {
        "result_schema_version": 2,
        "runner": "doppel.candidate-relation-path-ablation.v2",
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
        "candidate_gain": {
            "evidence_recall": round(
                union["evidence_recall"] - strict["evidence_recall"], 6
            ),
            "complete_evidence_rate": round(
                union["complete_evidence_rate"] - strict["complete_evidence_rate"],
                6,
            ),
            "average_candidates": round(
                union["average_candidates"] - strict["average_candidates"], 6
            ),
            "candidate_noise_hits": union["candidate_noise_hits"]
            - strict["candidate_noise_hits"],
        },
        "compilation": {
            field: compilation_totals[field]
            for field in (
                "observations",
                "compiled",
                "ambiguous",
                "over_bound",
                "duplicates",
            )
        },
        "compilation_failures": compilation_failures,
        "gate": {"ok": not gate_failures, "failures": gate_failures},
    }


def _summarize_profile(rows: list[dict[str, Any]]) -> dict[str, Any]:
    required_total = required_found = answerable = complete = 0
    missing_required = forbidden_hits = candidate_noise_hits = scope_leakage = 0
    recovery_cases = recovered_cases = dual_cases = dual_failures = dedupe_failures = 0
    graph_route_queries = 0
    latencies: list[float] = []
    details: list[dict[str, Any]] = []
    for row in rows:
        expected = {item for group in row["required_hop_memory_ids"] for item in group}
        actual = set(row["memory_ids"])
        forbidden = set(row["forbidden_memory_ids"])
        noise = set(row["candidate_noise_memory_ids"])
        required_total += len(expected)
        required_found += len(expected & actual)
        if expected:
            answerable += 1
            complete += int(expected.issubset(actual))
        missing_required += len(expected - actual)
        forbidden_hits += len(forbidden & actual)
        candidate_noise_hits += len(noise & actual)
        scope_leakage += sum(
            scope_key != row["authorized_scope_key"] for scope_key in row["scope_keys"]
        )
        if row["recovery_expected"]:
            recovery_cases += 1
            recovered_cases += int(expected.issubset(actual))
        if row["dual_attribution_expected"] and not row["both_attributed"]:
            dual_failures += 1
        dual_cases += int(row["dual_attribution_expected"])
        dedupe_failures += int(not row["dedupe_ok"])
        graph_route_queries += int(row["graph_route_queries"])
        latencies.append(float(row["latency_ms"]))
        details.append(
            {
                "query_id": row["query_id"],
                "memory_ids": row["memory_ids"],
                "missing_required": sorted(expected - actual),
                "forbidden_hits": sorted(forbidden & actual),
                "candidate_noise_hits": sorted(noise & actual),
                "both_attributed": row["both_attributed"],
            }
        )
    return {
        "queries": len(rows),
        "evidence_recall": round(required_found / required_total, 6),
        "complete_evidence_rate": round(complete / answerable, 6),
        "missing_required_evidence": missing_required,
        "forbidden_hits": forbidden_hits,
        "candidate_noise_hits": candidate_noise_hits,
        "scope_leakage": scope_leakage,
        "recovery_cases": recovery_cases,
        "recovered_cases": recovered_cases,
        "recovery_rate": round(recovered_cases / recovery_cases, 6)
        if recovery_cases
        else 1.0,
        "dual_attribution_cases": dual_cases,
        "dual_attribution_failures": dual_failures,
        "deduplication_failures": dedupe_failures,
        "graph_route_queries": graph_route_queries,
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
    except Exception as exc:  # noqa: BLE001
        report = {
            "result_schema_version": 2,
            "runner": "doppel.candidate-relation-path-ablation.v2",
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
        default=Path("benchmarks/datasets/candidate-relation-path-ablation-zh-v2.json"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/doppel/candidate-relation-path-ablation.json"),
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
