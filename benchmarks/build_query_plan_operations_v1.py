"""Build a domain-varied operation/time matrix for Query Plan v2 evaluation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

OUTPUT = Path(__file__).parent / "datasets" / "query-plan-operations-zh-v1.json"
NOW = "2026-09-15T12:00:00Z"
TOPICS = ("旅行", "设备维修", "会议", "票据报销")
OPERATIONS = ("lookup", "list", "count")
TEMPORAL_VIEWS = ("unbounded", "current", "prior", "planned", "as_of", "interval")


def _question(operation: str, temporal_view: str, topic: str) -> str:
    templates = {
        ("lookup", "unbounded"): "帮我找出与{topic}有关的事实。",
        ("lookup", "current"): "{topic}目前是什么情况？",
        ("lookup", "prior"): "{topic}之前是什么情况？",
        ("lookup", "planned"): "下一项尚未发生的{topic}计划是什么？",
        ("lookup", "as_of"): "2026年3月15日，{topic}是什么情况？",
        ("lookup", "interval"): "2025年期间，{topic}是什么情况？",
        ("list", "unbounded"): "列出所有{topic}记录。",
        ("list", "current"): "列出当前有效的{topic}记录。",
        ("list", "prior"): "列出已经结束的{topic}记录。",
        ("list", "planned"): "列出尚未发生的{topic}计划。",
        ("list", "as_of"): "列出2026年3月15日有效的{topic}记录。",
        ("list", "interval"): "列出2025年期间的{topic}记录。",
        ("count", "unbounded"): "{topic}一共发生了多少次？",
        ("count", "current"): "当前有效的{topic}事件有多少个？",
        ("count", "prior"): "已经完成的{topic}一共有多少次？",
        ("count", "planned"): "还没发生的{topic}计划一共有多少个？",
        ("count", "as_of"): "在2026年3月15日这个时间点，有多少条{topic}事件有效？",
        ("count", "interval"): "2025年期间，{topic}一共发生了多少次？",
    }
    return templates[(operation, temporal_view)].format(topic=topic)


def build_dataset() -> dict[str, object]:
    cases: list[dict[str, object]] = []
    for operation_index, operation in enumerate(OPERATIONS):
        for temporal_index, temporal_view in enumerate(TEMPORAL_VIEWS):
            for topic_index, topic in enumerate(TOPICS):
                row: dict[str, object] = {
                    "case_id": (
                        f"op-{operation_index + 1}-{temporal_index + 1}-"
                        f"{topic_index + 1}"
                    ),
                    "query": _question(operation, temporal_view, topic),
                    "now": NOW,
                    "calendar_timezone": "UTC",
                    "operation": operation,
                    "temporal_view": temporal_view,
                    "expected_memory_types": ["episode"]
                    if operation == "count"
                    else [],
                    "partition": ("dev", "heldout", "adversarial")[topic_index % 3],
                }
                if temporal_view == "as_of":
                    row["as_of"] = "2026-03-15T12:00:00Z"
                elif temporal_view == "interval":
                    row["time_from"] = "2025-01-01T00:00:00Z"
                    row["time_to"] = "2025-12-31T23:59:59Z"
                cases.append(row)
    assert len(cases) == 72
    return {
        "suite": "doppel-query-plan-operations-zh-v1",
        "suite_version": "1.0.0-draft.1",
        "language": "zh-CN",
        "frozen": False,
        "publication_ready": False,
        "description": (
            "Independent operation/time-view matrix with four domain-varied topics; "
            "it measures planning only and contains no retrieval answers."
        ),
        "cases": cases,
    }


def _serialized() -> str:
    return json.dumps(build_dataset(), ensure_ascii=False, indent=2) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    expected = _serialized()
    if args.check:
        if not OUTPUT.exists() or OUTPUT.read_text(encoding="utf-8") != expected:
            raise SystemExit("generated query-plan operation dataset is out of date")
        return 0
    OUTPUT.write_text(expected, encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
