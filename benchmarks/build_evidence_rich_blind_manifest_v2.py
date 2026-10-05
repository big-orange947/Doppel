"""Coherent host structure for the pre-retrieval revision of blind corpus V1."""

from __future__ import annotations

from dataclasses import dataclass

from benchmarks.build_evidence_rich_blind_manifest import build_manifest as build_v1
from benchmarks.evidence_rich_blind_authoring import (
    BlindCorpusAuthoringManifest,
    HostEntitySlot,
    OwnerAuthoringManifest,
)


@dataclass(frozen=True)
class RelationSemantics:
    source_types: frozenset[str]
    target_types: frozenset[str]
    meaning: str


ALL_TYPES = frozenset(
    {"person", "organization", "place", "object", "document", "animal", "concept"}
)
PERSON_OR_ORG = frozenset({"person", "organization"})
THINGS = frozenset({"object", "document", "animal"})
RELATIONS = {
    "HELD_BY": RelationSemantics(THINGS, PERSON_OR_ORG, "由目标保管、持有"),
    "CREATED_BY": RelationSemantics(THINGS, PERSON_OR_ORG, "由目标创作、制作或培育"),
    "MANAGED_BY": RelationSemantics(THINGS, PERSON_OR_ORG, "由目标管理"),
    "SOLD_BY": RelationSemantics(THINGS, PERSON_OR_ORG, "由目标出售"),
    "REPAIRED_BY": RelationSemantics(
        frozenset({"object"}), frozenset({"person"}), "由目标维修"
    ),
    "ISSUED_BY": RelationSemantics(
        frozenset({"document"}), frozenset({"organization"}), "由目标机构签发"
    ),
    "CARED_FOR_BY": RelationSemantics(
        frozenset({"animal"}), frozenset({"person"}), "由目标照护"
    ),
    "PURCHASED_AT": RelationSemantics(
        frozenset({"object"}), frozenset({"organization"}), "在目标门店购买"
    ),
    "RECOMMENDED_BY": RelationSemantics(
        frozenset({"object"}), frozenset({"person"}), "由目标推荐"
    ),
    "STORED_IN": RelationSemantics(
        frozenset({"object"}), frozenset({"object"}), "存放在目标容器中"
    ),
    "BORROWED_BY": RelationSemantics(
        frozenset({"object"}), frozenset({"person"}), "被目标借用"
    ),
    "ADOPTED_FROM": RelationSemantics(
        frozenset({"animal"}), frozenset({"organization"}), "从目标机构领养"
    ),
    "WORKS_AT": RelationSemantics(
        frozenset({"person"}), frozenset({"organization"}), "在目标机构任职"
    ),
    "LOCATED_IN": RelationSemantics(
        frozenset({"organization", "object"}), frozenset({"place"}), "位于目标地点"
    ),
    "MEMBER_OF": RelationSemantics(
        frozenset({"person"}), frozenset({"organization"}), "属于目标组织或是其成员"
    ),
    "OWNED_BY": RelationSemantics(
        frozenset({"organization"}), frozenset({"organization"}), "由目标拥有或运营"
    ),
    "RELATED_TO": RelationSemantics(
        ALL_TYPES, ALL_TYPES, "与目标存在关联；不暗示具体保管、购买或其他关系"
    ),
}


def audit_relation_endpoints(
    manifest: BlindCorpusAuthoringManifest,
) -> list[dict[str, str]]:
    """Audit schema types rather than guessing from generated names or questions."""
    issues = []
    for owner in manifest.owners:
        entities = {item.surface_key: item for item in owner.entities}
        for memory in owner.memories:
            if not memory.relation_type:
                continue
            spec = RELATIONS[memory.relation_type]
            for role, key, allowed in (
                ("source", memory.source_entity_key, spec.source_types),
                ("target", memory.target_entity_key, spec.target_types),
            ):
                if entities[key].entity_type not in allowed:
                    issues.append(
                        {
                            "owner_key": owner.owner_key,
                            "memory_key": memory.surface_key,
                            "endpoint": role,
                            "entity_key": key,
                            "actual_type": entities[key].entity_type,
                            "relation_type": memory.relation_type,
                        }
                    )
    return issues


def build_manifest() -> BlindCorpusAuthoringManifest:
    original = build_v1()
    owners = [_repair_owner(owner) for owner in original.owners]
    result = BlindCorpusAuthoringManifest.model_validate(
        {
            **original.model_dump(mode="json"),
            "version": "1.4.0",
            "suite": "doppel-evidence-rich-blind-zh-v1-revised-host-manifest",
            "owners": [o.model_dump(mode="json") for o in owners],
        }
    )
    if audit_relation_endpoints(result):
        raise ValueError("revised host manifest has incompatible relation endpoints")
    return result


