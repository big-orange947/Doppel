"""Build the independent natural-language relation-path Planner draft."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

Step = tuple[str, str]
Case = tuple[
    str,
    str,
    str,
    str,
    tuple[str, ...],
    tuple[Step, ...],
    tuple[str, ...],
    tuple[str, ...],
]


CASES: tuple[Case, ...] = (
    (
        "p01",
        "dev",
        "two_hop",
        "先找出现在保管相机的人，再查那个人现在位于哪里。",
        ("相机",),
        (("HELD_BY", "outbound"), ("LOCATED_AT", "outbound")),
        ("explicit_chain",),
        ("OWNED_BY", "PURCHASED_BY"),
    ),
    (
        "p02",
        "heldout",
        "two_hop",
        "从护照查到签发机关，然后告诉我该机关位于哪里。",
        ("护照",),
        (("ISSUED_BY", "outbound"), ("LOCATED_AT", "outbound")),
        ("explicit_chain",),
        ("HELD_BY",),
    ),
    (
        "p03",
        "dev",
        "two_hop",
        "先看这本书是谁推荐的，再查推荐人受雇于哪家机构。",
        ("书",),
        (("RECOMMENDED_BY", "outbound"), ("EMPLOYED_BY", "outbound")),
        ("explicit_chain",),
        ("PURCHASED_BY",),
    ),
    (
        "p04",
        "heldout",
        "two_hop",
        "先确定谁在照顾豆包，再找出照顾人现在的位置。",
        ("豆包",),
        (("CARED_FOR_BY", "outbound"), ("LOCATED_AT", "outbound")),
        ("explicit_chain",),
        ("OWNED_BY",),
    ),
    (
        "p05",
        "adversarial",
        "two_hop",
        "沿着旧画的修复者继续查，修复者目前位于哪里？",
        ("旧画",),
        (("REPAIRED_BY", "outbound"), ("LOCATED_AT", "outbound")),
        ("explicit_chain", "nearby_relation"),
        ("REPAIRED_AT",),
    ),
    (
        "p06",
        "heldout",
        "two_hop",
        "先查礼物的购买者，再查购买者现在在哪里。",
        ("礼物",),
        (("PURCHASED_BY", "outbound"), ("LOCATED_AT", "outbound")),
        ("explicit_chain", "nearby_relation"),
        ("PURCHASED_AT", "OWNED_BY"),
    ),
    (
        "p07",
        "dev",
        "two_hop",
        "从相机包找到借用人，然后查借用人的当前位置。",
        ("相机包",),
        (("LOANED_TO", "outbound"), ("LOCATED_AT", "outbound")),
        ("explicit_chain", "nearby_relation"),
        ("HELD_BY", "OWNED_BY"),
    ),
    (
        "p08",
        "adversarial",
        "two_hop",
        "文件存在哪个柜子里？再查那个柜子位于哪里。",
        ("文件",),
        (("STORED_IN", "outbound"), ("LOCATED_AT", "outbound")),
        ("explicit_chain", "nearby_relation"),
        ("HELD_BY",),
    ),
    (
        "p09",
        "heldout",
        "two_hop",
        "从小王反向找出由他保管的物品，再查物品存在哪个容器里。",
        ("小王",),
        (("HELD_BY", "inbound"), ("STORED_IN", "outbound")),
        ("explicit_chain", "inbound"),
        ("OWNED_BY",),
    ),
    (
        "p10",
        "dev",
        "two_hop",
        "先找出由星海维修处理的设备，再查每台设备现在归谁所有。",
        ("星海维修",),
        (("REPAIRED_BY", "inbound"), ("OWNED_BY", "outbound")),
        ("explicit_chain", "inbound", "nearby_relation"),
        ("REPAIRED_AT", "HELD_BY"),
    ),
    (
        "p11",
        "adversarial",
        "two_hop",
        "从林老师反向找他推荐过的书，再查这些书是谁购买的。",
        ("林老师",),
        (("RECOMMENDED_BY", "inbound"), ("PURCHASED_BY", "outbound")),
        ("explicit_chain", "inbound"),
        ("OWNED_BY",),
    ),
    (
        "p12",
        "dev",
        "two_hop",
        "先找出在北京店购买的物品，再查这些物品目前由谁保管。",
        ("北京店",),
        (("PURCHASED_AT", "inbound"), ("HELD_BY", "outbound")),
        ("explicit_chain", "inbound", "nearby_relation"),
        ("PURCHASED_BY", "OWNED_BY"),
    ),
    (
        "p13",
        "dev",
        "one_hop",
        "这本书是谁买的？",
        ("书",),
        (("PURCHASED_BY", "outbound"),),
        ("nearby_relation",),
        ("OWNED_BY", "HELD_BY"),
    ),
    (
        "p14",
        "heldout",
        "one_hop",
        "相机现在归谁所有？",
        ("相机",),
        (("OWNED_BY", "outbound"),),
        ("nearby_relation",),
        ("HELD_BY", "PURCHASED_BY"),
    ),
    (
        "p15",
        "adversarial",
        "one_hop",
        "护照目前由谁保管？",
        ("护照",),
        (("HELD_BY", "outbound"),),
        ("nearby_relation",),
        ("OWNED_BY", "ISSUED_BY"),
    ),
    (
        "p16",
        "heldout",
        "one_hop",
        "这本护照由哪个机关签发？",
        ("护照",),
        (("ISSUED_BY", "outbound"),),
        ("nearby_relation",),
        ("HELD_BY",),
    ),
    (
        "p17",
        "dev",
        "one_hop",
        "谁修了这台相机？",
        ("相机",),
        (("REPAIRED_BY", "outbound"),),
        ("nearby_relation",),
        ("REPAIRED_AT",),
    ),
    (
        "p18",
        "adversarial",
        "one_hop",
        "这台相机是在哪里维修的？",
        ("相机",),
        (("REPAIRED_AT", "outbound"),),
        ("nearby_relation",),
        ("REPAIRED_BY",),
    ),
    (
        "p19",
        "heldout",
        "one_hop",
        "这块表是在哪家店买的？",
        ("表",),
        (("PURCHASED_AT", "outbound"),),
        ("nearby_relation",),
        ("PURCHASED_BY",),
    ),
    (
        "p20",
        "dev",
        "one_hop",
        "豆包出生在哪里？",
        ("豆包",),
        (("BORN_AT", "outbound"),),
        ("nearby_relation",),
        ("ADOPTED_FROM", "LOCATED_AT"),
    ),
    (
        "p21",
        "adversarial",
        "one_hop",
        "豆包是从哪里领养的？",
        ("豆包",),
        (("ADOPTED_FROM", "outbound"),),
        ("nearby_relation",),
        ("BORN_AT", "PURCHASED_AT"),
    ),
    (
        "p22",
        "heldout",
        "one_hop",
        "护照上次是什么日期续签的？",
        ("护照",),
        (("RENEWED_ON", "outbound"),),
        ("nearby_relation",),
        ("ISSUED_BY",),
    ),
    (
        "p23",
        "dev",
        "one_hop",
        "从小王反向查他购买过哪些物品。",
        ("小王",),
        (("PURCHASED_BY", "inbound"),),
        ("inbound",),
        ("OWNED_BY",),
    ),
    (
        "p24",
        "heldout",
        "one_hop",
        "星海维修修过哪些设备？",
        ("星海维修",),
        (("REPAIRED_BY", "inbound"),),
        ("inbound", "nearby_relation"),
        ("REPAIRED_AT",),
    ),
    (
        "p25",
        "dev",
        "no_path",
        "我最近看过哪些书？",
        ("书",),
        (),
        ("nonrelation",),
        (),
    ),
    (
        "p26",
        "heldout",
        "no_path",
        "我去年一共旅行了几次？",
        (),
        (),
        ("nonrelation", "count"),
        (),
    ),
    (
        "p27",
        "adversarial",
        "no_path",
        "相机和小王到底是什么关系？",
        ("相机", "小王"),
        (),
        ("ambiguous_relation",),
        (),
    ),
    (
        "p28",
        "heldout",
        "no_path",
        "这本书是谁签名的？",
        ("书",),
        (),
        ("unsupported_relation",),
        (),
    ),
    (
        "p29",
        "adversarial",
        "no_path",
        "从相机找到保管人，再找他的雇主，最后查雇主的位置。",
        ("相机",),
        (),
        ("over_bound", "explicit_chain"),
        (),
    ),
    (
        "p30",
        "dev",
        "no_path",
        "帮我订一张明天去北京的机票。",
        ("北京",),
        (),
        ("nonrelation", "agent_action"),
        (),
    ),
    (
        "p31",
        "heldout",
        "no_path",
        "我通常喜欢什么口味？",
        (),
        (),
        ("nonrelation",),
        (),
    ),
    (
        "p32",
        "adversarial",
        "no_path",
        "这台设备与星海维修之间是所有权还是维修关系？",
        ("设备", "星海维修"),
        (),
        ("ambiguous_relation", "explicit_alternatives"),
        ("OWNED_BY", "REPAIRED_BY"),
    ),
)


def build_dataset() -> dict[str, Any]:
    cases = [
        {
            "case_id": case_id,
            "partition": partition,
            "category": category,
            "query": query,
            "expected_entity_mentions": list(entities),
            "expected_path_steps": [
                {"relation_types": [relation_type], "direction": direction}
                for relation_type, direction in steps
            ],
            "traits": list(traits),
            "forbidden_relation_types": list(forbidden),
        }
        for (
            case_id,
            partition,
            category,
            query,
            entities,
            steps,
            traits,
            forbidden,
        ) in CASES
    ]
    payload: dict[str, Any] = {
        "suite": "doppel-relation-path-planner-zh-v1",
        "suite_version": "1.0.0-draft.1",
        "frozen": False,
        "publication_ready": False,
        "relation_catalog": "../catalogs/personal-relations-v1.json",
        "cases": cases,
    }
    encoded = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    payload["fingerprint"] = hashlib.sha256(encoded).hexdigest()
    return payload


def main() -> None:
    target = (
        Path(__file__).parent
        / "datasets"
        / "relation-path-planner-quality-zh-v1.json"
    )
    target.write_text(
        json.dumps(build_dataset(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
