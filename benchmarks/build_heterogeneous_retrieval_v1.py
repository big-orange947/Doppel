"""Build the frozen heterogeneous personal-memory retrieval V1 corpus."""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "benchmarks/datasets/heterogeneous-retrieval-zh-v1.json"
SEED = 94720260925
SCOPE_COUNT = 48
MEMORIES_PER_SCOPE = 192

CITIES = (
    "上海", "成都", "杭州", "苏州", "青岛", "厦门", "昆明", "南京",
    "长沙", "宁波", "武汉", "福州", "大连", "无锡", "珠海", "西安",
)
ROLES = (
    "产品设计师", "数据分析师", "建筑摄影师", "后端工程师", "编辑", "研究助理",
    "项目经理", "交互设计师", "测试工程师", "纪录片剪辑师", "策展人", "财务顾问",
)
ITEMS = (
    "《海边的卡夫卡》", "徕卡M11", "黑胶唱片箱", "旅行手账", "机械键盘",
    "胶片相机", "蓝色工具箱", "绝版画册", "露营灯", "录音笔", "银色行李箱",
    "木刻刀组",
)
PEOPLE = (
    "林屿", "周澄", "程野", "顾南", "沈乔", "陆遥", "许墨", "唐棠",
    "江屿", "苏禾", "叶岚", "陈渡", "宋清", "季川", "白榆", "温言",
)
DRINKS = (
    "桂花乌龙", "烘米茶", "无糖豆乳", "陈皮白茶", "燕麦拿铁", "姜枣水",
    "冷萃茉莉", "南非国宝茶", "薄荷柠檬水", "焙火铁观音", "苹果肉桂茶", "黑芝麻糊",
)
ALLERGENS = ("花生", "虾", "芒果", "乳胶", "青霉素", "猫毛", "尘螨", "腰果")
DOCUMENTS = ("护照", "港澳通行证", "驾照", "潜水证", "记者证", "职业资格证")


