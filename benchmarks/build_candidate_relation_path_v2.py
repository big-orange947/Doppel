"""Build the draft dataset for exact-plus-candidate relation-path retrieval."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any, cast

from benchmarks.build_personal_relation_path_v1 import DOMAINS
from benchmarks.build_personal_relation_path_v1 import build_dataset as build_v1

ALTERNATIVES = {
    "HELD_BY": "LOANED_TO",
    "LOCATED_AT": "STORED_IN",
    "PROVIDED_BY": "AUTHORED_BY",
    "CONTACTABLE_AT": "REGISTERED_AT",
    "CARED_FOR_BY": "LIVES_WITH",
    "REPAIRED_BY": "SERVICED_BY",
    "WORKS_AT": "LOCATED_AT",
    "RECEIVED_BY": "HELD_BY",
    "RESTORED_BY": "REPAIRED_BY",
}


def _candidate_atoms(steps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    refs = ("anchor", "middle", "answer")
    atoms: list[dict[str, Any]] = []
    for index, step in enumerate(steps):
        exact = str(step["relation_types"][0])
        relation_types = [exact]
        alternative = ALTERNATIVES.get(exact)
        if alternative:
            relation_types.append(alternative)
        atoms.append(
            {
                "relation_types": relation_types,
                "source_ref": refs[index],
                "target_ref": refs[index + 1] if len(steps) == 2 else "answer",
            }
        )
    return atoms


def _convert_query(raw: dict[str, Any]) -> dict[str, Any]:
    steps = deepcopy(raw.pop("steps"))
    raw.pop("expected_path_count")
    raw["path_decision"] = "execute"
    raw["path_reason"] = "exact"
    raw["exact_steps"] = steps
    raw["candidate_topologies"] = [
        {"atoms": _candidate_atoms(steps), "confidence": 0.65}
    ]
    raw["candidate_noise_memory_ids"] = []
    raw["recovery_expected"] = False
    raw["dual_attribution_expected"] = bool(raw["required_hop_memory_ids"])
    raw["expected_compilation"] = {}
    return raw


def build_dataset() -> dict[str, object]:
    base = cast(dict[str, Any], deepcopy(build_v1()))
    queries = [_convert_query(item) for item in base["queries"]]
    relation_types = set(base["relation_types"])
    relation_types.update(ALTERNATIVES.values())

    # One deliberately widened branch makes the recall/precision trade-off visible.
    base["fixtures"].extend(
        [
            {
                "memory_id": "m-camera-a-noise-1",
                "scope": "s01",
                "content": "相机曾登记存放在器材架。",
                "valid_from": "2026-01-01T00:00:00+00:00",
                "valid_to": "",
            },
            {
                "memory_id": "m-camera-a-noise-2",
                "scope": "s01",
                "content": "器材架位于南京工作室。",
                "valid_from": "2026-01-01T00:00:00+00:00",
                "valid_to": "",
            },
        ]
    )
    base["entities"].extend(
        [
            {
                "entity_id": "e-camera-a-noise-middle",
                "scope": "s01",
                "name": "器材架",
            },
            {
                "entity_id": "e-camera-a-noise-end",
                "scope": "s01",
                "name": "南京工作室",
            },
        ]
    )
    base["edges"].extend(
        [
            {
                "edge_id": "edge-camera-a-noise-1",
                "scope": "s01",
                "source_entity_id": "e-camera-a-anchor",
                "target_entity_id": "e-camera-a-noise-middle",
                "relation_type": "STORED_IN",
                "fact": "相机曾登记存放在器材架。",
                "memory_id": "m-camera-a-noise-1",
                "valid_at": "2026-01-01T00:00:00+00:00",
                "invalid_at": "",
            },
            {
                "edge_id": "edge-camera-a-noise-2",
                "scope": "s01",
                "source_entity_id": "e-camera-a-noise-middle",
                "target_entity_id": "e-camera-a-noise-end",
                "relation_type": "LOCATED_AT",
                "fact": "器材架位于南京工作室。",
                "memory_id": "m-camera-a-noise-2",
                "valid_at": "2026-01-01T00:00:00+00:00",
                "invalid_at": "",
            },
        ]
    )
    for query in queries:
        if query["scope"] == "s01" and query["query_id"] in {
            "q-camera-a-two-hop",
            "q-camera-a-one-hop",
        }:
            first_atom = query["candidate_topologies"][0]["atoms"][0]
            first_atom["relation_types"].append("STORED_IN")
            query["candidate_noise_memory_ids"] = ["m-camera-a-noise-1"]
            if query["query_id"].endswith("two-hop"):
                query["candidate_noise_memory_ids"].append("m-camera-a-noise-2")

    for query in queries:
        if query["query_id"] == "q-orphan-missing-second-provenance":
            query["forbidden_memory_ids"] = ["m-orphan-1"]

    # Eight ontology-drift cases: the strict type misses, while a bounded alternative
    # set contains the stored host type. These are data labels, never runtime rules.
    for index, domain in enumerate(DOMAINS, start=1):
        (
            name,
            partition,
            anchor,
            _middle,
            endpoint,
            first_type,
            second_type,
            _first_content,
            _second_content,
        ) = domain
        strict_first = ALTERNATIVES[first_type]
        strict_second = ALTERNATIVES[second_type]
        scope_name = f"s{index:02d}"
        query = {
            "query_id": f"q-{name}-ontology-drift",
            "partition": partition,
            "category": "candidate_recovers_ontology_drift",
            "scope": scope_name,
            "query": f"{anchor}现在最终在哪里？",
            "entity_mentions": [anchor],
            "path_decision": "execute",
            "path_reason": "exact",
            "exact_steps": [
                {"relation_types": [strict_first], "direction": "outbound"},
                {"relation_types": [strict_second], "direction": "outbound"},
            ],
            "candidate_topologies": [
                {
                    "atoms": [
                        {
                            "relation_types": [strict_first, first_type],
                            "source_ref": "anchor",
                            "target_ref": "middle",
                        },
                        {
                            "relation_types": [strict_second, second_type],
                            "source_ref": "middle",
                            "target_ref": "answer",
                        },
                    ],
                    "confidence": 0.55,
                }
            ],
            "valid_at": "2026-08-01T00:00:00+00:00",
            "required_hop_memory_ids": [[f"m-{name}-1"], [f"m-{name}-2"]],
            "forbidden_memory_ids": [],
            "candidate_noise_memory_ids": (
                ["m-camera-a-noise-1", "m-camera-a-noise-2"]
                if name == "camera-a"
                else []
            ),
            "expected_end_entity": endpoint,
            "recovery_expected": True,
            "dual_attribution_expected": False,
            "expected_compilation": {"compiled": 1},
        }
        if name == "camera-a":
            query["candidate_topologies"][0]["atoms"][0]["relation_types"].append(
                "STORED_IN"
            )
        queries.append(query)

    # Invalid topology observations must be rejected locally, without a graph query.
    invalid_common = {
        "partition": "adversarial",
        "scope": "s01",
        "entity_mentions": ["相机"],
        "path_decision": "abstain",
        "path_reason": "ambiguous",
        "exact_steps": [],
        "valid_at": "2026-08-01T00:00:00+00:00",
        "required_hop_memory_ids": [],
        "forbidden_memory_ids": [],
        "candidate_noise_memory_ids": [],
        "expected_end_entity": "",
        "recovery_expected": False,
        "dual_attribution_expected": False,
    }
    queries.extend(
        [
            {
                **invalid_common,
                "query_id": "q-candidate-disconnected",
                "category": "candidate_topology_rejected",
                "query": "相机的未知关系在哪里？",
                "candidate_topologies": [
                    {
                        "atoms": [
                            {
                                "relation_types": ["HELD_BY"],
                                "source_ref": "other",
                                "target_ref": "answer",
                            }
                        ],
                        "confidence": 0.5,
                    }
                ],
                "expected_compilation": {"ambiguous": 1},
            },
            {
                **invalid_common,
                "query_id": "q-candidate-over-bound",
                "category": "candidate_topology_rejected",
                "query": "相机经过三层关系最终在哪里？",
                "path_reason": "over_bound",
                "candidate_topologies": [
                    {
                        "atoms": [
                            {
                                "relation_types": ["HELD_BY"],
                                "source_ref": "anchor",
                                "target_ref": "first",
                            },
                            {
                                "relation_types": ["WORKS_AT"],
                                "source_ref": "first",
                                "target_ref": "second",
                            },
                            {
                                "relation_types": ["LOCATED_AT"],
                                "source_ref": "second",
                                "target_ref": "answer",
                            },
                        ],
                        "confidence": 0.5,
                    }
                ],
                "expected_compilation": {"over_bound": 1},
            },
        ]
    )

    return {
        **base,
        "suite": "doppel-candidate-relation-path-ablation-zh-v2",
        "suite_version": "2.0.0-draft.1",
        "description": (
            "Generated exact-plus-candidate path retrieval draft; no natural-language "
            "Planner, LLM, or scenario-specific runtime mapping is involved."
        ),
        "relation_types": sorted(relation_types),
        "queries": queries,
        "requirements": {
            "min_queries": 35,
            "min_scopes": 9,
            "max_hops": 2,
            "candidate_recovery_rate": 1.0,
            "scope_leakage": 0,
            "temporal_or_provenance_forbidden_hits": 0,
            "publication_ready": False,
        },
    }


def main() -> None:
    destination = (
        Path(__file__).resolve().parent
        / "datasets"
        / "candidate-relation-path-ablation-zh-v2.json"
    )
    destination.write_text(
        json.dumps(build_dataset(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(destination)


if __name__ == "__main__":
    main()
