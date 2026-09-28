"""Build the host-authoritative manifest for blind evidence-rich evaluation."""

from __future__ import annotations

import json
from pathlib import Path

from benchmarks.evidence_rich_blind_authoring import (
    BlindCorpusAuthoringManifest,
    HostEntitySlot,
    HostMemorySlot,
    HostQuerySlot,
    OwnerAuthoringManifest,
)

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "data/doppel/evidence-rich-blind-v1-host-manifest.json"
IMPLEMENTATION_BASELINE = "9b672b593c1807616616897bd4800e81f911d188"

TWO_HOP_FAMILIES = (
    ("REPAIRED_BY", "WORKS_AT", "维修人员及其任职机构"),
    ("ISSUED_BY", "LOCATED_IN", "证件签发机构及其所在地"),
    ("CARED_FOR_BY", "WORKS_AT", "照护人员及其任职机构"),
    ("PURCHASED_AT", "LOCATED_IN", "购买门店及其所在地"),
    ("RECOMMENDED_BY", "WORKS_AT", "推荐人及其任职机构"),
    ("STORED_IN", "LOCATED_IN", "存放容器及其所在位置"),
    ("BORROWED_BY", "MEMBER_OF", "借用人及其所属组织"),
    ("ADOPTED_FROM", "OWNED_BY", "领养机构及其运营方"),
)
ONE_HOP_TYPES = ("HELD_BY", "CREATED_BY", "MANAGED_BY", "SOLD_BY")
RELATION_TYPES = sorted(
    {
        "RELATED_TO",
        *ONE_HOP_TYPES,
        *(relation for pair in TWO_HOP_FAMILIES for relation in pair[:2]),
    }
)
CATEGORIES = (
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
)
DISTRACTOR_DOMAINS = (
    "居住地点及搬迁安排",
    "工作机构及职业变化",
    "旅行经历及取消计划",
    "书籍设备及物品保管",
    "证件文档及办理记录",
    "饮食阅读及生活偏好",
    "健康信息及他人转述",
)


def build_manifest() -> BlindCorpusAuthoringManifest:
    owners = [_build_owner(index) for index in range(1, 25)]
    requirements = {
        "min_owners": 24,
        "min_queries": 240,
        "min_memories": 4_608,
        "min_relation_types": 16,
        "min_two_hop_pairs": 8,
        "min_non_default_two_hop_pairs": 6,
        "min_queries_per_owner": 10,
        "min_memories_per_owner": 192,
        "min_distractors_per_owner": 160,
        "min_partition_dev": 6,
        "min_partition_sealed": 12,
        "min_partition_adversarial": 6,
        **{f"min_category_{category}": 24 for category in CATEGORIES},
    }
    return BlindCorpusAuthoringManifest(
        suite="doppel-evidence-rich-blind-zh-v1-host-manifest",
        version="1.0.0",
        language="zh-CN",
        status="structure_frozen",
        authoring_contract_version=1,
        implementation_baseline=IMPLEMENTATION_BASELINE,
        relation_types=RELATION_TYPES,
        owners=owners,
        requirements=requirements,
    )


def _build_owner(index: int) -> OwnerAuthoringManifest:
    stem = f"blind-{index:02d}"
    scope = f"scope-{stem}"
    subject = f"subject-{stem}"
    partition = "dev" if index <= 6 else "sealed" if index <= 18 else "adversarial"
    one_hop = ONE_HOP_TYPES[(index - 1) % len(ONE_HOP_TYPES)]
    first_hop, second_hop, route_brief = TWO_HOP_FAMILIES[
        (index - 1) % len(TWO_HOP_FAMILIES)
    ]
    entities = _entities(stem, scope, route_brief)
    memories = _memories(
        stem,
        scope,
        subject,
        one_hop=one_hop,
        first_hop=first_hop,
        second_hop=second_hop,
        route_brief=route_brief,
    )
    queries = _queries(
        stem,
        scope,
        subject,
        partition=partition,
        one_hop=one_hop,
        first_hop=first_hop,
        second_hop=second_hop,
        route_brief=route_brief,
    )
    return OwnerAuthoringManifest(
        owner_key=f"owner-{stem}",
        scope=scope,
        partition=partition,
        entities=entities,
        memories=memories,
        queries=queries,
    )


