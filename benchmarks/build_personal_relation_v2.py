"""Build the reviewed-shape draft of the expanded personal relation dataset.

The generator keeps scenario semantics, partition assignment, and relevance labels
outside runtime code. Generated output is checked in so benchmark runs never need to
execute this module. Use ``--check`` in CI to detect manual/generated drift.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

OUTPUT = Path(__file__).parent / "datasets" / "personal-relation-ablation-zh-v2.json"
NOW = "2026-09-15T12:00:00Z"
ALL_RELATION_TYPES = [
    "ADOPTED_FROM",
    "BORROWED_FROM",
    "CARED_FOR_BY",
    "COPIED_BY",
    "GIFTED_BY",
    "HELD_BY",
    "ISSUED_BY",
    "LOCATED_AT",
    "PURCHASED_AT",
    "RECOMMENDED_BY",
    "REPAIRED_AT",
    "REPAIRED_BY",
    "SIGNED_WITH",
    "STORED_IN",
]

SCOPES = {
    f"owner_{index:02d}": {
        "user_id": f"relation-v2-owner-{index:02d}",
        "agent_id": "echo",
        "display_name": f"owner-{index:02d}",
    }
    for index in range(1, 13)
}

PRIMARY_LANGUAGE = {
    "STORED_IN": {
        "current": "{entity}目前收在{target}。",
        "history": "{entity}以前收在{target}，后来已经移走。",
        "fact_current": "{entity}当前存放在{target}。",
        "fact_history": "{entity}过去存放在{target}。",
        "question": ("存放在哪里", "收在哪儿"),
        "hint": ("存放", "收在哪儿"),
    },
    "LOCATED_AT": {
        "current": "{entity}目前放在{target}。",
        "history": "{entity}以前放在{target}，后来已经移走。",
        "fact_current": "{entity}当前位于{target}。",
        "fact_history": "{entity}过去位于{target}。",
        "question": ("放在哪里", "搁哪儿了"),
        "hint": ("放在哪里", "搁哪儿"),
    },
    "HELD_BY": {
        "current": "{entity}目前交给{target}代为保管。",
        "history": "{entity}以前由{target}保管，后来已经取回。",
        "fact_current": "{entity}当前由{target}保管，在{target}手里。",
        "fact_history": "{entity}过去由{target}保管，当时在{target}手里。",
        "question": ("由谁保管", "在谁手里"),
        "hint": ("保管", "在谁手里"),
    },
    "CARED_FOR_BY": {
        "current": "{entity}目前由{target}负责照护和复诊。",
        "history": "{entity}以前由{target}负责照护，之后已经转诊。",
        "fact_current": "{entity}当前由{target}负责照护。",
        "fact_history": "{entity}过去由{target}负责照护。",
        "question": ("由谁负责照护", "现在谁在照看"),
        "hint": ("照护", "照看"),
    },
}

SECONDARY_LANGUAGE = {
    "ISSUED_BY": {
        "content": "{entity}由{target}签发。",
        "fact": "{entity}的签发机构是{target}。",
        "question": ("由哪个机构签发", "是哪儿签发的"),
        "hint": ("签发", "哪儿签发"),
        "label": "签发机构",
    },
    "REPAIRED_BY": {
        "content": "{entity}上次由{target}负责维修。",
        "fact": "{entity}由{target}维修。",
        "question": ("上次由谁维修", "之前是谁修的"),
        "hint": ("维修", "谁修的"),
        "label": "维修人",
    },
    "RECOMMENDED_BY": {
        "content": "{entity}是{target}推荐给我的。",
        "fact": "{entity}由{target}推荐。",
        "question": ("是谁推荐的", "当初谁给我安利的"),
        "hint": ("推荐", "安利"),
        "label": "推荐人",
    },
    "COPIED_BY": {
        "content": "{entity}是在{target}配制的。",
        "fact": "{entity}由{target}配制。",
        "question": ("是哪家店配的", "当初找谁配的"),
        "hint": ("配制", "找谁配"),
        "label": "配制店",
    },
    "SIGNED_WITH": {
        "content": "{entity}是与{target}签订的。",
        "fact": "{entity}的签约对方是{target}。",
        "question": ("是和谁签的", "签约对方是谁"),
        "hint": ("签约", "和谁签"),
        "label": "签约对方",
    },
    "REPAIRED_AT": {
        "content": "{entity}上次是在{target}维修的。",
        "fact": "{entity}曾在{target}维修。",
        "question": ("上次在哪里维修", "之前在哪儿修过"),
        "hint": ("维修地点", "哪儿修过"),
        "label": "维修地点",
    },
    "ADOPTED_FROM": {
        "content": "{entity}是从{target}领养的。",
        "fact": "{entity}领养自{target}。",
        "question": ("是从哪里领养的", "当初从哪儿抱回来的"),
        "hint": ("领养", "抱回来"),
        "label": "领养来源",
    },
    "PURCHASED_AT": {
        "content": "{entity}是在{target}购买的。",
        "fact": "{entity}购买自{target}。",
        "question": ("是在哪里购买的", "当时在哪家店买的"),
        "hint": ("购买地点", "哪家店买"),
        "label": "购买地点",
    },
    "GIFTED_BY": {
        "content": "{entity}是{target}送给我的礼物。",
        "fact": "{entity}由{target}赠送。",
        "question": ("是谁送给我的", "当初是谁送的"),
        "hint": ("赠送", "谁送的"),
        "label": "赠送人",
    },
}

# Each entity appears in two exact owner scopes with different answers. This produces
# cross-owner collision pressure without making any query depend on a user name.
ARCHETYPES = [
    {
        "entity": "护照",
        "primary": "STORED_IN",
        "current": ["银行保险箱", "卧室衣柜上层抽屉"],
        "history": ["书房文件柜", "家中书桌抽屉"],
        "secondary": "ISSUED_BY",
        "secondary_target": ["上海市出入境管理局", "杭州市出入境管理局"],
    },
    {
        "entity": "单反相机",
        "primary": "LOCATED_AT",
        "current": ["工作室器材柜", "学校宿舍储物柜"],
        "history": ["家中书房", "摄影社活动室"],
        "secondary": "REPAIRED_BY",
        "secondary_target": ["光影维修中心周师傅", "镜界相机店赵师傅"],
    },
    {
        "entity": "《海边的卡夫卡》",
        "primary": "HELD_BY",
        "current": ["周恺", "许宁"],
        "history": ["李雯", "韩梅"],
        "secondary": "RECOMMENDED_BY",
        "secondary_target": ["王欣", "蒋晨"],
    },
    {
        "entity": "备用钥匙",
        "primary": "HELD_BY",
        "current": ["陈航", "小区物业前台"],
        "history": ["同事林青", "邻居何晓"],
        "secondary": "COPIED_BY",
        "secondary_target": ["安心锁业", "百顺配钥匙店"],
    },
    {
        "entity": "租房合同原件",
        "primary": "STORED_IN",
        "current": ["公司保险柜", "客厅文件箱"],
        "history": ["蓝色文件袋", "书房第二层抽屉"],
        "secondary": "SIGNED_WITH",
        "secondary_target": ["房东赵女士", "房东孙先生"],
    },
    {
        "entity": "折叠自行车",
        "primary": "LOCATED_AT",
        "current": ["赵晨家车库", "单位地下车棚"],
        "history": ["自家阳台", "父母家储藏室"],
        "secondary": "REPAIRED_AT",
        "secondary_target": ["瑞兴车行", "风驰单车工坊"],
    },
    {
        "entity": "豆包",
        "primary": "CARED_FOR_BY",
        "current": ["安和宠物医院李医生", "青禾动物诊所吴医生"],
        "history": ["仁爱宠物医院王医生", "城南动物医院郑医生"],
        "secondary": "ADOPTED_FROM",
        "secondary_target": ["环城流浪动物救助站", "暖窝动物救助中心"],
    },
    {
        "entity": "旧笔记本电脑",
        "primary": "LOCATED_AT",
        "current": ["远航维修店", "办公室设备间"],
        "history": ["家中书桌", "大学宿舍"],
        "secondary": "REPAIRED_BY",
        "secondary_target": ["远航维修店高师傅", "迅捷电脑城刘师傅"],
    },
    {
        "entity": "医保卡",
        "primary": "STORED_IN",
        "current": ["黑色证件盒", "随身钱包夹层"],
        "history": ["床头柜抽屉", "办公室文件袋"],
        "secondary": "ISSUED_BY",
        "secondary_target": ["浦东新区社保中心", "西湖区社保中心"],
    },
    {
        "entity": "木吉他",
        "primary": "HELD_BY",
        "current": ["音乐老师顾言", "乐队成员陆川"],
        "history": ["朋友陈曦", "琴行老板郑宇"],
        "secondary": "PURCHASED_AT",
        "secondary_target": ["和声乐器行", "弦音琴行"],
    },
    {
        "entity": "银色行李箱",
        "primary": "LOCATED_AT",
        "current": ["父母家储物间", "公司行政仓库"],
        "history": ["自家阁楼", "机场寄存处"],
        "secondary": "GIFTED_BY",
        "secondary_target": ["姐姐林悦", "朋友苏然"],
    },
    {
        "entity": "研究生毕业证",
        "primary": "STORED_IN",
        "current": ["银行保管箱", "书房防火文件柜"],
        "history": ["宿舍行李箱", "父母家书柜"],
        "secondary": "ISSUED_BY",
        "secondary_target": ["华东理工大学", "浙江工业大学"],
    },
]

UNKNOWN_ENTITIES = [
    "航拍无人机",
    "蓝色档案盒",
    "备用手机",
    "祖传怀表",
    "健身房门卡",
    "露营帐篷",
    "宠物疫苗本",
    "机械键盘",
    "体检报告原件",
    "电子琴",
    "红色登机箱",
    "本科成绩单",
    "运动相机",
    "绿色资料袋",
    "旧平板电脑",
    "纪念钢笔",
    "车库遥控器",
    "滑雪板",
    "宠物定位器",
    "移动硬盘",
    "商业保险合同",
    "尤克里里",
    "黑色旅行包",
    "学位认证书",
]


def _memory(
    *,
    scenario: int,
    suffix: str,
    scope: str,
    entity: str,
    relation_type: str,
    target: str,
    content: str,
    fact: str,
    temporal_status: str,
    state: str,
    valid_from: str,
    valid_to: str | None = None,
) -> dict[str, Any]:
    memory_id = f"v2-s{scenario:02d}-{suffix}"
    result: dict[str, Any] = {
        "memory_id": memory_id,
        "scope": scope,
        "content": content,
        "personal_memory_type": "fact" if suffix == "secondary" else "state",
        "temporal_status": temporal_status,
        "state": state,
        "valid_from": valid_from,
        "topic_key": f"relation.{scenario:02d}.{relation_type.lower()}",
        "evidence": [
            {
                "message_id": f"v2-msg-s{scenario:02d}-{suffix}",
                "at": valid_from,
            }
        ],
        "relation": {
            "source_entity": entity,
            "relation_type": relation_type,
            "target_entity": target,
            "fact": fact,
        },
    }
    if valid_to is not None:
        result["valid_to"] = valid_to
    return result


def _scenario_rows() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    fixtures: list[dict[str, Any]] = []
    scenarios: list[dict[str, Any]] = []
    for occurrence in range(2):
        for archetype_index, archetype in enumerate(ARCHETYPES):
            scenario = occurrence * len(ARCHETYPES) + archetype_index + 1
            scope_number = (
                archetype_index + 1
                if occurrence == 0
                else ((archetype_index + 5) % len(ARCHETYPES)) + 1
            )
            scope = f"owner_{scope_number:02d}"
            entity = archetype["entity"]
            primary_type = archetype["primary"]
            secondary_type = archetype["secondary"]
            current_target = archetype["current"][occurrence]
            history_target = archetype["history"][occurrence]
            secondary_target = archetype["secondary_target"][occurrence]
            primary = PRIMARY_LANGUAGE[primary_type]
            secondary = SECONDARY_LANGUAGE[secondary_type]
            ids = {
                "current": f"v2-s{scenario:02d}-primary-current",
                "history": f"v2-s{scenario:02d}-primary-history",
                "secondary": f"v2-s{scenario:02d}-secondary",
            }
            fixtures.extend(
                [
                    _memory(
                        scenario=scenario,
                        suffix="primary-current",
                        scope=scope,
                        entity=entity,
                        relation_type=primary_type,
                        target=current_target,
                        content=primary["current"].format(
                            entity=entity, target=current_target
                        ),
                        fact=primary["fact_current"].format(
                            entity=entity, target=current_target
                        ),
                        temporal_status="current",
                        state="confirmed",
                        valid_from="2026-04-01T00:00:00Z",
                    ),
                    _memory(
                        scenario=scenario,
                        suffix="primary-history",
                        scope=scope,
                        entity=entity,
                        relation_type=primary_type,
                        target=history_target,
                        content=primary["history"].format(
                            entity=entity, target=history_target
                        ),
                        fact=primary["fact_history"].format(
                            entity=entity, target=history_target
                        ),
                        temporal_status="historical",
                        state="superseded",
                        valid_from="2025-01-01T00:00:00Z",
                        valid_to="2026-03-31T23:59:59Z",
                    ),
                    _memory(
                        scenario=scenario,
                        suffix="secondary",
                        scope=scope,
                        entity=entity,
                        relation_type=secondary_type,
                        target=secondary_target,
                        content=secondary["content"].format(
                            entity=entity, target=secondary_target
                        ),
                        fact=secondary["fact"].format(
                            entity=entity, target=secondary_target
                        ),
                        temporal_status="timeless",
                        state="confirmed",
                        valid_from="2025-06-01T00:00:00Z",
                    ),
                ]
            )
            scenarios.append(
                {
                    "scenario": scenario,
                    "scope": scope,
                    "entity": entity,
                    "occurrence": occurrence,
                    "primary_type": primary_type,
                    "secondary_type": secondary_type,
                    "primary": primary,
                    "secondary": secondary,
                    "ids": ids,
                }
            )
    return fixtures, scenarios


def _query_base(
    scenario: dict[str, Any],
    number: int,
    *,
    text: str,
    intent: str,
    relation_type: str,
    relation_hint: str,
    partition: str,
    category: str,
) -> dict[str, Any]:
    return {
        "query_id": f"v2-s{scenario['scenario']:02d}-q{number:02d}",
        "query": text,
        "scopes": [scenario["scope"]],
        "now": NOW,
        "intent": intent,
        "entity_mentions": [scenario["entity"]],
        "relation_hints": [relation_hint],
        "category": category,
        "partition": partition,
        "_relation_type": relation_type,
    }


def _scenario_queries(scenario: dict[str, Any], unknown_entity: str) -> list[dict[str, Any]]:
    entity = scenario["entity"]
    occurrence = scenario["occurrence"]
    primary = scenario["primary"]
    secondary = scenario["secondary"]
    ids = scenario["ids"]
    primary_question = primary["question"][occurrence]
    primary_hint = primary["hint"][occurrence]
    secondary_question = secondary["question"][occurrence]
    secondary_hint = secondary["hint"][occurrence]
    current_text = (
        f"我的{entity}现在{primary_question}？"
        if occurrence == 0
        else f"{entity}目前到底{primary_question}？"
    )
    paraphrase_text = (
        f"我一时想不起来，{entity}这会儿{primary_question}？"
        if occurrence == 0
        else f"帮我回忆一下，{entity}眼下{primary_question}？"
    )
    history_text = (
        f"我的{entity}之前{primary_question}？"
        if occurrence == 0
        else f"{entity}先前{primary_question}？"
    )
    as_of_day = "2026年3月15日" if occurrence == 0 else "2026年2月20日"
    as_of_text = f"{as_of_day}{entity}{primary_question}？"
    secondary_text = (
        f"{entity}{secondary_question}？"
        if occurrence == 0
        else f"说到{entity}，它{secondary_question}？"
    )
    secondary_paraphrase = (
        f"我忘了{entity}{secondary_question}，帮我找一下。"
        if occurrence == 0
        else f"翻翻记忆，{entity}{secondary_question}来着？"
    )
    contrast_text = (
        f"不是问{secondary['label']}，我是问{entity}现在{primary_question}？"
        if occurrence == 0
        else f"先别说{secondary['label']}，{entity}目前{primary_question}？"
    )
    borrowed_text = (
        f"{entity}是从谁那里借来的？"
        if occurrence == 0
        else f"当初是谁把{entity}借给我的？"
    )
    unknown_text = (
        f"{unknown_entity}现在{primary['question'][0]}？"
        if occurrence == 0
        else f"我那个{unknown_entity}目前{primary['question'][1]}？"
    )
    interval_text = (
        f"2025年我的{entity}{primary_question}？"
        if occurrence == 0
        else f"在2025年，{entity}当时{primary_question}？"
    )

    rows = [
        _query_base(
            scenario,
            1,
            text=current_text,
            intent="current",
            relation_type=scenario["primary_type"],
            relation_hint=primary_hint,
            partition="dev",
            category="current_relation",
        ),
        _query_base(
            scenario,
            2,
            text=paraphrase_text,
            intent="current",
            relation_type=scenario["primary_type"],
            relation_hint=primary_hint,
            partition="heldout",
            category="semantic_paraphrase",
        ),
        _query_base(
            scenario,
            3,
            text=history_text,
            intent="history",
            relation_type=scenario["primary_type"],
            relation_hint=primary_hint,
            partition="heldout",
            category="history_relation",
        ),
        _query_base(
            scenario,
            4,
            text=as_of_text,
            intent="as_of",
            relation_type=scenario["primary_type"],
            relation_hint=primary_hint,
            partition="adversarial",
            category="temporal_boundary",
        ),
        _query_base(
            scenario,
            5,
            text=secondary_text,
            intent="lookup",
            relation_type=scenario["secondary_type"],
            relation_hint=secondary_hint,
            partition="dev",
            category="same_entity_multi_relation",
        ),
        _query_base(
            scenario,
            6,
            text=secondary_paraphrase,
            intent="lookup",
            relation_type=scenario["secondary_type"],
            relation_hint=secondary_hint,
            partition="heldout",
            category="semantic_paraphrase",
        ),
        _query_base(
            scenario,
            7,
            text=contrast_text,
            intent="current",
            relation_type=scenario["primary_type"],
            relation_hint=primary_hint,
            partition="adversarial",
            category="negated_relation_contrast",
        ),
        _query_base(
            scenario,
            8,
            text=borrowed_text,
            intent="lookup",
            relation_type="BORROWED_FROM",
            relation_hint="借来",
            partition="adversarial",
            category="related_but_insufficient",
        ),
        _query_base(
            scenario,
            9,
            text=unknown_text,
            intent="current",
            relation_type=scenario["primary_type"],
            relation_hint=primary_hint,
            partition="heldout",
            category="unknown_entity",
        ),
        _query_base(
            scenario,
            10,
            text=interval_text,
            intent="history",
            relation_type=scenario["primary_type"],
            relation_hint=primary_hint,
            partition="dev",
            category="historical_interval_relation",
        ),
    ]

    for number, row in enumerate(rows, start=1):
        if number in {1, 2, 7}:
            row["required_memory_ids"] = [ids["current"]]
            row["_grade_kind"] = "current"
        elif number in {3, 4, 10}:
            row["required_memory_ids"] = [ids["history"]]
            row["_grade_kind"] = "history"
        elif number in {5, 6}:
            row["required_memory_ids"] = [ids["secondary"]]
            row["_grade_kind"] = "secondary"
        elif number == 8:
            row["expected_abstain"] = True
            row["abstain_reason"] = (
                "No direct borrowing evidence; same-entity memories remain useful "
                "grade-1 context and are not security failures."
            )
            row["_grade_kind"] = "context"
        else:
            row["entity_mentions"] = [unknown_entity]
            row["expected_abstain"] = True
            row["abstain_reason"] = "No memory exists for the explicitly named entity."
            row["_grade_kind"] = "unknown"
        if number == 4:
            row["as_of"] = (
                "2026-03-15T12:00:00Z"
                if occurrence == 0
                else "2026-02-20T12:00:00Z"
            )
            row["accepted_intents"] = ["as_of", "history"]
            row["accept_interval_covering_as_of"] = True
        if number == 10:
            row["time_from"] = "2025-01-01T00:00:00Z"
            row["time_to"] = "2025-12-31T23:59:59Z"
    return rows


def build_dataset() -> dict[str, Any]:
    fixtures, scenarios = _scenario_rows()
    fixture_ids = [item["memory_id"] for item in fixtures]
    fixture_by_id = {item["memory_id"]: item for item in fixtures}
    queries: list[dict[str, Any]] = []
    relation_type_labels: dict[str, list[str]] = {}

    for scenario, unknown_entity in zip(scenarios, UNKNOWN_ENTITIES, strict=True):
        local_ids = set(scenario["ids"].values())
        cross_scope_ids = {
            item["memory_id"]
            for item in fixtures
            if item["relation"]["source_entity"] == scenario["entity"]
            and item["scope"] != scenario["scope"]
        }
        for row in _scenario_queries(scenario, unknown_entity):
            grade_kind = row.pop("_grade_kind")
            relation_type = row.pop("_relation_type")
            relation_type_labels[row["query_id"]] = [relation_type]
            grades = {memory_id: 0 for memory_id in fixture_ids}
            forbidden = set(cross_scope_ids)
            if grade_kind != "unknown":
                for memory_id in local_ids:
                    grades[memory_id] = 1
            if grade_kind == "current":
                grades[scenario["ids"]["current"]] = 2
                grades[scenario["ids"]["history"]] = 0
                forbidden.add(scenario["ids"]["history"])
            elif grade_kind == "history":
                grades[scenario["ids"]["history"]] = 2
                grades[scenario["ids"]["current"]] = 0
                forbidden.add(scenario["ids"]["current"])
            elif grade_kind == "secondary":
                grades[scenario["ids"]["secondary"]] = 2
            elif grade_kind == "context":
                # Related evidence can orient an answer model but cannot prove who
                # lent the item. This is deliberately grade 1 rather than forbidden.
                pass
            if row["query_id"].endswith("q07"):
                grades[scenario["ids"]["secondary"]] = 0
                forbidden.add(scenario["ids"]["secondary"])
            row["forbidden_memory_ids"] = sorted(forbidden)
            row["relevance_grades"] = grades
            queries.append(row)

    assert len(fixtures) == 72
    assert len(queries) == 240
    assert all(memory_id in fixture_by_id for memory_id in fixture_ids)
    return {
        "suite": "doppel-personal-relation-ablation-zh-v2",
        "suite_version": "2.0.0-draft.1",
        "language": "zh-CN",
        "status": "draft",
        "frozen": False,
        "publication_ready": False,
        "description": (
            "Expanded personal-Agent relation retrieval draft with 12 exact owner "
            "scopes, temporal state transitions, same-entity multi-relation context, "
            "cross-owner collisions, explicit negation, unknown entities, and complete "
            "0/1/2 corpus judgments. Generated labels require independent semantic "
            "review before freezing; no extraction or LLM output is involved."
        ),
        "relation_types": ALL_RELATION_TYPES,
        "relation_type_labels": relation_type_labels,
        "scopes": SCOPES,
        "fixtures": fixtures,
        "queries": queries,
        "requirements": {
            "relation_benchmark": True,
            "min_queries": 240,
            "min_scopes": 12,
            "complete_relevance_judgments": True,
            "complete_relation_type_labels": True,
            "validate_direct_relation_evidence": True,
            "relevance_rubric": "0=irrelevant_or_unauthorized;1=related_context_not_proof;2=direct_answer_evidence",
            "related_context_categories": ["related_but_insufficient"],
            "partition_minimums": {"dev": 72, "heldout": 96, "adversarial": 72},
            "partition_assignment": "fixed_by_query_position_before_runtime_evaluation",
            "zero_paid_llm_calls": True,
            "required_profiles": [
                "lexical",
                "lexical_vector",
                "lexical_relation",
                "lexical_vector_relation",
            ],
        },
    }


def _serialized() -> str:
    return json.dumps(build_dataset(), ensure_ascii=False, indent=2) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--check",
        action="store_true",
        help="fail when the checked-in dataset differs from deterministic output",
    )
    args = parser.parse_args()
    expected = _serialized()
    if args.check:
        if not OUTPUT.exists() or OUTPUT.read_text(encoding="utf-8") != expected:
            raise SystemExit("generated v2 relation dataset is out of date")
        return 0
    OUTPUT.write_text(expected, encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
