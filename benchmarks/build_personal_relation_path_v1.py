"""Build the deterministic draft dataset for bounded typed relation paths."""

from __future__ import annotations

import json
from pathlib import Path

DOMAINS = (
    (
        "camera-a",
        "dev",
        "相机",
        "小王",
        "上海",
        "HELD_BY",
        "LOCATED_AT",
        "相机由小王保管。",
        "小王目前住在上海。",
    ),
    (
        "camera-b",
        "heldout",
        "相机",
        "阿宁",
        "杭州",
        "HELD_BY",
        "LOCATED_AT",
        "相机由阿宁保管。",
        "阿宁目前住在杭州。",
    ),
    (
        "document",
        "dev",
        "租房合同",
        "林老师",
        "lin@example.test",
        "PROVIDED_BY",
        "CONTACTABLE_AT",
        "租房合同由林老师提供。",
        "林老师的联系邮箱是 lin@example.test。",
    ),
    (
        "pet",
        "heldout",
        "豆包",
        "陈姨",
        "苏州",
        "CARED_FOR_BY",
        "LOCATED_AT",
        "豆包临时由陈姨照看。",
        "陈姨目前住在苏州。",
    ),
    (
        "device",
        "dev",
        "徕卡相机",
        "星海维修",
        "徐汇区",
        "REPAIRED_BY",
        "LOCATED_AT",
        "徕卡相机由星海维修处理。",
        "星海维修位于徐汇区。",
    ),
    (
        "key",
        "heldout",
        "备用钥匙",
        "表姐",
        "创意园",
        "HELD_BY",
        "WORKS_AT",
        "备用钥匙交给表姐保管。",
        "表姐目前在创意园工作。",
    ),
    (
        "package",
        "adversarial",
        "快递",
        "物业前台",
        "一楼大厅",
        "RECEIVED_BY",
        "LOCATED_AT",
        "快递由物业前台代收。",
        "物业前台位于一楼大厅。",
    ),
    (
        "painting",
        "adversarial",
        "旧画",
        "周师傅",
        "东湖仓库",
        "RESTORED_BY",
        "WORKS_AT",
        "旧画由周师傅修复。",
        "周师傅目前在东湖仓库工作。",
    ),
)