def _entities(stem: str, scope: str, route_brief: str) -> list[HostEntitySlot]:
    specifications = (
        ("current-city", "place", "主人的长期常住城市"),
        ("temporary-city", "place", "主人曾短期居住的另一座城市"),
        ("current-employer", "organization", "主人当前任职的机构"),
        ("old-employer", "organization", "主人已经离开的旧任职机构"),
        ("one-hop-anchor", "object", "用于一跳关系问题的个人物品"),
        ("one-hop-target", "person", "与个人物品有直接关系的人或机构"),
        ("two-hop-anchor", "object", f"用于{route_brief}问题的个人对象"),
        ("two-hop-middle", "person", f"{route_brief}中的中间实体"),
        ("two-hop-target", "organization", f"{route_brief}中的最终实体"),
        ("document", "document", "包含一个稳定个人事实的文档"),
        ("cross-item", "object", "在另一段会话中提及的个人物品"),
        ("peer", "person", "曾错误转述主人信息的联系人"),
        ("branch-target", "person", "语义相近但不构成答案的竞争分支实体"),
        ("cycle-node", "concept", "只用于构成图循环的关联节点"),
        ("shared-alias", "organization", "跨 owner 故意复用显示名的机构"),
        ("distractor-hub", "organization", "密集干扰记忆反复提及的机构"),
    )
    return [
        HostEntitySlot(
            surface_key=f"entity-{key}",
            entity_id=f"entity-{stem}-{key}",
            scope=scope,
            entity_type=entity_type,
            semantic_brief=brief,
            shared_name_group=("shared-org-alias-v1" if key == "shared-alias" else ""),
        )
        for key, entity_type, brief in specifications
    ]


