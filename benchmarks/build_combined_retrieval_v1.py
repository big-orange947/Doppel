"""Build the frozen 144-query combined retrieval corpus deterministically."""

from __future__ import annotations

import argparse
import json
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "benchmarks/datasets/combined-retrieval-zh-v1.json"
CATALOG = ROOT / "benchmarks/catalogs/personal-relations-v1.json"
SEED = 94720260924


@dataclass(frozen=True)
class RoutePattern:
    first_type: str
    first_direction: Literal["outbound", "inbound"]
    second_type: str
    second_direction: Literal["outbound", "inbound"]
    anchor: str
    middle: str
    answer: str
    one_hop_query: str
    two_hop_query: str


PATTERNS = (
    RoutePattern(
        "HELD_BY", "outbound", "LOCATED_AT", "outbound",
        "黄铜星盘", "许澄", "临江公寓",
        "我那只黄铜星盘现在由谁保管？",
        "替我保管黄铜星盘的人目前住在哪里？",
    ),
    RoutePattern(
        "REPAIRED_BY", "outbound", "EMPLOYED_BY", "outbound",
        "老式放映机", "杜师傅", "青岚影像社",
        "老式放映机交给谁维修了？",
        "修理老式放映机的师傅供职于哪家机构？",
    ),
    RoutePattern(
        "ISSUED_BY", "outbound", "LOCATED_AT", "outbound",
        "潜水资格卡", "海岳协会", "滨河路九号",
        "我的潜水资格卡是哪家机构签发的？",
        "签发潜水资格卡的机构位于哪里？",
    ),
    RoutePattern(
        "LOANED_TO", "inbound", "OWNED_BY", "outbound",
        "程野", "木刻刀组", "闻溪",
        "有哪些东西借给程野使用了？",
        "借给程野的那套木刻刀究竟归谁所有？",
    ),
    RoutePattern(
        "RECOMMENDED_BY", "outbound", "EMPLOYED_BY", "outbound",
        "《潮汐图谱》", "季岚", "远帆书店",
        "《潮汐图谱》是谁推荐给我的？",
        "推荐《潮汐图谱》的人在哪家单位工作？",
    ),
    RoutePattern(
        "CARED_FOR_BY", "outbound", "LOCATED_AT", "outbound",
        "玄凤鹦鹉阿麦", "罗姨", "松石花园",
        "阿麦这段时间由谁照料？",
        "照料阿麦的人现在住在哪个小区？",
    ),
    RoutePattern(
        "PURCHASED_AT", "outbound", "LOCATED_AT", "outbound",
        "手摇咖啡磨", "北屿器具铺", "栖霞街十二号",
        "我的手摇咖啡磨是在哪家店买的？",
        "卖给我手摇咖啡磨的店铺位于哪里？",
    ),
    RoutePattern(
        "ADOPTED_FROM", "inbound", "OWNED_BY", "outbound",
        "星河救助站", "狸花猫团子", "乔宁",
        "我从星河救助站领养的是哪只动物？",
        "从星河救助站领养来的那只猫现在归谁所有？",
    ),
    RoutePattern(
        "PURCHASED_BY", "outbound", "EMPLOYED_BY", "outbound",
        "胶片扫描仪", "秦舟", "墨桥工作室",
        "那台胶片扫描仪最初是谁买的？",
        "购买胶片扫描仪的人目前在哪里任职？",
    ),
    RoutePattern(
        "REPAIRED_AT", "outbound", "LOCATED_AT", "outbound",
        "折叠自行车", "白塔修车铺", "槐安巷三号",
        "折叠自行车送到哪家店维修了？",
        "维修折叠自行车的店铺具体在什么地方？",
    ),
    RoutePattern(
        "STORED_IN", "outbound", "LOCATED_AT", "outbound",
        "旅行底片盒", "防潮箱乙号", "书房北墙",
        "旅行底片盒平时收在哪个容器里？",
        "装着旅行底片的防潮箱放在房间什么位置？",
    ),
    RoutePattern(
        "ISSUED_BY", "inbound", "OWNED_BY", "outbound",
        "云帆培训中心", "结业证乙七", "林沐",
        "云帆培训中心签发给我的是哪份证书？",
        "云帆培训中心签发的那份结业证属于谁？",
    ),
)