def build_dataset() -> dict[str, object]:
    scopes: dict[str, dict[str, str]] = {}
    fixtures: list[dict[str, object]] = []
    entities: list[dict[str, str]] = []
    edges: list[dict[str, object]] = []
    queries: list[dict[str, object]] = []
    relation_types: set[str] = set()
    for index, domain in enumerate(DOMAINS, start=1):
        (
            name,
            partition,
            anchor,
            middle,
            endpoint,
            first_type,
            second_type,
            first_content,
            second_content,
        ) = domain
        scope_name = f"s{index:02d}"
        scopes[scope_name] = {
            "user_id": f"path-owner-{index:02d}",
            "agent_id": "path-benchmark",
        }
        relation_types.update((first_type, second_type))
        memory_one = f"m-{name}-1"
        memory_two = f"m-{name}-2"
        valid_two = (
            "2026-07-01T00:00:00+00:00"
            if name == "pet"
            else "2026-01-01T00:00:00+00:00"
        )
        fixtures.extend(
            (
                {
                    "memory_id": memory_one,
                    "scope": scope_name,
                    "content": first_content,
                    "valid_from": "2026-01-01T00:00:00+00:00",
                    "valid_to": "",
                },
                {
                    "memory_id": memory_two,
                    "scope": scope_name,
                    "content": second_content,
                    "valid_from": valid_two,
                    "valid_to": "",
                },
            )
        )
        entity_ids = [f"e-{name}-anchor", f"e-{name}-middle", f"e-{name}-end"]
        entities.extend(
            {
                "entity_id": entity_id,
                "scope": scope_name,
                "name": entity_name,
            }
            for entity_id, entity_name in zip(
                entity_ids, (anchor, middle, endpoint), strict=True
            )
        )
        edges.extend(
            (
                {
                    "edge_id": f"edge-{name}-1",
                    "scope": scope_name,
                    "source_entity_id": entity_ids[0],
                    "target_entity_id": entity_ids[1],
                    "relation_type": first_type,
                    "fact": first_content,
                    "memory_id": memory_one,
                    "valid_at": "2026-01-01T00:00:00+00:00",
                    "invalid_at": "",
                },
                {
                    "edge_id": f"edge-{name}-2",
                    "scope": scope_name,
                    "source_entity_id": entity_ids[1],
                    "target_entity_id": entity_ids[2],
                    "relation_type": second_type,
                    "fact": second_content,
                    "memory_id": memory_two,
                    "valid_at": valid_two,
                    "invalid_at": "",
                },
            )
        )
        steps = [
            {"relation_types": [first_type], "direction": "outbound"},
            {"relation_types": [second_type], "direction": "outbound"},
        ]
        queries.extend(
            (
                {
                    "query_id": f"q-{name}-two-hop",
                    "partition": partition,
                    "category": "two_hop_answerable",
                    "scope": scope_name,
                    "query": f"{anchor}现在最终在哪里？",
                    "entity_mentions": [anchor],
                    "steps": steps,
                    "valid_at": "2026-08-01T00:00:00+00:00",
                    "required_hop_memory_ids": [[memory_one], [memory_two]],
                    "forbidden_memory_ids": [],
                    "expected_end_entity": endpoint,
                    "expected_path_count": 1,
                },
                {
                    "query_id": f"q-{name}-one-hop",
                    "partition": partition,
                    "category": "one_hop_control",
                    "scope": scope_name,
                    "query": f"{anchor}直接关联的是谁或哪里？",
                    "entity_mentions": [anchor],
                    "steps": steps[:1],
                    "valid_at": "2026-08-01T00:00:00+00:00",
                    "required_hop_memory_ids": [[memory_one]],
                    "forbidden_memory_ids": [],
                    "expected_end_entity": middle,
                    "expected_path_count": 1,
                },
                {
                    "query_id": f"q-{name}-wrong-type",
                    "partition": partition,
                    "category": "wrong_relation_adversary",
                    "scope": scope_name,
                    "query": f"{anchor}是否经由{middle}关联到一个不存在的出生地？",
                    "entity_mentions": [anchor],
                    "steps": [
                        steps[0],
                        {"relation_types": ["BORN_IN"], "direction": "outbound"},
                    ],
                    "valid_at": "2026-08-01T00:00:00+00:00",
                    "required_hop_memory_ids": [],
                    "forbidden_memory_ids": [],
                    "expected_end_entity": "",
                    "expected_path_count": 0,
                },
            )
        )
    relation_types.add("BORN_IN")
    # Pet's second edge starts in July: the same topology must not exist in March.
    queries.append(
        {
            "query_id": "q-pet-before-second-hop",
            "partition": "adversarial",
            "category": "second_hop_not_yet_valid",
            "scope": "s04",
            "query": "三月份豆包经由陈姨最终在哪里？",
            "entity_mentions": ["豆包"],
            "steps": [
                {"relation_types": ["CARED_FOR_BY"], "direction": "outbound"},
                {"relation_types": ["LOCATED_AT"], "direction": "outbound"},
            ],
            "valid_at": "2026-03-01T00:00:00+00:00",
            "required_hop_memory_ids": [],
            "forbidden_memory_ids": ["m-pet-2"],
            "expected_end_entity": "",
            "expected_path_count": 0,
        }
    )
    scopes["s09"] = {
        "user_id": "path-owner-09",
        "agent_id": "path-benchmark",
    }
    fixtures.append(
        {
            "memory_id": "m-orphan-1",
            "scope": "s09",
            "content": "护照由小李保管。",
            "valid_from": "2026-01-01T00:00:00+00:00",
            "valid_to": "",
        }
    )
    entities.extend(
        (
            {"entity_id": "e-orphan-passport", "scope": "s09", "name": "护照"},
            {"entity_id": "e-orphan-li", "scope": "s09", "name": "小李"},
            {"entity_id": "e-orphan-beijing", "scope": "s09", "name": "北京"},
        )
    )
    edges.extend(
        (
            {
                "edge_id": "edge-orphan-1",
                "scope": "s09",
                "source_entity_id": "e-orphan-passport",
                "target_entity_id": "e-orphan-li",
                "relation_type": "HELD_BY",
                "fact": "护照由小李保管。",
                "memory_id": "m-orphan-1",
                "valid_at": "2026-01-01T00:00:00+00:00",
                "invalid_at": "",
            },
            {
                "edge_id": "edge-orphan-2",
                "scope": "s09",
                "source_entity_id": "e-orphan-li",
                "target_entity_id": "e-orphan-beijing",
                "relation_type": "LOCATED_AT",
                "fact": "小李目前在北京。",
                "memory_id": "",
                "valid_at": "2026-01-01T00:00:00+00:00",
                "invalid_at": "",
            },
        )
    )
    queries.append(
        {
            "query_id": "q-orphan-missing-second-provenance",
            "partition": "adversarial",
            "category": "orphan_second_hop",
            "scope": "s09",
            "query": "护照经由小李最终在哪里？",
            "entity_mentions": ["护照"],
            "steps": [
                {"relation_types": ["HELD_BY"], "direction": "outbound"},
                {"relation_types": ["LOCATED_AT"], "direction": "outbound"},
            ],
            "valid_at": "2026-08-01T00:00:00+00:00",
            "required_hop_memory_ids": [],
            "forbidden_memory_ids": [],
            "expected_end_entity": "",
            "expected_path_count": 0,
        }
    )
    return {
        "suite": "doppel-personal-relation-path-ablation-zh-v1",
        "suite_version": "1.0.0-draft.1",
        "language": "zh-CN",
        "status": "draft",
        "frozen": False,
        "publication_ready": False,
        "description": "Generated oracle-path draft; no natural-language Planner or model output is involved.",
        "relation_types": sorted(relation_types),
        "scopes": scopes,
        "fixtures": fixtures,
        "entities": entities,
        "edges": edges,
        "queries": queries,
        "requirements": {
            "min_queries": 25,
            "min_scopes": 9,
            "max_hops": 2,
            "complete_hop_evidence": True,
            "publication_ready": False,
        },
    }


def main() -> None:
    destination = (
        Path(__file__).resolve().parent
        / "datasets"
        / "personal-relation-path-ablation-zh-v1.json"
    )
    destination.write_text(
        json.dumps(build_dataset(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(destination)


if __name__ == "__main__":
    main()