def _memories(
    stem: str,
    scope: str,
    subject: str,
    *,
    one_hop: str,
    first_hop: str,
    second_hop: str,
    route_brief: str,
) -> list[HostMemorySlot]:
    rows: list[dict[str, object]] = [
        _memory_row(
            "current-residence",
            "fact",
            "主人当前长期住在常住城市",
            "residence.current",
            "current",
            "required",
        ),
        _memory_row(
            "temporary-residence",
            "fact",
            "主人曾因短期任务临时住在另一座城市，且临住已经结束",
            "residence.temporary",
            "historical",
            "required",
            valid_from="2026-02-01T00:00:00+08:00",
            valid_to="2026-04-01T00:00:00+08:00",
        ),
        _memory_row(
            "current-employer",
            "fact",
            "主人更正后当前任职于新机构",
            "career.employer",
            "current",
            "required",
        ),
        _memory_row(
            "old-employer",
            "fact",
            "主人过去任职于旧机构，后来已离职",
            "career.employer",
            "historical",
            "forbidden",
            valid_from="2023-01-01T00:00:00+08:00",
            valid_to="2025-01-01T00:00:00+08:00",
        ),
        _memory_row(
            "trip-one",
            "episode",
            "主人完成了第一段独立旅行",
            "travel.completed",
            "historical",
            "required",
            event_key=f"event-{stem}-trip-one",
        ),
        _memory_row(
            "trip-two",
            "episode",
            "主人完成了第二段不同的旅行",
            "travel.completed",
            "historical",
            "required",
            event_key=f"event-{stem}-trip-two",
        ),
        _memory_row(
            "trip-cancelled",
            "fact",
            "主人取消了一段原计划的旅行，没有成行",
            "travel.plan",
            "cancelled",
            "forbidden",
        ),
        _memory_row(
            "one-hop",
            "relation",
            f"个人物品与目标实体存在 {one_hop} 直接关系",
            "possession.one-hop",
            "current",
            "required",
            relation=(one_hop, "entity-one-hop-anchor", "entity-one-hop-target"),
        ),
        _memory_row(
            "two-hop-first",
            "relation",
            f"个人对象经 {first_hop} 指向{route_brief}的中间实体",
            "possession.two-hop-first",
            "current",
            "required",
            relation=(first_hop, "entity-two-hop-anchor", "entity-two-hop-middle"),
        ),
        _memory_row(
            "two-hop-second",
            "relation",
            f"中间实体经 {second_hop} 指向{route_brief}的最终实体",
            "possession.two-hop-second",
            "current",
            "required",
            relation=(second_hop, "entity-two-hop-middle", "entity-two-hop-target"),
        ),
        _memory_row(
            "document-fact",
            "document_fact",
            "一份文档明确记录主人的稳定证件或账户事实",
            "document.stable-fact",
            "current",
            "required",
            source_kind="document",
        ),
        _memory_row(
            "cross-conversation",
            "fact",
            "另一段会话明确记录个人物品的辨识信息",
            "possession.cross-conversation",
            "current",
            "required",
            conversation="history",
        ),
        _memory_row(
            "subject-correction",
            "fact",
            "主人明确纠正关于自己的健康或偏好信息",
            "owner.corrected-claim",
            "current",
            "required",
        ),
        _memory_row(
            "peer-misattribution",
            "fact",
            "联系人曾把另一个人的情况错误安在主人身上",
            "owner.corrected-claim",
            "current",
            "forbidden",
            authority="peer_statement",
            state="candidate",
        ),
        _memory_row(
            "no-answer-related",
            "relation",
            "个人物品目前由某人保管，但没有任何购买者信息",
            "possession.related-holder",
            "current",
            "related",
            relation=("HELD_BY", "entity-one-hop-anchor", "entity-branch-target"),
        ),
        _memory_row(
            "no-answer-stale",
            "relation",
            "过期记录曾把同一物品关联到另一个人",
            "possession.related-holder",
            "historical",
            "forbidden",
            valid_from="2023-01-01T00:00:00+08:00",
            valid_to="2024-01-01T00:00:00+08:00",
            relation=("HELD_BY", "entity-one-hop-anchor", "entity-peer"),
        ),
        _memory_row(
            "competing-first",
            "relation",
            f"相近个人对象经 {first_hop} 指向竞争分支实体",
            "graph.competing-first",
            "current",
            "related",
            relation=(first_hop, "entity-one-hop-anchor", "entity-branch-target"),
        ),
        _memory_row(
            "competing-second",
            "relation",
            f"竞争分支实体经 {second_hop} 指向共享别名机构",
            "graph.competing-second",
            "current",
            "related",
            relation=(second_hop, "entity-branch-target", "entity-shared-alias"),
        ),
        _memory_row(
            "cycle-out",
            "relation",
            "个人对象关联到循环节点",
            "graph.cycle-out",
            "current",
            "support",
            relation=("RELATED_TO", "entity-two-hop-anchor", "entity-cycle-node"),
        ),
        _memory_row(
            "cycle-back",
            "relation",
            "循环节点反向关联到同一个个人对象",
            "graph.cycle-back",
            "current",
            "support",
            relation=("RELATED_TO", "entity-cycle-node", "entity-two-hop-anchor"),
        ),
        _memory_row(
            "stale-route",
            "relation",
            f"已过期的个人对象 {first_hop} 关系分支",
            "graph.stale-route",
            "historical",
            "forbidden",
            valid_from="2023-01-01T00:00:00+08:00",
            valid_to="2024-01-01T00:00:00+08:00",
            relation=(first_hop, "entity-two-hop-anchor", "entity-branch-target"),
        ),
        _memory_row(
            "support-context",
            "fact",
            "与关系问题同主题但只提供背景、不提供答案的上下文",
            "graph.support-context",
            "current",
            "support",
        ),
    ]
    for index in range(23, 193):
        domain = DISTRACTOR_DOMAINS[(index - 23) % len(DISTRACTOR_DOMAINS)]
        rows.append(
            _memory_row(
                f"distractor-{index:03d}",
                "preference" if index % 11 == 0 else "fact",
                f"高密度干扰记忆 {index:03d}，主题为{domain}，包含与主问题相近的名词但不支持答案",
                f"distractor.{index:03d}",
                "timeless" if index % 11 == 0 else "current",
                "distractor",
            )
        )
    result: list[HostMemorySlot] = []
    for index, row in enumerate(rows, start=1):
        key = str(row.pop("key"))
        relation_value = row.pop("relation", None)
        relation = (
            tuple(str(item) for item in relation_value)
            if isinstance(relation_value, tuple)
            else ()
        )
        row["subject_id"] = subject
        result.append(
            HostMemorySlot.model_validate(
                {
                    "surface_key": f"memory-{key}",
                    "memory_id": f"memory-{stem}-{index:03d}",
                    "scope": scope,
                    "conversation_id": (
                        f"conversation-{stem}-{row.pop('conversation')}"
                    ),
                    "evidence_id": f"evidence-{stem}-{index:03d}",
                    "relation_type": relation[0] if relation else "",
                    "source_entity_key": relation[1] if relation else "",
                    "target_entity_key": relation[2] if relation else "",
                    **row,
                }
            )
        )
    return result


def _memory_row(
    key: str,
    kind: str,
    brief: str,
    fact_key: str,
    temporal_status: str,
    corpus_role: str,
    *,
    event_key: str = "",
    source_kind: str = "chat",
    conversation: str = "primary",
    authority: str = "human_self",
    state: str = "confirmed",
    valid_from: str = "2025-01-01T00:00:00+08:00",
    valid_to: str = "",
    relation: tuple[str, str, str] | None = None,
) -> dict[str, object]:
    return {
        "key": key,
        "kind": kind,
        "semantic_brief": brief,
        "subject_id": "__OWNER_SUBJECT__",
        "fact_key": fact_key,
        "event_key": event_key,
        "temporal_status": temporal_status,
        "authority": authority,
        "state": state,
        "valid_from": valid_from,
        "valid_to": valid_to,
        "corpus_role": corpus_role,
        "source_kind": source_kind,
        "conversation": conversation,
        "relation": relation,
    }