BEVERAGES = (
    "桂花乌龙", "烘米茶", "无糖豆乳", "陈皮白茶", "黑芝麻糊", "苹果肉桂茶",
    "薄荷柠檬水", "焙火铁观音", "南非国宝茶", "姜枣水", "冷萃茉莉", "燕麦拿铁",
)
SEMANTIC_QUERIES = (
    "我习惯用哪种饮品开始一天？",
    "按我的日常习惯，早晨一般会喝什么？",
    "如果准备我的早餐，饮料应该选哪一种？",
    "我早起时最常喝的东西是什么？",
    "我的晨间饮品偏好是什么？",
    "平时给我准备早饭时该搭配什么喝的？",
)


def build_dataset() -> dict[str, Any]:
    catalog = json.loads(CATALOG.read_text("utf-8"))
    relation_types = [str(item["name"]) for item in catalog]
    scopes: dict[str, dict[str, str]] = {}
    fixtures: list[dict[str, Any]] = []
    entities: list[dict[str, str]] = []
    edges: list[dict[str, str]] = []
    queries: list[dict[str, Any]] = []

    for index in range(36):
        pattern = PATTERNS[index % len(PATTERNS)]
        scope_name = f"s{index + 1:02d}"
        stem = f"c{index + 1:02d}"
        scopes[scope_name] = {
            "user_id": f"sealed-owner-{index + 1:02d}",
            "agent_id": "doppel-sealed-eval",
        }
        main_nodes = _add_route(
            stem=f"{stem}-main",
            scope=scope_name,
            pattern=pattern,
            valid_from="2025-01-01T00:00:00+08:00",
            fixtures=fixtures,
            entities=entities,
            edges=edges,
        )
        future_nodes = _add_route(
            stem=f"{stem}-future",
            scope=scope_name,
            pattern=pattern,
            valid_from="2025-01-01T00:00:00+08:00",
            second_valid_from="2027-01-01T00:00:00+08:00",
            name_suffix="（备用）",
            fixtures=fixtures,
            entities=entities,
            edges=edges,
        )
        beverage = BEVERAGES[index % len(BEVERAGES)]
        semantic_memory_id = f"m-{stem}-preference"
        fixtures.append(
            _memory(
                semantic_memory_id,
                scope_name,
                f"我的固定晨间习惯是喝{beverage}，通常不另外加糖。",
                "2024-03-01T00:00:00+08:00",
            )
        )
        for distractor_index in range(95):
            fixtures.append(
                _distractor(
                    scope_name,
                    stem,
                    distractor_index,
                    beverage=beverage,
                    pattern=pattern,
                )
            )

        route = _route(pattern)
        valid_at = "2026-06-01T12:00:00+08:00"
        queries.extend(
            (
                {
                    "case_id": f"q-{stem}-one-hop",
                    "partition": "sealed",
                    "category": "one_hop_relation",
                    "scope": scope_name,
                    "query": pattern.one_hop_query,
                    "anchor": pattern.anchor,
                    "entity_mentions": [pattern.anchor],
                    "valid_at": valid_at,
                    "required_routes": [route[:1]],
                    "required_memory_ids": [main_nodes["first_memory_id"]],
                    "related_memory_ids": [],
                    "hard_forbidden_memory_ids": [],
                    "answerable": True,
                },
                {
                    "case_id": f"q-{stem}-two-hop",
                    "partition": "sealed",
                    "category": "two_hop_relation",
                    "scope": scope_name,
                    "query": pattern.two_hop_query,
                    "anchor": pattern.anchor,
                    "entity_mentions": [pattern.anchor],
                    "valid_at": valid_at,
                    "required_routes": [route],
                    "required_memory_ids": [
                        main_nodes["first_memory_id"],
                        main_nodes["second_memory_id"],
                    ],
                    "related_memory_ids": [],
                    "hard_forbidden_memory_ids": [],
                    "answerable": True,
                },
                {
                    "case_id": f"q-{stem}-semantic",
                    "partition": "sealed",
                    "category": "semantic_nonrelation",
                    "scope": scope_name,
                    "query": SEMANTIC_QUERIES[index % len(SEMANTIC_QUERIES)],
                    "anchor": "我",
                    "entity_mentions": [],
                    "valid_at": valid_at,
                    "required_routes": [],
                    "required_memory_ids": [semantic_memory_id],
                    "related_memory_ids": [],
                    "hard_forbidden_memory_ids": [],
                    "answerable": True,
                },
                {
                    "case_id": f"q-{stem}-future-hop",
                    "partition": "adversarial",
                    "category": "temporal_incomplete_path",
                    "scope": scope_name,
                    "query": _future_query(pattern),
                    "anchor": f"{pattern.anchor}（备用）",
                    "entity_mentions": [f"{pattern.anchor}（备用）"],
                    "valid_at": valid_at,
                    "required_routes": [route],
                    "required_memory_ids": [],
                    "related_memory_ids": [future_nodes["first_memory_id"]],
                    "hard_forbidden_memory_ids": [
                        future_nodes["second_memory_id"]
                    ],
                    "answerable": False,
                },
            )
        )

    rng = random.Random(SEED)
    rng.shuffle(fixtures)
    rng.shuffle(entities)
    rng.shuffle(edges)
    rng.shuffle(queries)
    return {
        "suite": "doppel-combined-retrieval-zh-v1",
        "version": "1.0.0",
        "language": "zh-CN",
        "status": "frozen",
        "frozen": True,
        "publication_ready": False,
        "seed": SEED,
        "description": (
            "Frozen synthetic corpus combining natural-language path generation, "
            "dense per-owner semantic distractors, temporal invalidation, graph "
            "provenance, and repeated cross-owner entity names. No real personal data."
        ),
        "relation_catalog": "benchmarks/catalogs/personal-relations-v1.json",
        "relation_types": relation_types,
        "scopes": scopes,
        "fixtures": fixtures,
        "entities": entities,
        "edges": edges,
        "queries": queries,
        "requirements": {
            "min_scopes": 36,
            "min_queries": 144,
            "min_memories": 3600,
            "min_memories_per_scope": 100,
            "min_queries_per_scope": 4,
            "min_category_one_hop_relation": 36,
            "min_category_two_hop_relation": 36,
            "min_category_semantic_nonrelation": 36,
            "min_category_temporal_incomplete_path": 36,
        },
    }