def build_dataset() -> dict[str, Any]:
    rng = random.Random(SEED)
    scopes: dict[str, Any] = {}
    memories: list[dict[str, Any]] = []
    entities: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    queries: list[dict[str, Any]] = []
    for index in range(SCOPE_COUNT):
        number = index + 1
        stem = f"u{number:02d}"
        scope = f"s{number:02d}"
        partition = _partition(index)
        style = {"dev": "explicit", "sealed": "paraphrase", "adversarial": "elliptical"}[
            partition
        ]
        owner = f"owner-{number:02d}"
        scopes[scope] = {
            "user_id": owner,
            "agent_id": "doppel-heterogeneous-eval",
            "partition": partition,
        }
        home = CITIES[index % len(CITIES)]
        temporary = CITIES[(index + 5) % len(CITIES)]
        friend_city = CITIES[(index + 9) % len(CITIES)]
        old_role = ROLES[index % len(ROLES)]
        new_role = ROLES[(index + 3) % len(ROLES)]
        item = ITEMS[index % len(ITEMS)]
        person = PEOPLE[index % len(PEOPLE)]
        drink = DRINKS[index % len(DRINKS)]
        allergen = ALLERGENS[index % len(ALLERGENS)]
        document = DOCUMENTS[index % len(DOCUMENTS)]
        trip_a = CITIES[(index + 2) % len(CITIES)]
        trip_b = CITIES[(index + 7) % len(CITIES)]
        cancelled = CITIES[(index + 11) % len(CITIES)]
        conv_a = f"{stem}-private-a"
        conv_b = f"{stem}-private-b"
        group = f"{stem}-group"

        ids = _core_memories(
            memories,
            scope=scope,
            stem=stem,
            owner=owner,
            conv_a=conv_a,
            conv_b=conv_b,
            group=group,
            home=home,
            temporary=temporary,
            old_role=old_role,
            new_role=new_role,
            trip_a=trip_a,
            trip_b=trip_b,
            cancelled=cancelled,
            item=item,
            person=person,
            friend_city=friend_city,
            document=document,
            drink=drink,
            allergen=allergen,
            expiry_year=2029 + index % 5,
        )
        _graph(
            entities,
            edges,
            scope=scope,
            stem=stem,
            owner=owner,
            item=item,
            person=person,
            friend_city=friend_city,
            ids=ids,
        )
        _queries(
            queries,
            scope=scope,
            stem=stem,
            owner=owner,
            partition=partition,
            style=style,
            conv_a=conv_a,
            conv_b=conv_b,
            home=home,
            temporary=temporary,
            old_role=old_role,
            new_role=new_role,
            trip_a=trip_a,
            trip_b=trip_b,
            cancelled=cancelled,
            item=item,
            person=person,
            friend_city=friend_city,
            document=document,
            drink=drink,
            allergen=allergen,
            expiry_year=2029 + index % 5,
            ids=ids,
        )
        _distractors(
            memories,
            rng,
            scope=scope,
            stem=stem,
            owner=owner,
            conv_a=conv_a,
            group=group,
            item=item,
            person=person,
            home=home,
            drink=drink,
            target_count=MEMORIES_PER_SCOPE,
        )

    return {
        "suite": "doppel-heterogeneous-retrieval-zh-v1",
        "version": "1.0.0",
        "language": "zh-CN",
        "status": "frozen",
        "frozen": True,
        "publication_ready": False,
        "seed": SEED,
        "description": (
            "Frozen synthetic personal-memory corpus with domain-diverse temporal, "
            "episodic, document, relation, cross-conversation, subject-correction, "
            "and related-but-insufficient evidence. No real personal data."
        ),
        "relation_types": ["HELD_BY", "LIVES_IN"],
        "scopes": scopes,
        "memories": memories,
        "entities": entities,
        "edges": edges,
        "queries": queries,
        "requirements": {
            "min_scopes": 48,
            "min_queries": 480,
            "min_memories": 9216,
            "min_memories_per_scope": 192,
            "min_queries_per_scope": 10,
            **{f"min_category_{name}": 48 for name in (
                "current_residence", "temporary_residence_as_of", "corrected_fact",
                "episode_count", "one_hop_relation", "two_hop_relation",
                "document_fact", "cross_conversation", "subject_correction",
                "no_answer_related",
            )},
            "min_domain_residence": 96,
            "min_domain_career": 48,
            "min_domain_travel": 48,
            "min_domain_possessions": 144,
            "min_domain_documents": 48,
            "min_domain_preferences": 48,
            "min_domain_health": 48,
            "min_partition_dev": 120,
            "min_partition_sealed": 280,
            "min_partition_adversarial": 80,
        },
    }


def _partition(index: int) -> str:
    if index < 12:
        return "dev"
    if index < 40:
        return "sealed"
    return "adversarial"


def _memory(
    memory_id: str,
    scope: str,
    conversation_id: str,
    content: str,
    subject_id: str,
    fact_key: str,
    *,
    source_kind: str = "chat",
    kind: str = "fact",
    event_key: str = "",
    temporal_status: str = "current",
    valid_from: str = "2024-01-01T00:00:00+08:00",
    valid_to: str = "",
    authority: str = "human_self",
    state: str = "confirmed",
) -> dict[str, Any]:
    return {
        "memory_id": memory_id,
        "scope": scope,
        "conversation_id": conversation_id,
        "source_kind": source_kind,
        "kind": kind,
        "content": content,
        "subject_id": subject_id,
        "fact_key": fact_key,
        "event_key": event_key,
        "temporal_status": temporal_status,
        "valid_from": valid_from,
        "valid_to": valid_to,
        "authority": authority,
        "state": state,
        "tags": ["personal-memory"],
        "evidence_id": f"evidence:{memory_id}",
    }


