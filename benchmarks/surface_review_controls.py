"""Hand-authored development controls, separate from the unopened blind corpus."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from benchmarks.evidence_rich_blind_authoring import OwnerSurfaceReview
from benchmarks.evidence_rich_blind_revision import REVIEW_INSTRUCTIONS, _meanings
from doppel_memory.intelligence import StructuredGenerationRequest


class ReviewControl(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    case_id: str
    family: str
    pair_id: str
    reviewer_input: dict[str, Any]
    acceptable: bool
    allowed_issue_keys: list[str] = Field(default_factory=list)
    allowed_issue_codes: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_gold(self) -> ReviewControl:
        keys = [
            x["surface_key"]
            for k in ("entities", "memories", "queries")
            for x in self.reviewer_input[k]
        ]
        if not keys or len(keys) != len(set(keys)):
            raise ValueError("control surface keys must be nonempty and unique")
        if not set(self.allowed_issue_keys).issubset(keys):
            raise ValueError("control expected issue refers to unknown slot")
        if self.acceptable:
            if self.allowed_issue_keys or self.allowed_issue_codes:
                raise ValueError("acceptable control cannot expect issues")
        elif not self.allowed_issue_keys or not self.allowed_issue_codes:
            raise ValueError("defective control needs issue keys and codes")
        return self


def _entity(key: str, name: str, kind: str, brief: str) -> dict[str, Any]:
    return {
        "surface_key": key,
        "entity_type": kind,
        "semantic_brief": brief,
        "shared_name_group": "",
        "required_display_name": "",
        "authored_name": name,
    }


def _memory(
    key: str,
    brief: str,
    content: str,
    *,
    relation: dict[str, str] | None = None,
    edge: str = "",
) -> dict[str, Any]:
    return {
        "surface_key": key,
        "kind": "relation" if relation else "fact",
        "semantic_brief": brief,
        "relation": relation,
        "authored_content": content,
        "authored_edge_fact": edge,
    }


def _query(
    brief: str, text: str, *, view: str = "current", intent: str = "lookup"
) -> dict[str, Any]:
    return {
        "surface_key": "query-a",
        "category": "personal_information",
        "query_style": "explicit",
        "intent": intent,
        "temporal_view": view,
        "semantic_brief": brief,
        "required_route_shape": [],
        "authored_query": text,
    }


def build_controls() -> list[ReviewControl]:
    pairs: list[tuple[str, dict[str, Any], dict[str, Any], list[str], list[str]]] = []

    def add(
        family: str,
        good: dict[str, Any],
        bad: dict[str, Any],
        keys: list[str],
        codes: list[str],
    ) -> None:
        pairs.append((family, good, bad, keys, codes))

    def payload(
        memories: list[dict[str, Any]],
        queries: list[dict[str, Any]] | None = None,
        entities: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        return {
            "entities": entities or [],
            "memories": memories,
            "queries": queries or [],
        }

    base = [
        _memory(
            "memory-a",
            "只记录银色三脚架的保管人，不添加购买者。",
            "银色三脚架现在由周岚保管。",
        )
    ]
    add(
        "unknown_relation_question",
        payload(
            base,
            [
                _query(
                    "询问三脚架的购买者，问句不要提供答案或宣布是否有答案。",
                    "银色三脚架是谁买的？",
                )
            ],
        ),
        payload(
            base,
            [
                _query(
                    "询问三脚架的购买者，问句不要提供答案或宣布是否有答案。",
                    "银色三脚架是周岚买的，对吗？",
                )
            ],
        ),
        ["query-a"],
        ["answer_leak"],
    )

    base = [
        _memory(
            "memory-a",
            "记录主人对猫毛是否过敏的亲自澄清。",
            "主人澄清自己对猫毛并不过敏。",
        )
    ]
    add(
        "topic_is_not_truth_value",
        payload(
            base,
            [
                _query(
                    "询问主人澄清后的猫毛过敏状态，不提供结论。", "我对猫毛是否过敏？"
                )
            ],
        ),
        payload(
            base,
            [
                _query(
                    "询问主人澄清后的猫毛过敏状态，不提供结论。",
                    "我对猫毛并不过敏，是这样吧？",
                )
            ],
        ),
        ["query-a"],
        ["answer_leak"],
    )

    def custody(exclusive: bool) -> dict[str, Any]:
        a = (
            "红色工具箱自2027年1月1日起由许澄独自保管，目前仍有效。"
            if exclusive
            else "红色工具箱以前由许澄保管，这段保管于2026年12月31日结束。"
        )
        b = "红色工具箱自2027年1月1日起由叶珊独自保管，目前仍有效。"
        return payload(
            [
                _memory(
                    "memory-a", "如实记录工具箱保管关系，独自保管的有效期不得重叠。", a
                ),
                _memory(
                    "memory-b", "如实记录工具箱保管关系，独自保管的有效期不得重叠。", b
                ),
            ]
        )

    add(
        "old_current_custody",
        custody(False),
        custody(True),
        ["memory-a", "memory-b"],
        ["relation_mismatch", "semantic_drift"],
    )

    base = [
        _memory(
            "memory-a",
            "临住从2027年6月1日起持续至6月30日结束，7月1日起不再临住。",
            "主人2027年6月1日至6月30日在宁波临住，7月1日起已经搬离。",
        )
    ]
    add(
        "historical_question_after_event_ends",
        payload(
            base,
            [
                _query(
                    "询问2027年6月12日临住的城市。",
                    "2027年6月12日我临时住在哪？",
                    view="as_of",
                )
            ],
        ),
        payload(
            base,
            [
                _query(
                    "询问2027年6月12日临住的城市。",
                    "2027年7月12日我临时住在哪？",
                    view="as_of",
                )
            ],
        ),
        ["query-a"],
        ["temporal_mismatch", "semantic_drift"],
    )

    brief = "研修住宿自2027年9月1日起，持续到9月30日结束；10月1日起已结束。"
    add(
        "exact_interval_boundary",
        payload(
            [
                _memory(
                    "memory-a",
                    brief,
                    "主人从2027年9月1日起住在研修宿舍，住到9月30日结束，10月1日起不再入住。",
                )
            ]
        ),
        payload(
            [
                _memory(
                    "memory-a",
                    brief,
                    "主人从2027年9月1日起住在研修宿舍，一直住到10月15日才结束。",
                )
            ]
        ),
        ["memory-a"],
        ["temporal_mismatch", "semantic_drift"],
    )

    entities = [
        _entity(
            "entity-a", "培训合格证", "document", "正式的培训合格证明，不是普通出版物。"
        ),
        _entity(
            "entity-b",
            "海棠培训中心",
            "organization",
            "负责签发本中心培训合格证的机构。",
        ),
    ]
    relation = {
        "type": "ISSUED_BY",
        "source_entity_key": "entity-a",
        "target_entity_key": "entity-b",
    }
    add(
        "issuable_document_subtype",
        payload(
            [
                _memory(
                    "memory-a",
                    "记载上述证明由目标机构签发。",
                    "培训合格证由海棠培训中心签发。",
                    relation=relation,
                    edge="培训合格证由海棠培训中心签发。",
                )
            ],
            entities=entities,
        ),
        payload(
            [
                _memory(
                    "memory-a",
                    "记载上述证明由目标机构签发。",
                    "普通散文集《雨后街道》由海棠培训中心签发。",
                    relation=relation,
                    edge="普通散文集《雨后街道》由海棠培训中心签发。",
                )
            ],
            entities=[
                {**entities[0], "authored_name": "普通散文集《雨后街道》"},
                entities[1],
            ],
        ),
        ["entity-a", "memory-a"],
        ["relation_mismatch", "entity_inconsistent", "semantic_drift"],
    )

    entities = [
        _entity("entity-a", "木色画架", "object", "被保管的画架。"),
        _entity("entity-b", "林穗", "person", "画架当前保管人。"),
    ]
    relation = {
        "type": "HELD_BY",
        "source_entity_key": "entity-a",
        "target_entity_key": "entity-b",
    }
    add(
        "edge_content_meaning",
        payload(
            [
                _memory(
                    "memory-a",
                    "正文和边事实都只描述画架由保管人保管。",
                    "木色画架由林穗保管。",
                    relation=relation,
                    edge="木色画架在林穗那里保管。",
                )
            ],
            entities=entities,
        ),
        payload(
            [
                _memory(
                    "memory-a",
                    "正文和边事实都只描述画架由保管人保管。",
                    "木色画架由林穗保管。",
                    relation=relation,
                    edge="木色画架由林穗出售。",
                )
            ],
            entities=entities,
        ),
        ["memory-a"],
        ["relation_mismatch", "semantic_drift"],
    )

    entities = [
        _entity("entity-a", "江橙", "person", "任职者。"),
        _entity("entity-b", "墨帆工作室", "organization", "任职机构。"),
    ]
    relation = {
        "type": "WORKS_AT",
        "source_entity_key": "entity-a",
        "target_entity_key": "entity-b",
    }
    add(
        "relation_direction",
        payload(
            [
                _memory(
                    "memory-a",
                    "描述源人物在目标机构任职。",
                    "江橙在墨帆工作室任职。",
                    relation=relation,
                    edge="江橙在墨帆工作室任职。",
                )
            ],
            entities=entities,
        ),
        payload(
            [
                _memory(
                    "memory-a",
                    "描述源人物在目标机构任职。",
                    "墨帆工作室在江橙任职。",
                    relation=relation,
                    edge="墨帆工作室在江橙任职。",
                )
            ],
            entities=entities,
        ),
        ["memory-a"],
        [
            "relation_mismatch",
            "entity_inconsistent",
            "semantic_drift",
            "unnatural_language",
        ],
    )

    acquisition = "保持动物来源自洽；若有领养和后续转让，必须交代实际行为主体与经过。"
    add(
        "acquisition_actor_chain",
        payload(
            [
                _memory(
                    "memory-a",
                    acquisition,
                    "小狗麦穗原先由苏航从溪畔救助站领养，后来苏航把它转售给主人。",
                ),
                _memory(
                    "memory-b",
                    acquisition,
                    "主人从苏航那里买来小狗麦穗；这是上述领养之后的转让。",
                ),
            ]
        ),
        payload(
            [
                _memory(
                    "memory-a",
                    acquisition,
                    "主人首次取得小狗麦穗的唯一来源，是直接从溪畔救助站领养，从未经过其他人转让。",
                ),
                _memory(
                    "memory-b",
                    acquisition,
                    "主人首次取得同一只小狗麦穗的唯一来源，是从苏航购买，并非领养。",
                ),
            ]
        ),
        ["memory-a", "memory-b"],
        ["relation_mismatch", "semantic_drift", "entity_inconsistent"],
    )

    lifecycle = "描述同一只猫的领养经历；不同机构之间的变化应说明退养和再次领养。"
    add(
        "return_and_readoption_lifecycle",
        payload(
            [
                _memory(
                    "memory-a",
                    lifecycle,
                    "猫小舟于2025年从东岸救助所领养，2026年已退养；救助所随后移交了安置责任。",
                ),
                _memory(
                    "memory-b",
                    lifecycle,
                    "2027年主人从接手安置的西岸救助所再次领养了同一只猫小舟。",
                ),
            ]
        ),
        payload(
            [
                _memory(
                    "memory-a",
                    lifecycle,
                    "主人于2025年从东岸救助所领养猫小舟，此后从未退养、转出或再次领养。",
                ),
                _memory(
                    "memory-b",
                    lifecycle,
                    "主人于2027年从西岸救助所再次领养了同一只猫小舟。",
                ),
            ]
        ),
        ["memory-a", "memory-b"],
        ["relation_mismatch", "semantic_drift"],
    )

    base = [
        _memory(
            "memory-a",
            "记录主人取消的郊游计划，不能写成已经成行。",
            "主人取消了去湿地公园的郊游，没有成行。",
        )
    ]
    add(
        "requested_operation",
        payload(
            base,
            [
                _query(
                    "询问取消的计划数量，不询问完成的出行数量。",
                    "我取消过几次郊游计划？",
                    intent="count",
                )
            ],
        ),
        payload(
            base,
            [
                _query(
                    "询问取消的计划数量，不询问完成的出行数量。",
                    "我完成过几次郊游？",
                    intent="count",
                )
            ],
        ),
        ["query-a"],
        ["semantic_drift", "temporal_mismatch"],
    )

    issuer_entities = [
        _entity(
            "entity-a",
            "考核合格证",
            "document",
            "只能由有考核资格的机构签发的合格证明。",
        ),
        _entity(
            "entity-b",
            "丹霞考核中心",
            "organization",
            "具有本项考核和证书签发资格的机构。",
        ),
        _entity(
            "entity-c",
            "春山印刷厂",
            "organization",
            "只提供证书纸张印刷，没有考核或签发资格。",
        ),
    ]
    good_relation = {
        "type": "ISSUED_BY",
        "source_entity_key": "entity-a",
        "target_entity_key": "entity-b",
    }
    bad_relation = {**good_relation, "target_entity_key": "entity-c"}
    brief = "证书只能由具有签发资格的机构签发，印刷供应商不拥有签发权。"
    add(
        "competent_issuer_role",
        payload(
            [
                _memory(
                    "memory-a",
                    brief,
                    "考核合格证由丹霞考核中心签发。",
                    relation=good_relation,
                    edge="考核合格证由丹霞考核中心签发。",
                )
            ],
            entities=issuer_entities,
        ),
        payload(
            [
                _memory(
                    "memory-a",
                    brief,
                    "考核合格证由春山印刷厂签发。",
                    relation=bad_relation,
                    edge="考核合格证由春山印刷厂签发。",
                )
            ],
            entities=issuer_entities,
        ),
        ["memory-a"],
        ["relation_mismatch", "entity_inconsistent", "semantic_drift"],
    )

    controls = []
    # Alternating which variant is first avoids a trivial positional answer cue.
    for index, (family, good, bad, keys, codes) in enumerate(pairs, 1):
        variants = (
            [(True, good), (False, bad)] if index % 2 else [(False, bad), (True, good)]
        )
        for acceptable, content in variants:
            controls.append(
                ReviewControl(
                    case_id=f"review-control-{len(controls) + 1:02d}",
                    family=family,
                    pair_id=f"pair-{index:02d}",
                    reviewer_input=content,
                    acceptable=acceptable,
                    allowed_issue_keys=[] if acceptable else keys,
                    allowed_issue_codes=[] if acceptable else codes,
                )
            )
    return controls


def fingerprint(controls: list[ReviewControl]) -> str:
    return hashlib.sha256(
        json.dumps(
            [c.model_dump(mode="json") for c in controls],
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()


def build_baseline_request(control: ReviewControl) -> StructuredGenerationRequest:
    content = {
        **control.reviewer_input,
        "language": "zh-CN",
        "contract_revision": "pre-retrieval-v3",
        "relation_meanings": _meanings(),
    }
    # Hash public request material only. IDs, family/pair, and expected judgments stay local.
    content["review_nonce"] = hashlib.sha256(
        json.dumps(content, ensure_ascii=False, sort_keys=True).encode()
    ).hexdigest()[:24]
    return StructuredGenerationRequest(
        instructions=REVIEW_INSTRUCTIONS,
        input=content,
        output_schema=OwnerSurfaceReview.model_json_schema(),
    )