def _add_route(
    *,
    stem: str,
    scope: str,
    pattern: RoutePattern,
    valid_from: str,
    fixtures: list[dict[str, Any]],
    entities: list[dict[str, str]],
    edges: list[dict[str, str]],
    second_valid_from: str | None = None,
    name_suffix: str = "",
) -> dict[str, str]:
    node_names = (
        pattern.anchor + name_suffix,
        pattern.middle + name_suffix,
        pattern.answer + name_suffix,
    )
    node_ids = tuple(f"e-{stem}-{part}" for part in ("anchor", "middle", "answer"))
    for entity_id, name in zip(node_ids, node_names, strict=True):
        entities.append({"entity_id": entity_id, "scope": scope, "name": name})
    memory_ids = (f"m-{stem}-hop-1", f"m-{stem}-hop-2")
    relations = (pattern.first_type, pattern.second_type)
    directions = (pattern.first_direction, pattern.second_direction)
    times = (valid_from, second_valid_from or valid_from)
    for position, (relation_type, direction, at, memory_id) in enumerate(
        zip(relations, directions, times, memory_ids, strict=True)
    ):
        current_id, next_id = node_ids[position], node_ids[position + 1]
        current_name, next_name = node_names[position], node_names[position + 1]
        if direction == "outbound":
            source_id, target_id = current_id, next_id
            source_name, target_name = current_name, next_name
        else:
            source_id, target_id = next_id, current_id
            source_name, target_name = next_name, current_name
        fact = _fact(relation_type, source_name, target_name)
        fixtures.append(_memory(memory_id, scope, fact, at))
        edges.append(
            {
                "edge_id": f"edge-{stem}-{position + 1}",
                "scope": scope,
                "source_entity_id": source_id,
                "target_entity_id": target_id,
                "relation_type": relation_type,
                "fact": fact,
                "memory_id": memory_id,
                "valid_at": at,
                "invalid_at": "",
            }
        )
    return {"first_memory_id": memory_ids[0], "second_memory_id": memory_ids[1]}


