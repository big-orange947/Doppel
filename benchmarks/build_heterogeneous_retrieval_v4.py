"""Build the deterministic topology-adversarial heterogeneous retrieval corpus."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from benchmarks.heterogeneous_retrieval_quality import (
    HeterogeneousRetrievalDataset,
    load_dataset,
)

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "benchmarks/datasets/heterogeneous-retrieval-zh-v3.json"
OUTPUT = ROOT / "benchmarks/datasets/heterogeneous-retrieval-zh-v4.json"

PERSON_NAMES = ("周岚", "陈默", "许舟", "沈青", "顾川", "叶宁")
CITY_NAMES = ("苏州", "青岛", "昆明", "珠海", "合肥", "大连")
MAKER_NAMES = ("白塔工作室", "远山工坊", "星港设计", "松林制造")


def build_dataset() -> dict[str, Any]:
    source = load_dataset(SOURCE)
    payload = source.model_dump(mode="json")
    payload.update(
        {
            "suite": "doppel-heterogeneous-retrieval-zh-v4",
            "version": "4.0.0",
            "description": (
                "Opened V3 corpus plus topology-adversarial graph branches, cycles, "
                "competing two-hop continuations, unrelated one-hop paths, and stale "
                "edges for evaluating generic bounded exploration."
            ),
        }
    )
    payload["relation_types"].extend(
        ["LOANED_TO", "WORKS_IN", "MADE_BY", "RELATED_TO"]
    )
    entities_by_scope: dict[str, list[dict[str, Any]]] = {}
    for entity in payload["entities"]:
        entities_by_scope.setdefault(entity["scope"], []).append(entity)

    for index, (scope_name, scope) in enumerate(payload["scopes"].items(), start=1):
        stem = f"u{index:02d}"
        existing = entities_by_scope[scope_name]
        item = next(entity for entity in existing if entity["entity_type"] == "object")
        alternate_person = PERSON_NAMES[(index - 1) % len(PERSON_NAMES)]
        alternate_city = CITY_NAMES[(index - 1) % len(CITY_NAMES)]
        maker = MAKER_NAMES[(index - 1) % len(MAKER_NAMES)]
        subject_id = scope["user_id"]
        conversation_id = f"{stem}-topology-adversarial"
        entity_specs = (
            (f"e-{stem}-alternate-person", alternate_person, "person"),
            (f"e-{stem}-alternate-city", alternate_city, "place"),
            (f"e-{stem}-maker", maker, "organization"),
            (f"e-{stem}-cycle", f"{item['name']}的关联节点", "concept"),
            (f"e-{stem}-old-holder", f"旧保管人{index:02d}", "person"),
        )
        payload["entities"].extend(
            {
                "entity_id": entity_id,
                "scope": scope_name,
                "name": name,
                "entity_type": entity_type,
            }
            for entity_id, name, entity_type in entity_specs
        )

        memory_specs = (
            (
                f"m-{stem}-loaned-branch",
                f"{item['name']}曾借给{alternate_person}保管。",
                "relation:loaned-branch",
                "2024-01-01T00:00:00+08:00",
                "",
            ),
            (
                f"m-{stem}-alternate-location",
                f"{alternate_person}目前在{alternate_city}工作。",
                "relation:alternate-location",
                "2024-01-01T00:00:00+08:00",
                "",
            ),
            (
                f"m-{stem}-maker",
                f"{item['name']}由{maker}设计制作。",
                "relation:maker",
                "2024-01-01T00:00:00+08:00",
                "",
            ),
            (
                f"m-{stem}-cycle-out",
                f"{item['name']}关联到一个循环测试节点。",
                "relation:cycle-out",
                "2024-01-01T00:00:00+08:00",
                "",
            ),
            (
                f"m-{stem}-cycle-back",
                f"循环测试节点又关联回{item['name']}。",
                "relation:cycle-back",
                "2024-01-01T00:00:00+08:00",
                "",
            ),
            (
                f"m-{stem}-stale-holder",
                f"{item['name']}以前由旧保管人{index:02d}保管。",
                "relation:stale-holder",
                "2023-01-01T00:00:00+08:00",
                "2025-01-01T00:00:00+08:00",
            ),
        )
        payload["memories"].extend(
            {
                "memory_id": memory_id,
                "scope": scope_name,
                "conversation_id": conversation_id,
                "source_kind": "chat",
                "kind": "relation",
                "content": content,
                "subject_id": subject_id,
                "fact_key": fact_key,
                "event_key": "",
                "temporal_status": "historical" if valid_to else "current",
                "valid_from": valid_from,
                "valid_to": valid_to,
                "authority": "human_self",
                "state": "confirmed",
                "tags": ["personal-memory"],
                "evidence_id": f"evidence:{memory_id}",
            }
            for memory_id, content, fact_key, valid_from, valid_to in memory_specs
        )
        edge_specs = (
            (
                f"edge-{stem}-00-maker",
                item["entity_id"],
                f"e-{stem}-maker",
                "MADE_BY",
                f"{item['name']}由{maker}设计制作",
                f"m-{stem}-maker",
                "",
            ),
            (
                f"edge-{stem}-01-cycle-out",
                item["entity_id"],
                f"e-{stem}-cycle",
                "RELATED_TO",
                f"{item['name']}关联到循环节点",
                f"m-{stem}-cycle-out",
                "",
            ),
            (
                f"edge-{stem}-02-cycle-back",
                f"e-{stem}-cycle",
                item["entity_id"],
                "RELATED_TO",
                f"循环节点关联回{item['name']}",
                f"m-{stem}-cycle-back",
                "",
            ),
            (
                f"edge-{stem}-03-loaned",
                item["entity_id"],
                f"e-{stem}-alternate-person",
                "LOANED_TO",
                f"{item['name']}曾借给{alternate_person}",
                f"m-{stem}-loaned-branch",
                "",
            ),
            (
                f"edge-{stem}-04-works",
                f"e-{stem}-alternate-person",
                f"e-{stem}-alternate-city",
                "WORKS_IN",
                f"{alternate_person}在{alternate_city}工作",
                f"m-{stem}-alternate-location",
                "",
            ),
            (
                f"edge-{stem}-05-stale",
                item["entity_id"],
                f"e-{stem}-old-holder",
                "HELD_BY",
                f"{item['name']}以前由旧保管人{index:02d}保管",
                f"m-{stem}-stale-holder",
                "2025-01-01T00:00:00+08:00",
            ),
        )
        payload["edges"].extend(
            {
                "edge_id": edge_id,
                "scope": scope_name,
                "source_entity_id": source_id,
                "target_entity_id": target_id,
                "relation_type": relation_type,
                "fact": fact,
                "memory_id": memory_id,
                "valid_at": (
                    "2023-01-01T00:00:00+08:00"
                    if invalid_at
                    else "2024-01-01T00:00:00+08:00"
                ),
                "invalid_at": invalid_at,
            }
            for (
                edge_id,
                source_id,
                target_id,
                relation_type,
                fact,
                memory_id,
                invalid_at,
            ) in edge_specs
        )

        stale_id = f"m-{stem}-stale-holder"
        branch_ids = [
            f"m-{stem}-maker",
            f"m-{stem}-cycle-out",
            f"m-{stem}-loaned-branch",
            f"m-{stem}-alternate-location",
        ]
        for query in payload["queries"]:
            if query["scope"] != scope_name:
                continue
            if query["category"] in {
                "one_hop_relation",
                "two_hop_relation",
                "no_answer_related",
            }:
                query["hard_forbidden_memory_ids"].append(stale_id)
            if query["category"] == "no_answer_related":
                query["related_memory_ids"].extend(branch_ids)

    payload["requirements"]["min_memories"] = len(payload["memories"])
    payload["requirements"]["min_memories_per_scope"] = min(
        sum(memory["scope"] == scope_name for memory in payload["memories"])
        for scope_name in payload["scopes"]
    )
    return HeterogeneousRetrievalDataset.model_validate(payload).model_dump(mode="json")


def main() -> None:
    payload = build_dataset()
    OUTPUT.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", "utf-8"
    )


if __name__ == "__main__":
    main()