def _repair_owner(owner: OwnerAuthoringManifest) -> OwnerAuthoringManifest:
    bykey = {m.surface_key: m for m in owner.memories}
    first = RELATIONS[bykey["memory-two-hop-first"].relation_type]
    second = RELATIONS[bykey["memory-two-hop-second"].relation_type]
    anchor_type = next(iter(first.source_types))
    middle_type = next(iter(first.target_types))
    final_type = next(iter(second.target_types))
    types = {
        "entity-one-hop-anchor": anchor_type,
        "entity-one-hop-target": "person",
        "entity-two-hop-anchor": anchor_type,
        "entity-two-hop-middle": middle_type,
        "entity-two-hop-target": final_type,
        "entity-branch-target": middle_type,
    }
    entities = []
    for entity in owner.entities:
        data = entity.model_dump(mode="json")
        if entity.surface_key in types:
            data["entity_type"] = types[entity.surface_key]
            data["semantic_brief"] += f"；必须是 {types[entity.surface_key]} 类型的实体"
        entities.append(HostEntitySlot.model_validate(data))
    stem = owner.owner_key.removeprefix("owner-")
    for key, kind, brief in (
        ("branch-final", final_type, "竞争路径的终点；与主要路径终点不同"),
        (
            "no-answer-anchor",
            "object",
            "独立的个人物品，仅有保管信息；与一跳和两跳对象均不同",
        ),
        ("no-answer-holder", "person", "独立无答案物品的当前保管人"),
    ):
        entities.append(
            HostEntitySlot(
                surface_key=f"entity-{key}",
                entity_id=f"entity-{stem}-{key}",
                scope=owner.scope,
                entity_type=kind,
                semantic_brief=f"{brief}；必须是 {kind} 类型的实体",
            )
        )
    memories = []
    for memory in owner.memories:
        data = memory.model_dump(mode="json")
        key = memory.surface_key
        if key == "memory-competing-first":
            data["semantic_brief"] = (
                "描述确切的 entity-one-hop-anchor 与 entity-branch-target 的关系；不得换成另一个相似对象"
            )
        elif key == "memory-competing-second":
            data["target_entity_key"] = "entity-branch-final"
        elif key in {"memory-no-answer-related", "memory-no-answer-stale"}:
            data["source_entity_key"] = "entity-no-answer-anchor"
            if key == "memory-no-answer-related":
                data["target_entity_key"] = "entity-no-answer-holder"
            data["semantic_brief"] = (
                "独立个人物品 entity-no-answer-anchor 的保管关系；不得附加购买者信息"
            )
        if memory.relation_type:
            spec = RELATIONS[memory.relation_type]
            data["semantic_brief"] += (
                f"；确切关系为 {data['source_entity_key']} {spec.meaning} {data['target_entity_key']}；"
                "正文和边事实必须使用这两个端点的同一显示名，不得改指别的对象"
            )
            if memory.valid_to:
                data["semantic_brief"] += (
                    "；这是已失效的历史关系，正文和边事实都必须明确使用过去时并说明已结束"
                )
        elif key == "memory-temporary-residence":
            data["semantic_brief"] += (
                "；入住 entity-temporary-city 的时间从 2026年2月1日开始，到 2026年4月1日之前结束"
            )
        elif key == "memory-current-residence":
            data["semantic_brief"] += "；常住城市使用 entity-current-city 的显示名"
        elif key == "memory-current-employer":
            data["semantic_brief"] += (
                "；当前任职机构使用 entity-current-employer 的显示名"
            )
        elif key == "memory-old-employer":
            data["semantic_brief"] += "；旧机构使用 entity-old-employer 的显示名"
        memories.append(type(memory).model_validate(data))
    queries = []
    for query in owner.queries:
        data = query.model_dump(mode="json")
        if query.surface_key == "query-no-answer":
            data["semantic_brief"] = (
                "询问独立物品 entity-no-answer-anchor 是谁购买的；问句本身不要宣告答案未知，也不要补出购买者"
            )
        elif query.surface_key == "query-document":
            data["semantic_brief"] += (
                "；询问文档中记录的那一项事实的具体值，不要改为询问哪份文档"
            )
        elif query.surface_key == "query-cross-conversation":
            data["semantic_brief"] += (
                "；询问已提及物品的辨识信息，不要改为询问是哪件物品"
            )
        queries.append(type(query).model_validate(data))
    return OwnerAuthoringManifest.model_validate(
        {
            **owner.model_dump(mode="json"),
            "entities": [e.model_dump(mode="json") for e in entities],
            "memories": [m.model_dump(mode="json") for m in memories],
            "queries": [q.model_dump(mode="json") for q in queries],
        }
    )
