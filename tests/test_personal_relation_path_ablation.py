"""Dataset and metric contracts for the bounded relation-path ablation."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from benchmarks.build_personal_relation_path_v1 import build_dataset
from benchmarks.personal_relation_path_ablation import (
    PathDataset,
    _summarize_profile,
    load_dataset,
)

ROOT = Path(__file__).resolve().parents[1]
DATASET = (
    ROOT / "benchmarks" / "datasets" / "personal-relation-path-ablation-zh-v1.json"
)


def test_committed_relation_path_dataset_is_deterministic_and_draft() -> None:
    committed = json.loads(DATASET.read_text(encoding="utf-8"))
    assert committed == build_dataset()
    dataset = load_dataset(DATASET)

    assert dataset.frozen is False
    assert dataset.publication_ready is False
    assert len(dataset.scopes) == 9
    assert len(dataset.fixtures) == 17
    assert len(dataset.entities) == 27
    assert len(dataset.edges) == 18
    assert len(dataset.queries) == 26
    assert {item.partition for item in dataset.queries} == {
        "dev",
        "heldout",
        "adversarial",
    }
    assert sum(len(item.steps) == 2 for item in dataset.queries) == 18
    assert {item.category for item in dataset.queries}.issuperset(
        {
            "two_hop_answerable",
            "one_hop_control",
            "wrong_relation_adversary",
            "second_hop_not_yet_valid",
            "orphan_second_hop",
        }
    )


def test_relation_path_dataset_rejects_cross_scope_topology() -> None:
    payload = build_dataset()
    payload["edges"][0]["source_entity_id"] = "e-camera-b-anchor"

    with pytest.raises(ValueError, match="cross-scope topology"):
        PathDataset.model_validate(payload)


def test_relation_path_metrics_keep_recall_and_security_separate() -> None:
    rows = [
        {
            "query_id": "q1",
            "memory_ids": ["a"],
            "required_hop_memory_ids": [["a"], ["b"]],
            "forbidden_memory_ids": [],
            "authorized_scope_key": "scope-a",
            "scope_keys": ["scope-a"],
            "expected_path_count": 1,
            "actual_path_count": 1,
            "expected_end_entity": "上海",
            "path_endpoints": ["上海"],
            "latency_ms": 10.0,
            "category": "two_hop_answerable",
            "partition": "dev",
        },
        {
            "query_id": "q2",
            "memory_ids": ["c"],
            "required_hop_memory_ids": [["c"]],
            "forbidden_memory_ids": ["z"],
            "authorized_scope_key": "scope-a",
            "scope_keys": ["scope-foreign"],
            "expected_path_count": 1,
            "actual_path_count": 1,
            "expected_end_entity": "小王",
            "path_endpoints": ["小王"],
            "latency_ms": 20.0,
            "category": "one_hop_control",
            "partition": "heldout",
        },
    ]

    path = _summarize_profile(rows, includes_path=True)
    assert path["evidence_recall"] == pytest.approx(2 / 3, abs=1e-6)
    assert path["complete_evidence_rate"] == 0.5
    assert path["missing_required_evidence"] == 1
    assert path["forbidden_hits"] == 0
    assert path["scope_leakage"] == 1
    assert path["path_count_failures"] == 0
    assert path["endpoint_failures"] == 0

    one_hop = _summarize_profile(rows, includes_path=False)
    assert one_hop["path_count_failures"] is None
    assert one_hop["endpoint_failures"] is None
