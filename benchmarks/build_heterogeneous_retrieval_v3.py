"""Build V3 with explicit generic oracle count-plan fields."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from benchmarks.build_heterogeneous_retrieval_v2 import build_dataset as build_v2

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "benchmarks/datasets/heterogeneous-retrieval-zh-v3.json"


def build_dataset() -> dict[str, Any]:
    dataset = build_v2()
    dataset["suite"] = "doppel-heterogeneous-retrieval-zh-v3"
    dataset["version"] = "3.0.0"
    dataset["description"] = (
        str(dataset["description"])
        + " V3 declares generic oracle query-plan fields for exhaustive episode "
        "counts, keeping Planner quality separate from retrieval execution."
    )
    dataset["requirements"]["requires_oracle_count_plan"] = True
    for query in dataset["queries"]:
        query["oracle_search_text"] = None
        query["oracle_memory_types"] = []
        query["oracle_topic_keys"] = []
        if query["intent"] != "count":
            continue
        required = set(query["required_memory_ids"])
        fact_keys = sorted(
            {
                memory["fact_key"]
                for memory in dataset["memories"]
                if memory["memory_id"] in required
            }
        )
        if not fact_keys:
            raise ValueError(f"{query['case_id']}: count query has no required fact key")
        query["oracle_search_text"] = ""
        query["oracle_memory_types"] = ["episode"]
        query["oracle_topic_keys"] = fact_keys
    return dataset


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
