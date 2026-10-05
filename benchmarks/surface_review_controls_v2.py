"""Versioned development extensions; original V1 input/gold remains immutable."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from benchmarks.surface_review_controls import ReviewControl, _entity, _memory, _query
from benchmarks.surface_review_controls import build_controls as build_v1_controls

GOLD_REVISION = "review-control-gold.v2"


def build_controls() -> list[ReviewControl]:
    controls = []
    for original in build_v1_controls():
        # Lifecycle contradictions may properly be reported as temporal mismatches.
        # Change only this family's scorer taxonomy, NOT its surface or V1 result.
        codes = list(original.allowed_issue_codes)
        if (
            original.family == "return_and_readoption_lifecycle"
            and not original.acceptable
        ):
            codes.append("temporal_mismatch")
        controls.append(
            original.model_copy(deep=True, update={"allowed_issue_codes": codes})
        )

    def pair(
        family: str,
        good: dict[str, Any],
        bad: dict[str, Any],
        key: str,
        codes: list[str],
    ) -> None:
        number = len(controls) // 2 + 1
        variants = (
            [(True, good), (False, bad)] if number % 2 else [(False, bad), (True, good)]
        )
        for acceptable, content in variants:
            controls.append(
                ReviewControl(
                    case_id=f"review-control-{len(controls) + 1:02d}",
                    family=family,
                    pair_id=f"pair-{number:02d}",
                    reviewer_input=content,
                    acceptable=acceptable,
                    allowed_issue_keys=[] if acceptable else [key],
                    allowed_issue_codes=[] if acceptable else codes,
                )
            )

    def question(brief: str, text: str) -> dict[str, Any]:
        return {"entities": [], "memories": [], "queries": [_query(brief, text)]}

    pair(
        "positive_candidate_confirmation",
        question("开放询问主人当前是否持有驾照，不给出真值结论。", "我现在有驾照吗？"),
        question(
            "开放询问主人当前是否持有驾照，不给出真值结论。", "我现在有驾照，没记错吧？"
        ),
        "query-a",
        ["answer_leak"],
    )
    pair(
        "negative_candidate_confirmation",
        question(
            "询问主人对乳制品是否不耐受，不给出肯定或否定结论。",
            "我对乳制品会不会不耐受？",
        ),
        question(
            "询问主人对乳制品是否不耐受，不给出肯定或否定结论。",
            "我对乳制品并不属于不耐受，对吧？",
        ),
        "query-a",
        ["answer_leak"],
    )
    pair(
        "permitted_confirmation_contract",
        question(
            "允许确认式提问：询问青色背包是否由许禾购买，问句可带候选购买者；不宣布答案是否存在。",
            "青色背包是许禾买的，对吗？",
        ),
        question(
            "允许确认式提问：询问青色背包是否由许禾购买，问句可带候选购买者；不宣布答案是否存在。",
            "没有青色背包购买者的记录，肯定无法回答，是吧？",
        ),
        "query-a",
        ["answer_leak", "semantic_drift"],
    )

    def relation(
        source_name: str, target_name: str, kind: str, content: str, edge: str
    ) -> dict[str, Any]:
        if kind == "HELD_BY":
            entities = [
                _entity("entity-a", source_name, "object", "需要保管的物品。"),
                _entity("entity-b", target_name, "person", "保管物品的人。"),
            ]
            brief = "源物品由目标人物保管，不改变物品和保管人的角色。"
        else:
            entities = [
                _entity("entity-a", source_name, "person", "任职者。"),
                _entity("entity-b", target_name, "organization", "任职机构。"),
            ]
            brief = "源人物在目标机构任职，不颠倒任职者和机构的角色。"
        return {
            "entities": entities,
            "queries": [],
            "memories": [
                _memory(
                    "memory-a",
                    brief,
                    content,
                    edge=edge,
                    relation={
                        "type": kind,
                        "source_entity_key": "entity-a",
                        "target_entity_key": "entity-b",
                    },
                )
            ],
        }

    pair(
        "passive_and_active_custody",
        relation(
            "红色测距仪",
            "顾秋",
            "HELD_BY",
            "顾秋保管着红色测距仪。",
            "红色测距仪被顾秋保管着。",
        ),
        relation(
            "红色测距仪",
            "顾秋",
            "HELD_BY",
            "红色测距仪保管着顾秋。",
            "顾秋被红色测距仪保管着。",
        ),
        "memory-a",
        [
            "relation_mismatch",
            "semantic_drift",
            "entity_inconsistent",
            "unnatural_language",
        ],
    )
    pair(
        "fronted_workplace_roles",
        relation(
            "罗晴",
            "星野工作室",
            "WORKS_AT",
            "在星野工作室任职的人是罗晴。",
            "罗晴任职于星野工作室。",
        ),
        relation(
            "罗晴",
            "星野工作室",
            "WORKS_AT",
            "在罗晴任职的是星野工作室。",
            "星野工作室任职于罗晴。",
        ),
        "memory-a",
        [
            "relation_mismatch",
            "semantic_drift",
            "entity_inconsistent",
            "unnatural_language",
        ],
    )
    good = relation(
        "黄色相机",
        "宋远",
        "HELD_BY",
        "宋远那里保管着黄色相机。",
        "黄色相机交给宋远保管。",
    )
    bad = deepcopy(good)
    bad["memories"][0]["authored_edge_fact"] = "黄色相机那里保管着宋远。"
    pair(
        "independent_content_edge_roles",
        good,
        bad,
        "memory-a",
        [
            "relation_mismatch",
            "semantic_drift",
            "entity_inconsistent",
            "unnatural_language",
        ],
    )
    return controls