def _memory(
    memory_id: str,
    scope: str,
    content: str,
    valid_from: str,
    *,
    authority: str = "human_self",
    state: str = "confirmed",
) -> dict[str, Any]:
    return {
        "memory_id": memory_id,
        "scope": scope,
        "content": content,
        "valid_from": valid_from,
        "valid_to": "",
        "authority": authority,
        "state": state,
        "tags": ["personal-memory"],
        "evidence_id": f"evidence:{memory_id}",
    }


def _distractor(
    scope: str,
    stem: str,
    index: int,
    *,
    beverage: str,
    pattern: RoutePattern,
) -> dict[str, Any]:
    topics = (
        f"朋友提过他早晨喜欢喝{beverage}，这不是我的固定习惯。",
        f"我把第{index + 1}份旅行清单收进了资料夹。",
        f"上次经过{pattern.answer}时拍过一张街景照片。",
        f"{pattern.middle}曾在群聊里讨论过早餐搭配。",
        f"我收藏的第{index + 1}张唱片是现场录音版本。",
        f"家里的第{index + 1}个收纳盒贴着蓝色标签。",
        "我计划以后尝试一种新的无糖饮品，尚未决定品种。",
        f"关于{pattern.anchor}的第{index + 1}条维护备注不涉及存放地点。",
    )
    authority = "agent_output" if index % 17 == 0 else "human_self"
    state = "expired" if index % 19 == 0 else "confirmed"
    valid_from = (
        "2027-02-01T00:00:00+08:00"
        if index % 23 == 0
        else "2024-01-01T00:00:00+08:00"
    )
    return _memory(
        f"m-{stem}-distractor-{index + 1:03d}",
        scope,
        topics[index % len(topics)],
        valid_from,
        authority=authority,
        state=state,
    )


def _route(pattern: RoutePattern) -> list[dict[str, Any]]:
    return [
        {
            "relation_types": [pattern.first_type],
            "direction": pattern.first_direction,
        },
        {
            "relation_types": [pattern.second_type],
            "direction": pattern.second_direction,
        },
    ]


def _future_query(pattern: RoutePattern) -> str:
    return (
        f"截至2026年6月，沿着{pattern.anchor}（备用）的关系链，"
        "最终地点或归属能确定吗？"
    )


def _fact(relation_type: str, source: str, target: str) -> str:
    templates = {
        "ADOPTED_FROM": "{source}是从{target}领养来的。",
        "CARED_FOR_BY": "{source}目前由{target}照料。",
        "EMPLOYED_BY": "{source}目前受雇于{target}。",
        "HELD_BY": "{source}现在由{target}保管。",
        "ISSUED_BY": "{source}由{target}签发。",
        "LOANED_TO": "{source}已经借给{target}使用。",
        "LOCATED_AT": "{source}目前位于{target}。",
        "OWNED_BY": "{source}归{target}所有。",
        "PURCHASED_AT": "{source}是在{target}购买的。",
        "PURCHASED_BY": "{source}最初由{target}购买。",
        "RECOMMENDED_BY": "{source}是{target}推荐给我的。",
        "REPAIRED_AT": "{source}送到{target}维修。",
        "REPAIRED_BY": "{source}由{target}负责维修。",
        "STORED_IN": "{source}平时收在{target}里。",
    }
    return templates[relation_type].format(source=source, target=target)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(build_dataset(), ensure_ascii=False, indent=2) + "\n", "utf-8"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
