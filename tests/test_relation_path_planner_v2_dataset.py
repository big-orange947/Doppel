"""Frozen-corpus contracts for the V2 sealed relation-path evaluation."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from benchmarks.build_relation_path_planner_v2 import build_dataset
from benchmarks.relation_path_planner_quality import (
    load_dataset,
    load_relation_catalog,
)

ROOT = Path(__file__).resolve().parents[1]
V1_DATASET = ROOT / "benchmarks/datasets/relation-path-planner-quality-zh-v1.json"
V2_DATASET = ROOT / "benchmarks/datasets/relation-path-planner-quality-zh-v2.json"
CATALOG = ROOT / "benchmarks/catalogs/personal-relations-v1.json"


def test_v2_sealed_dataset_is_deterministic_frozen_and_unseen() -> None:
    committed = json.loads(V2_DATASET.read_text("utf-8"))
    assert committed == build_dataset()
    dataset = load_dataset(V2_DATASET)
    v1_queries = {case.query for case in load_dataset(V1_DATASET).cases}

    assert dataset.frozen is True
    assert dataset.publication_ready is False
    assert dataset.suite_version == "2.0.0-sealed.1"
    assert len(dataset.cases) == 48
    assert Counter(case.partition for case in dataset.cases) == {
        "heldout": 36,
        "adversarial": 12,
    }
    assert Counter(case.category for case in dataset.cases) == {
        "one_hop": 16,
        "two_hop": 16,
        "no_path": 16,
    }
    assert not v1_queries.intersection(case.query for case in dataset.cases)


def test_v2_sealed_dataset_covers_catalog_directions_and_no_path_reasons() -> None:
    dataset = load_dataset(V2_DATASET)
    catalog_names = {item.name for item in load_relation_catalog(CATALOG)}
    selected_names = {
        relation_type
        for case in dataset.cases
        for step in case.expected_path_steps
        for relation_type in step.relation_types
    }
    direction_pairs = {
        tuple(step.direction for step in case.expected_path_steps)
        for case in dataset.cases
        if case.category == "two_hop"
    }
    no_path_traits = Counter(
        reason
        for case in dataset.cases
        if case.category == "no_path"
        for reason in (
            "over_bound",
            "ambiguous_relation",
            "unsupported_relation",
            "nonrelation",
        )
        if reason in case.traits
    )

    assert selected_names == catalog_names
    assert direction_pairs.issuperset(
        {
            ("outbound", "outbound"),
            ("inbound", "outbound"),
            ("outbound", "inbound"),
            ("inbound", "inbound"),
        }
    )
    assert no_path_traits == {
        "over_bound": 4,
        "ambiguous_relation": 4,
        "unsupported_relation": 4,
        "nonrelation": 4,
    }


def test_v2_category_shapes_are_consistent_with_sealed_gold() -> None:
    dataset = load_dataset(V2_DATASET)

    for case in dataset.cases:
        if case.category == "one_hop":
            assert len(case.expected_path_steps) == 1
        elif case.category == "two_hop":
            assert len(case.expected_path_steps) == 2
        else:
            assert case.expected_path_steps == []
            assert any(
                trait in case.traits
                for trait in (
                    "over_bound",
                    "ambiguous_relation",
                    "unsupported_relation",
                    "nonrelation",
                )
            )