def _core_memories(target: list[dict[str, Any]], **v: Any) -> dict[str, str]:
    stem, scope, owner = v["stem"], v["scope"], v["owner"]
    ids = {name: f"m-{stem}-{name}" for name in (
        "home", "temporary", "old-role", "new-role", "trip-a", "trip-a-repeat",
        "trip-b", "trip-cancelled", "held-by", "friend-location", "document",
        "preference", "peer-allergy", "owner-no-allergy", "friend-allergy",
    )}
    target.extend((
        _memory(ids["home"], scope, v["conv_a"], f"我的长期常住地是{v['home']}。", owner, "residence:home"),
        _memory(ids["temporary"], scope, v["conv_b"], f"我临时到{v['temporary']}出差两个月，住到三月底。", owner, "residence:temporary", temporal_status="historical", valid_from="2026-02-01T00:00:00+08:00", valid_to="2026-04-01T00:00:00+08:00"),
        _memory(ids["old-role"], scope, v["conv_a"], f"我之前的职位记录为{v['old_role']}。", owner, "career:role", temporal_status="historical", valid_to="2025-07-01T00:00:00+08:00", state="superseded"),
        _memory(ids["new-role"], scope, v["conv_b"], f"更正一下，我现在的职位是{v['new_role']}。", owner, "career:role", valid_from="2025-07-01T00:00:00+08:00"),
        _memory(ids["trip-a"], scope, v["conv_a"], f"我在2025年春天去{v['trip_a']}旅行并按计划返程。", owner, "travel:completed", kind="episode", event_key=f"{stem}:trip-a", temporal_status="historical", valid_from="2025-03-10T00:00:00+08:00"),
        _memory(ids["trip-a-repeat"], scope, v["conv_b"], f"我又提到过去年春天那次{v['trip_a']}之行。", owner, "travel:completed", kind="episode", event_key=f"{stem}:trip-a", temporal_status="historical", valid_from="2025-03-10T00:00:00+08:00"),
        _memory(ids["trip-b"], scope, v["conv_b"], f"我在2025年秋天完成了一次{v['trip_b']}旅行。", owner, "travel:completed", kind="episode", event_key=f"{stem}:trip-b", temporal_status="historical", valid_from="2025-10-08T00:00:00+08:00"),
        _memory(ids["trip-cancelled"], scope, v["conv_a"], f"原计划去{v['cancelled']}的行程后来取消了。", owner, "travel:cancelled", kind="episode", event_key=f"{stem}:trip-cancelled", temporal_status="cancelled", valid_from="2025-12-01T00:00:00+08:00"),
        _memory(ids["held-by"], scope, v["conv_a"], f"我的{v['item']}目前放在{v['person']}那里。", owner, "possession:holder", kind="relation"),
        _memory(ids["friend-location"], scope, v["conv_b"], f"{v['person']}现在长期住在{v['friend_city']}。", owner, "contact:residence", kind="relation"),
        _memory(ids["document"], scope, v["conv_a"], f"文档记录：我的{v['document']}有效期到{v['expiry_year']}年8月。", owner, "document:expiry", source_kind="document", kind="document_fact"),
        _memory(ids["preference"], scope, v["conv_a"], f"我平时早餐最稳定的饮品是{v['drink']}。", owner, "preference:breakfast-drink", kind="preference", temporal_status="timeless"),
        _memory(ids["peer-allergy"], scope, v["group"], f"群友猜测我可能对{v['allergen']}过敏。", owner, "health:allergy", source_kind="group_chat", authority="peer_statement"),
        _memory(ids["owner-no-allergy"], scope, v["conv_b"], f"我明确说明：我对{v['allergen']}不过敏。", owner, "health:allergy"),
        _memory(ids["friend-allergy"], scope, v["group"], f"真正对{v['allergen']}过敏的是{v['person']}。", f"contact:{v['person']}", "health:allergy", source_kind="group_chat", authority="peer_statement"),
    ))
    return ids


def _graph(entities: list[dict[str, Any]], edges: list[dict[str, Any]], **v: Any) -> None:
    stem, scope = v["stem"], v["scope"]
    item_id, person_id, city_id = f"e-{stem}-item", f"e-{stem}-person", f"e-{stem}-city"
    entities.extend((
        {"entity_id": item_id, "scope": scope, "name": v["item"], "entity_type": "object"},
        {"entity_id": person_id, "scope": scope, "name": v["person"], "entity_type": "person"},
        {"entity_id": city_id, "scope": scope, "name": v["friend_city"], "entity_type": "place"},
    ))
    edges.extend((
        {"edge_id": f"edge-{stem}-held", "scope": scope, "source_entity_id": item_id, "target_entity_id": person_id, "relation_type": "HELD_BY", "fact": f"{v['item']}放在{v['person']}那里", "memory_id": v["ids"]["held-by"], "valid_at": "2024-01-01T00:00:00+08:00", "invalid_at": ""},
        {"edge_id": f"edge-{stem}-lives", "scope": scope, "source_entity_id": person_id, "target_entity_id": city_id, "relation_type": "LIVES_IN", "fact": f"{v['person']}住在{v['friend_city']}", "memory_id": v["ids"]["friend-location"], "valid_at": "2024-01-01T00:00:00+08:00", "invalid_at": ""},
    ))


