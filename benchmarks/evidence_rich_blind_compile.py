"""Compile accepted blind surfaces into a frozen heterogeneous retrieval corpus."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from collections import Counter
from pathlib import Path
from typing import Any

from benchmarks.build_evidence_rich_blind_manifest import build_manifest
from benchmarks.evidence_rich_blind_acquire import (
    DEFAULT_OUTPUT as DEFAULT_AUTHORED_SURFACES,
)
from benchmarks.evidence_rich_blind_acquire import MEMORY_BATCH_SIZE
from benchmarks.evidence_rich_blind_authoring import (
    MAX_AUTHORING_ATTEMPTS,
    build_authoring_request,
    split_owner_authoring_batches,
)
from benchmarks.evidence_rich_blind_review import DEFAULT_OUTPUT as DEFAULT_REVIEW
from benchmarks.heterogeneous_retrieval_quality import HeterogeneousRetrievalDataset

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "data/doppel/evidence-rich-blind-v1-corpus.json"
DEFAULT_REPORT = ROOT / "data/doppel/evidence-rich-blind-v1-compile-report.json"
OPENED_V4 = ROOT / "benchmarks/datasets/heterogeneous-retrieval-zh-v4.json"
RUNNER = "doppel.evidence-rich-blind-compile.v1"


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--compile", action="store_true")
    result.add_argument(
        "--authored-surfaces", type=Path, default=DEFAULT_AUTHORED_SURFACES
    )
    result.add_argument("--review", type=Path, default=DEFAULT_REVIEW)
    result.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    result.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    return result


def run(args: argparse.Namespace) -> int:
    manifest = build_manifest()
    plan = {
        "runner": RUNNER,
        "mode": "compile" if args.compile else "dry_run",
        "manifest_fingerprint": manifest.fingerprint,
        "authored_surfaces_path": str(args.authored_surfaces.resolve()),
        "authored_surfaces_available": args.authored_surfaces.is_file(),
        "review_path": str(args.review.resolve()),
        "review_available": args.review.is_file(),
        "owner_count": len(manifest.owners),
        "query_count": sum(len(owner.queries) for owner in manifest.owners),
        "memory_count": sum(len(owner.memories) for owner in manifest.owners),
        "external_http_enabled": False,
        "provider_calls": 0,
        "retrieval_enabled": False,
        "quality_metrics_available": False,
    }
    if not args.compile:
        print(json.dumps(plan, ensure_ascii=False, indent=2))
        return 0
    if args.output.exists() or args.report.exists():
        raise ValueError("first compile output or report already exists")

    authored = _load_json_object(args.authored_surfaces, "authored surfaces")
    review = _load_json_object(args.review, "semantic review")
    authored_sha256 = _sha256(args.authored_surfaces)
    review_sha256 = _sha256(args.review)
    _validate_authored(manifest, authored)
    _validate_review(manifest, review, authored_sha256)
    dataset = compile_corpus(manifest, authored)
    _validate_novel_surfaces(dataset)
    payload = dataset.model_dump(mode="json")
    _write_json(args.output, payload)
    query_text_counts = Counter(item.query for item in dataset.queries)
    entity_name_counts = Counter(item.name for item in dataset.entities)
    report = {
        "runner": RUNNER,
        "status": "compiled_unopened",
        "manifest_fingerprint": manifest.fingerprint,
        "authored_surfaces_sha256": authored_sha256,
        "review_sha256": review_sha256,
        "corpus_sha256": _sha256(args.output),
        "corpus_fingerprint": dataset.fingerprint,
        "owner_count": len(dataset.scopes),
        "query_count": len(dataset.queries),
        "unique_query_text_count": len(query_text_counts),
        "repeated_query_text_group_count": sum(
            count > 1 for count in query_text_counts.values()
        ),
        "maximum_query_text_repetition": max(query_text_counts.values(), default=0),
        "memory_count": len(dataset.memories),
        "entity_count": len(dataset.entities),
        "unique_entity_name_count": len(entity_name_counts),
        "repeated_entity_name_group_count": sum(
            count > 1 for count in entity_name_counts.values()
        ),
        "maximum_entity_name_repetition": max(entity_name_counts.values(), default=0),
        "edge_count": len(dataset.edges),
        "review_accepted": True,
        "retrieval_opened": False,
        "quality_metrics_available": False,
        "external_http_calls": 0,
        "provider_calls": 0,
    }
    _write_json(args.report, report)
    print(f"output: {args.output.resolve()}")
    print(f"report: {args.report.resolve()}")
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0


def compile_corpus(
    manifest: Any, authored: dict[str, Any]
) -> HeterogeneousRetrievalDataset:
    owner_surfaces = {item["owner_key"]: item for item in authored["owners"]}
    scopes: dict[str, Any] = {}
    memories: list[dict[str, Any]] = []
    entities: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    queries: list[dict[str, Any]] = []
    for owner in manifest.owners:
        surfaces = owner_surfaces[owner.owner_key]
        scopes[owner.scope] = {
            "user_id": owner.memories[0].subject_id,
            "agent_id": "doppel-evidence-rich-blind-eval",
            "partition": owner.partition,
        }
        entity_names = surfaces["entity_names_by_id"]
        entity_by_key = {item.surface_key: item for item in owner.entities}
        memory_by_key = {item.surface_key: item for item in owner.memories}
        for entity in owner.entities:
            entities.append(
                {
                    "entity_id": entity.entity_id,
                    "scope": entity.scope,
                    "name": entity_names[entity.entity_id],
                    "entity_type": entity.entity_type,
                }
            )
        for memory in owner.memories:
            memories.append(
                {
                    "memory_id": memory.memory_id,
                    "scope": memory.scope,
                    "conversation_id": memory.conversation_id,
                    "source_kind": memory.source_kind,
                    "kind": memory.kind,
                    "content": surfaces["memory_content_by_id"][memory.memory_id],
                    "subject_id": memory.subject_id,
                    "fact_key": memory.fact_key,
                    "event_key": memory.event_key,
                    "temporal_status": memory.temporal_status,
                    "valid_from": memory.valid_from,
                    "valid_to": memory.valid_to,
                    "authority": memory.authority,
                    "state": memory.state,
                    "tags": memory.tags,
                    "evidence_id": memory.evidence_id,
                }
            )
            if memory.relation_type:
                source = entity_by_key[memory.source_entity_key]
                target = entity_by_key[memory.target_entity_key]
                edges.append(
                    {
                        "edge_id": f"edge-{memory.memory_id}",
                        "scope": memory.scope,
                        "source_entity_id": source.entity_id,
                        "target_entity_id": target.entity_id,
                        "relation_type": memory.relation_type,
                        "fact": surfaces["edge_fact_by_memory_id"][memory.memory_id],
                        "memory_id": memory.memory_id,
                        "valid_at": memory.valid_from,
                        "invalid_at": memory.valid_to,
                    }
                )
        for query in owner.queries:
            entity_mentions = _entity_mentions(
                query, memory_by_key, entity_by_key, entity_names
            )
            queries.append(
                {
                    "case_id": query.case_id,
                    "partition": owner.partition,
                    "category": query.category,
                    "domain": query.domain,
                    "query_style": query.query_style,
                    "scope": query.scope,
                    "conversation_id": query.conversation_id,
                    "query": surfaces["query_text_by_case_id"][query.case_id],
                    "intent": query.intent,
                    "temporal_view": query.temporal_view,
                    "valid_at": query.valid_at,
                    "subject_id": query.subject_id,
                    "entity_mentions": entity_mentions,
                    "required_routes": [
                        [
                            {
                                "relation_types": [relation],
                                "direction": "outbound",
                            }
                            for relation in route
                        ]
                        for route in query.required_relation_routes
                    ],
                    "required_memory_ids": [
                        memory_by_key[key].memory_id
                        for key in query.required_memory_keys
                    ],
                    "related_memory_ids": [
                        memory_by_key[key].memory_id
                        for key in query.related_memory_keys
                    ],
                    "hard_forbidden_memory_ids": [
                        memory_by_key[key].memory_id
                        for key in query.hard_forbidden_memory_keys
                    ],
                    "expected_count": query.expected_count,
                    "answerable": query.answerable,
                    "oracle_search_text": "" if query.intent == "count" else None,
                    "oracle_memory_types": ["episode"]
                    if query.intent == "count"
                    else [],
                    "oracle_topic_keys": (
                        ["travel.completed"] if query.intent == "count" else []
                    ),
                }
            )
    category_counts = Counter(item["category"] for item in queries)
    domain_counts = Counter(item["domain"] for item in queries)
    partition_counts = Counter(item["partition"] for item in queries)
    requirements: dict[str, Any] = {
        "min_scopes": len(scopes),
        "min_queries": len(queries),
        "min_memories": len(memories),
        "min_memories_per_scope": 192,
        "min_queries_per_scope": 10,
        "requires_oracle_count_plan": True,
    }
    requirements.update(
        {f"min_category_{name}": count for name, count in category_counts.items()}
    )
    requirements.update(
        {
            f"min_domain_{name}": domain_counts[name]
            for name in (
                "residence",
                "career",
                "travel",
                "possessions",
                "documents",
                "preferences",
                "health",
            )
        }
    )
    requirements.update(
        {
            f"min_partition_{name}": partition_counts[name]
            for name in ("dev", "sealed", "adversarial")
        }
    )
    payload = {
        "suite": "doppel-evidence-rich-blind-zh-v1",
        "version": "1.0.0",
        "language": "zh-CN",
        "status": "frozen",
        "frozen": True,
        "publication_ready": False,
        "seed": 94720260928,
        "description": (
            "Owner-disjoint first-run synthetic corpus for rank-first versus "
            "evidence-rich personal-memory retrieval. Surfaces require independent "
            "semantic review before compilation and retrieval remains unopened."
        ),
        "relation_types": manifest.relation_types,
        "scopes": scopes,
        "memories": memories,
        "entities": entities,
        "edges": edges,
        "queries": queries,
        "requirements": requirements,
    }
    return HeterogeneousRetrievalDataset.model_validate(payload)


def _entity_mentions(
    query: Any,
    memories: dict[str, Any],
    entities: dict[str, Any],
    names: dict[str, str],
) -> list[str]:
    candidates = [*query.required_memory_keys, *query.related_memory_keys]
    for key in candidates:
        memory = memories[key]
        if memory.source_entity_key:
            entity = entities[memory.source_entity_key]
            return [names[entity.entity_id]]
    return []


def _validate_authored(manifest: Any, authored: dict[str, Any]) -> None:
    if authored.get("status") != "authored_unreviewed":
        raise ValueError("compile requires authored_unreviewed surfaces")
    if authored.get("manifest_fingerprint") != manifest.fingerprint:
        raise ValueError("authored manifest fingerprint mismatch")
    if authored.get("review_complete") is not False:
        raise ValueError("authored artifact must precede review")
    if authored.get("retrieval_opened") is not False:
        raise ValueError("authored artifact must precede retrieval")
    if authored.get("quality_metrics_available") is not False:
        raise ValueError("authored artifact must not expose retrieval metrics")
    owners = authored.get("owners")
    if not isinstance(owners, list):
        raise TypeError("authored artifact requires owners")
    actual = {str(item.get("owner_key")): item for item in owners}
    if len(actual) != len(owners) or set(actual) != {
        owner.owner_key for owner in manifest.owners
    }:
        raise ValueError("authored owner set mismatch")
    for owner in manifest.owners:
        item = actual[owner.owner_key]
        expected = {
            "entity_names_by_id": {entity.entity_id for entity in owner.entities},
            "memory_content_by_id": {memory.memory_id for memory in owner.memories},
            "edge_fact_by_memory_id": {memory.memory_id for memory in owner.memories},
            "query_text_by_case_id": {query.case_id for query in owner.queries},
        }
        for field, keys in expected.items():
            values = item.get(field)
            if not isinstance(values, dict) or set(values) != keys:
                raise ValueError(f"authored {field} set mismatch")
            if field != "edge_fact_by_memory_id" and any(
                not str(value or "").strip() for value in values.values()
            ):
                raise ValueError(f"authored {field} contains empty text")
        for memory in owner.memories:
            fact = item["edge_fact_by_memory_id"][memory.memory_id]
            if bool(str(fact or "").strip()) != bool(memory.relation_type):
                raise ValueError(
                    "authored edge fact does not match host relation shape"
                )
        for entity in owner.entities:
            required = entity.required_display_name.strip()
            if required and item["entity_names_by_id"][entity.entity_id] != required:
                raise ValueError("authored entity name violates a host requirement")
        entity_names = list(item["entity_names_by_id"].values())
        if len(entity_names) != len(set(entity_names)):
            raise ValueError("authored entity names must be unique within one owner")
        query_texts = list(item["query_text_by_case_id"].values())
        if len(query_texts) != len(set(query_texts)):
            raise ValueError("authored query text must be unique within one owner")
    shared_names: dict[str, list[str]] = {}
    for owner in manifest.owners:
        item = actual[owner.owner_key]
        for entity in owner.entities:
            if entity.shared_name_group:
                shared_names.setdefault(entity.shared_name_group, []).append(
                    item["entity_names_by_id"][entity.entity_id]
                )
    for group, names in shared_names.items():
        if len(names) < 2 or len(set(names)) != 1:
            raise ValueError(f"shared entity name group is inconsistent: {group}")
    edge_facts: list[str] = []
    for owner in manifest.owners:
        item = actual[owner.owner_key]
        edge_facts.extend(
            str(value)
            for value in item["edge_fact_by_memory_id"].values()
            if str(value).strip()
        )
    if len(edge_facts) != len(set(edge_facts)):
        raise ValueError("authored relation edge facts contain duplicate surface text")
    nonces = {
        str(
            build_authoring_request(batch, variation_attempt=attempt).input[
                "authoring_nonce"
            ]
        )
        for owner in manifest.owners
        for batch in split_owner_authoring_batches(
            owner, memory_batch_size=MEMORY_BATCH_SIZE
        )
        for attempt in range(MAX_AUTHORING_ATTEMPTS)
    }
    surfaces = [
        str(value)
        for item in owners
        for field in (
            "entity_names_by_id",
            "memory_content_by_id",
            "edge_fact_by_memory_id",
            "query_text_by_case_id",
        )
        for value in item[field].values()
    ]
    if any(nonce in surface for nonce in nonces for surface in surfaces):
        raise ValueError("authored surface exposes an internal variation nonce")


def _validate_review(
    manifest: Any, review: dict[str, Any], authored_sha256: str
) -> None:
    if (
        review.get("status") != "reviewed_accepted"
        or review.get("accepted") is not True
    ):
        raise ValueError("compile requires an accepted first semantic review")
    if review.get("review_complete") is not True or review.get("issue_count") != 0:
        raise ValueError("accepted review must be complete and issue-free")
    if review.get("manifest_fingerprint") != manifest.fingerprint:
        raise ValueError("review manifest fingerprint mismatch")
    if review.get("authored_surfaces_sha256") != authored_sha256:
        raise ValueError("review is not bound to the authored surface artifact")
    if review.get("retrieval_opened") is not False:
        raise ValueError("semantic review must precede retrieval")
    if review.get("quality_metrics_available") is not False:
        raise ValueError("semantic review must not expose retrieval metrics")
    if review.get("auto_rewrite_performed") is not False:
        raise ValueError("semantic review must not rewrite authored surfaces")
    batches = [
        batch
        for owner in manifest.owners
        for batch in split_owner_authoring_batches(
            owner, memory_batch_size=MEMORY_BATCH_SIZE
        )
    ]
    reports = review.get("batches")
    if not isinstance(reports, list):
        raise TypeError("semantic review requires batch reports")
    if review.get("batch_count") != len(batches):
        raise ValueError("semantic review batch count mismatch")
    actual = {str(item.get("batch_id")): item for item in reports}
    if len(actual) != len(reports) or set(actual) != {
        batch.batch_id for batch in batches
    }:
        raise ValueError("semantic review batch set mismatch")
    for batch in batches:
        item = actual[batch.batch_id]
        keys = sorted(
            surface.surface_key
            for surface in [*batch.entities, *batch.memories, *batch.queries]
        )
        if item.get("owner_key") != batch.owner_key:
            raise ValueError("semantic review batch owner mismatch")
        if item.get("reviewed_surface_count") != len(keys):
            raise ValueError("semantic review coverage count mismatch")
        if item.get("reviewed_surface_keys_sha256") != _fingerprint(keys):
            raise ValueError("semantic review coverage fingerprint mismatch")
        if item.get("issue_count") != 0 or item.get("issues") != []:
            raise ValueError("accepted semantic review contains issues")


def _validate_novel_surfaces(dataset: HeterogeneousRetrievalDataset) -> None:
    memory_texts = [item.content for item in dataset.memories]
    if len(memory_texts) != len(set(memory_texts)):
        raise ValueError("compiled corpus contains duplicate memory surface text")
    opened = json.loads(OPENED_V4.read_text("utf-8"))
    if set(memory_texts).intersection(item["content"] for item in opened["memories"]):
        raise ValueError("compiled memory text copies the opened V4 corpus")
    if {item.memory_id for item in dataset.memories}.intersection(
        item["memory_id"] for item in opened["memories"]
    ):
        raise ValueError("compiled memory IDs overlap the opened V4 corpus")
    if {item.entity_id for item in dataset.entities}.intersection(
        item["entity_id"] for item in opened["entities"]
    ):
        raise ValueError("compiled entity IDs overlap the opened V4 corpus")
    if {item.case_id for item in dataset.queries}.intersection(
        item["case_id"] for item in opened["queries"]
    ):
        raise ValueError("compiled case IDs overlap the opened V4 corpus")


def _load_json_object(path: Path, label: str) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(f"{label} artifact is required")
    raw = json.loads(path.read_text("utf-8"))
    if not isinstance(raw, dict):
        raise TypeError(f"{label} artifact must be an object")
    return raw


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", "utf-8"
    )
    os.replace(temporary, path)


def _fingerprint(value: Any) -> str:
    payload = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main(argv: list[str] | None = None) -> int:
    return run(parser().parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