def _queries(
    stem: str,
    scope: str,
    subject: str,
    *,
    partition: str,
    one_hop: str,
    first_hop: str,
    second_hop: str,
    route_brief: str,
) -> list[HostQuerySlot]:
    style = {"dev": "explicit", "sealed": "paraphrase", "adversarial": "elliptical"}[
        partition
    ]
    rows = (
        (
            "current-residence",
            "current_residence",
            "residence",
            "lookup",
            "current",
            "询问主人结束临住后现在长期住在哪里",
            ["memory-current-residence"],
            ["memory-temporary-residence"],
            [],
            [],
            None,
        ),
        (
            "temporary-as-of",
            "temporary_residence_as_of",
            "residence",
            "lookup",
            "as_of",
            "询问 2026 年 3 月主人临时住在哪座城市",
            ["memory-temporary-residence"],
            ["memory-current-residence"],
            [],
            [],
            None,
        ),
        (
            "corrected-fact",
            "corrected_fact",
            "career",
            "lookup",
            "current",
            "询问主人更正后的当前任职机构",
            ["memory-current-employer"],
            [],
            ["memory-old-employer"],
            [],
            None,
        ),
        (
            "episode-count",
            "episode_count",
            "travel",
            "count",
            "history",
            "询问主人实际完成过多少次不同旅行，取消计划不计",
            ["memory-trip-one", "memory-trip-two"],
            [],
            ["memory-trip-cancelled"],
            [],
            2,
        ),
        (
            "one-hop",
            "one_hop_relation",
            "possessions",
            "lookup",
            "current",
            f"询问个人物品通过 {one_hop} 直接关联到谁或哪个机构",
            ["memory-one-hop"],
            ["memory-competing-first"],
            ["memory-no-answer-stale"],
            [[one_hop]],
            None,
        ),
        (
            "two-hop",
            "two_hop_relation",
            "possessions",
            "lookup",
            "current",
            f"通过{route_brief}两跳关系询问最终实体",
            ["memory-two-hop-first", "memory-two-hop-second"],
            ["memory-competing-first", "memory-competing-second"],
            ["memory-stale-route"],
            [[first_hop, second_hop]],
            None,
        ),
        (
            "document",
            "document_fact",
            "documents",
            "lookup",
            "current",
            "询问只有个人文档明确记录的稳定事实",
            ["memory-document-fact"],
            [],
            [],
            [],
            None,
        ),
        (
            "cross-conversation",
            "cross_conversation",
            "possessions",
            "lookup",
            "current",
            "在新会话询问另一段会话记录的个人物品辨识信息",
            ["memory-cross-conversation"],
            [],
            [],
            [],
            None,
        ),
        (
            "subject-correction",
            "subject_correction",
            "health",
            "lookup",
            "current",
            "询问主人亲自澄清后的健康或偏好信息，不采信联系人误传",
            ["memory-subject-correction"],
            [],
            ["memory-peer-misattribution"],
            [],
            None,
        ),
        (
            "no-answer",
            "no_answer_related",
            "possessions",
            "lookup",
            "current",
            "询问个人物品由谁购买；现有记忆只知道由谁保管，答案未知",
            [],
            ["memory-no-answer-related", "memory-support-context"],
            ["memory-no-answer-stale"],
            [],
            None,
        ),
    )
    result: list[HostQuerySlot] = []
    for index, row in enumerate(rows, start=1):
        (
            key,
            category,
            domain,
            intent,
            temporal_view,
            brief,
            required,
            related,
            forbidden,
            routes,
            expected_count,
        ) = row
        result.append(
            HostQuerySlot.model_validate(
                {
                    "surface_key": f"query-{key}",
                    "case_id": f"case-{stem}-{index:02d}",
                    "scope": scope,
                    "category": category,
                    "domain": domain,
                    "query_style": style,
                    "conversation_id": f"conversation-{stem}-query-{index:02d}",
                    "intent": intent,
                    "temporal_view": temporal_view,
                    "semantic_brief": brief,
                    "valid_at": (
                        "2026-03-15T00:00:00+08:00"
                        if category == "temporary_residence_as_of"
                        else "2026-09-28T00:00:00+08:00"
                    ),
                    "subject_id": subject,
                    "entity_mentions": [],
                    "answerable": bool(required),
                    "required_memory_keys": required,
                    "related_memory_keys": related,
                    "hard_forbidden_memory_keys": forbidden,
                    "required_relation_routes": routes,
                    "expected_count": expected_count,
                }
            )
        )
    return result


def main() -> None:
    manifest = build_manifest()
    OUTPUT.write_text(
        json.dumps(manifest.model_dump(mode="json"), ensure_ascii=False, indent=2)
        + "\n",
        "utf-8",
    )
    print(f"output: {OUTPUT.resolve()}")
    print(f"fingerprint: {manifest.fingerprint}")


if __name__ == "__main__":
    main()