def _queries(target: list[dict[str, Any]], **v: Any) -> None:
    base = {"partition": v["partition"], "query_style": v["style"], "scope": v["scope"], "conversation_id": v["conv_b"], "subject_id": v["owner"], "entity_mentions": [], "required_routes": [], "related_memory_ids": [], "hard_forbidden_memory_ids": [], "expected_count": None, "answerable": True}
    phrasing = _phrasings(v["partition"], v)
    rows = (
        ("current-residence", "current_residence", "residence", phrasing[0], "lookup", "current", "2026-06-01T12:00:00+08:00", [v["ids"]["home"]], [], [v["ids"]["temporary"]], [], None, True),
        ("temporary-asof", "temporary_residence_as_of", "residence", phrasing[1], "lookup", "as_of", "2026-03-15T12:00:00+08:00", [v["ids"]["temporary"]], [v["ids"]["home"]], [], [], None, True),
        ("corrected-role", "corrected_fact", "career", phrasing[2], "lookup", "current", "2026-06-01T12:00:00+08:00", [v["ids"]["new-role"]], [], [v["ids"]["old-role"]], [], None, True),
        ("travel-count", "episode_count", "travel", phrasing[3], "count", "history", "2026-06-01T12:00:00+08:00", [v["ids"]["trip-a"], v["ids"]["trip-b"]], [v["ids"]["trip-a-repeat"]], [v["ids"]["trip-cancelled"]], [], 2, True),
        ("holder", "one_hop_relation", "possessions", phrasing[4], "lookup", "current", "2026-06-01T12:00:00+08:00", [v["ids"]["held-by"]], [], [], [[{"relation_types": ["HELD_BY"], "direction": "outbound"}]], None, True),
        ("object-city", "two_hop_relation", "possessions", phrasing[5], "lookup", "current", "2026-06-01T12:00:00+08:00", [v["ids"]["held-by"], v["ids"]["friend-location"]], [], [], [[{"relation_types": ["HELD_BY"], "direction": "outbound"}, {"relation_types": ["LIVES_IN"], "direction": "outbound"}]], None, True),
        ("document", "document_fact", "documents", phrasing[6], "lookup", "current", "2026-06-01T12:00:00+08:00", [v["ids"]["document"]], [], [], [], None, True),
        ("cross-conversation", "cross_conversation", "preferences", phrasing[7], "lookup", "current", "2026-06-01T12:00:00+08:00", [v["ids"]["preference"]], [], [], [], None, True),
        ("subject-correction", "subject_correction", "health", phrasing[8], "lookup", "current", "2026-06-01T12:00:00+08:00", [v["ids"]["owner-no-allergy"]], [], [v["ids"]["peer-allergy"], v["ids"]["friend-allergy"]], [], None, True),
        ("buyer-unknown", "no_answer_related", "possessions", phrasing[9], "lookup", "current", "2026-06-01T12:00:00+08:00", [], [v["ids"]["held-by"]], [], [], None, False),
    )
    for suffix, category, domain, query, intent, temporal, valid_at, required, related, forbidden, routes, count, answerable in rows:
        item = dict(base)
        item.update({"case_id": f"q-{v['stem']}-{suffix}", "category": category, "domain": domain, "query": query, "intent": intent, "temporal_view": temporal, "valid_at": valid_at, "required_memory_ids": required, "related_memory_ids": related, "hard_forbidden_memory_ids": forbidden, "required_routes": routes, "expected_count": count, "answerable": answerable})
        if category in {"one_hop_relation", "two_hop_relation", "no_answer_related"}:
            item["entity_mentions"] = [v["item"]]
        target.append(item)


