"""Build V2 by correcting one evidence-role label without changing corpus text."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from benchmarks.build_heterogeneous_retrieval_v1 import build_dataset as build_v1

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "benchmarks/datasets/heterogeneous-retrieval-zh-v2.json"


def build_dataset() -> dict[str, Any]:
    dataset = build_v1()
    dataset["suite"] = "doppel-heterogeneous-retrieval-zh-v2"
    dataset["version"] = "2.0.0"
    dataset["description"] = (
        str(dataset["description"])
        + " V2 classifies the superseded peer claim in subject-correction cases as "
        "related conflict context rather than hard-forbidden evidence."
    )
    for query in dataset["queries"]:
        if query["category"] != "subject_correction":
            continue
        peer_ids = [
            memory_id
            for memory_id in query["hard_forbidden_memory_ids"]
            if memory_id.endswith("-peer-allergy")
        ]
        if len(peer_ids) != 1:
            raise ValueError(f"{query['case_id']}: expected one peer conflict label")
        query["hard_forbidden_memory_ids"] = [
            memory_id
            for memory_id in query["hard_forbidden_memory_ids"]
            if memory_id not in peer_ids
        ]
        query["related_memory_ids"] = [*query["related_memory_ids"], *peer_ids]
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
