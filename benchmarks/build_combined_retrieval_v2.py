"""Build V2 with unique provider prompts over the same isolation topology."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from benchmarks.build_combined_retrieval_v1 import build_dataset as build_v1

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "benchmarks/datasets/combined-retrieval-zh-v2.json"
SEMANTIC_VARIANTS = (
    "如果替我准备早餐，应该搭配哪一种饮品？",
    "我的晨间饮料通常会选什么？",
    "按以前记录的习惯，我起床后一般喝什么？",
    "早饭时给我倒什么喝的最符合习惯？",
    "我每天开头常喝的饮品是哪一种？",
    "关于早餐饮料，我一贯的偏好是什么？",
    "不考虑偶尔尝试，我早晨固定会喝什么？",
    "我通常用什么饮料开启一天？",
    "家里替我备早餐时，饮品该怎么选？",
    "记忆中我最稳定的晨间饮品是什么？",
    "早起之后，我惯常喝的是哪种东西？",
    "我的早餐饮品习惯具体是什么？",
)


def build_dataset() -> dict[str, Any]:
    dataset = build_v1()
    dataset["suite"] = "doppel-combined-retrieval-zh-v2"
    dataset["version"] = "2.0.0"
    dataset["description"] = (
        "Frozen synthetic corpus combining 144 unique natural-language provider "
        "prompts, dense per-owner semantic distractors, temporal invalidation, graph "
        "provenance, and repeated cross-owner entity names. No real personal data."
    )
    for query in dataset["queries"]:
        number = _case_number(str(query["case_id"]))
        cycle = (number - 1) // 12
        base = str(query["query"])
        if query["category"] == "semantic_nonrelation":
            base = SEMANTIC_VARIANTS[(number - 1) % 12]
        query["query"] = _variant(base, cycle)
    return dataset


def _case_number(case_id: str) -> int:
    match = re.fullmatch(r"q-c(\d{2})-.+", case_id)
    if match is None:
        raise ValueError(f"unexpected combined case ID: {case_id}")
    return int(match.group(1))


def _variant(query: str, cycle: int) -> str:
    if cycle == 0:
        return query
    body = query.rstrip("？。")
    if cycle == 1:
        return f"请根据我以前留下的信息确认一下：{body}？"
    if cycle == 2:
        return f"我换一种说法问，{body}？"
    raise ValueError(f"unexpected corpus cycle: {cycle}")


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