def _phrasings(partition: str, v: dict[str, Any]) -> tuple[str, ...]:
    token = v["stem"].upper()
    if partition == "dev":
        return (
            f"[{token}] 我现在的长期常住地是哪里？", f"[{token}] 2026年3月15日我临时住在哪里？",
            f"[{token}] 更正之后我现在的职位是什么？", f"[{token}] 去掉重复提及和取消计划，我完成过几次旅行？",
            f"[{token}] 我的{v['item']}现在由谁保管？", f"[{token}] 我的{v['item']}目前在哪座城市？",
            f"[{token}] 我的{v['document']}有效期到哪一年？", f"[{token}] 换了会话后再问，我早餐通常喝什么？",
            f"[{token}] 我本人对{v['allergen']}过敏吗？", f"[{token}] 这件{v['item']}是谁购买的？",
        )
    if partition == "sealed":
        return (
            f"[{token}] 出差结束后，平常说的家还是在哪儿？", f"[{token}] 回到那段出差期间看，3月中旬我落脚哪儿？",
            f"[{token}] 别用旧资料，我目前到底做什么职位？", f"[{token}] 同一次旅程别重复算，没成行的也别算，总共几趟？",
            f"[{token}] 那件{v['item']}我落在谁手上了？", f"[{token}] 想找回{v['item']}，最后应该去哪个城市？",
            f"[{token}] 文档里那份{v['document']}什么时候过期？", f"[{token}] 不看当前聊天，我固定的早餐饮品是什么？",
            f"[{token}] 群里说法不一致，我自己到底有没有{v['allergen']}过敏？", f"[{token}] 只知道{v['item']}在别人那里，能确定买它的人是谁吗？",
        )
    return (
        f"[{token}] 北京式临时落脚已经过去了，所以我的常住处究竟是哪？", f"[{token}] 别按今天答，倒回2026-03-15那天我住哪？",
        f"[{token}] 旧职位那条作废后，现在那条是什么？", f"[{token}] 提过两遍算一趟，取消算零趟——我实际去了多少次？",
        f"[{token}] {v['item']}不在我这儿，当前拿着它的是谁？", f"[{token}] 沿着“东西在谁那、那人住哪”找，{v['item']}在哪座城？",
        f"[{token}] 别凭聊天猜，查文档：{v['document']}哪年失效？", f"[{token}] 这是另一个会话，但我早饭喝什么的习惯应当没变吧？",
        f"[{token}] 说过敏的不是我本人吧？请按主体纠正后回答{v['allergen']}这件事。", f"[{token}] 保管人不等于购买人；现有记忆能回答{v['item']}是谁买的吗？",
    )


def _distractors(target: list[dict[str, Any]], rng: random.Random, **v: Any) -> None:
    existing = sum(item["scope"] == v["scope"] for item in target)
    topics = (
        lambda n: f"{v['person']}在群里提过第{n}份早餐清单。",
        lambda n: f"我把第{n}张旅行票据收进了资料夹，但没有新增旅行。",
        lambda n: f"未来也许会换到{CITIES[(n + 3) % len(CITIES)]}，目前没有决定。",
        lambda n: f"关于{v['item']}的第{n}条维护备注没有说明购买者。",
        lambda n: f"朋友喜欢喝{v['drink']}，这不是我的早餐习惯。",
        lambda n: f"第{n}个收纳盒贴着蓝色标签。",
        lambda n: f"我浏览过一篇介绍{v['home']}旅行路线的文章。",
        lambda n: f"系统曾生成第{n}条未经确认的个人资料摘要。",
    )
    for offset in range(int(v["target_count"]) - existing):
        number = offset + 1
        topic_index = rng.randrange(len(topics))
        authority = "agent_output" if number % 17 == 0 else (
            "peer_statement" if number % 11 == 0 else "human_self"
        )
        state = "expired" if number % 19 == 0 else (
            "candidate" if number % 23 == 0 else "confirmed"
        )
        target.append(
            _memory(
                f"m-{v['stem']}-distractor-{number:03d}",
                v["scope"],
                v["group"] if number % 3 == 0 else v["conv_a"],
                topics[topic_index](number),
                v["owner"] if number % 5 else f"contact:{v['person']}",
                f"distractor:{topic_index}:{number}",
                source_kind="group_chat" if number % 3 == 0 else "chat",
                temporal_status="planned" if topic_index == 2 else "timeless",
                authority=authority,
                state=state,
            )
        )


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
