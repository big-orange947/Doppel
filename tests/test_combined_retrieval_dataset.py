"""Contracts for the frozen combined retrieval corpus."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any, cast

import pytest

from benchmarks.build_combined_retrieval_v1 import build_dataset
from benchmarks.build_combined_retrieval_v2 import build_dataset as build_dataset_v2
from benchmarks.combined_retrieval_quality import (
    CombinedRetrievalDataset,
    load_dataset,
)

ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "benchmarks/datasets/combined-retrieval-zh-v1.json"
EXPECTED_FINGERPRINT = "e16bb570cd3da5924a22a4b1556774d42e556992eaa93d5060c59fc5f2beaf51"
DATASET_V2 = ROOT / "benchmarks/datasets/combined-retrieval-zh-v2.json"
EXPECTED_V2_FINGERPRINT = "f35257ad354f5132c49f152b0b705fbba2cc7ce04dec4635237c91c505a84f6b"


def test_combined_dataset_is_deterministic_frozen_and_dense() -> None:
    committed = json.loads(DATASET.read_text("utf-8"))
    assert committed == build_dataset()
    dataset = load_dataset(DATASET)

    assert dataset.fingerprint == EXPECTED_FINGERPRINT
    assert dataset.frozen is True
    assert dataset.publication_ready is False
    assert len(dataset.scopes) == 36
    assert len(dataset.fixtures) == 3_600
    assert len(dataset.entities) == 216
    assert len(dataset.edges) == 144
    assert len(dataset.queries) == 144
    assert set(Counter(item.scope for item in dataset.fixtures).values()) == {100}
    assert Counter(item.category for item in dataset.queries) == {
        "one_hop_relation": 36,
        "two_hop_relation": 36,
        "semantic_nonrelation": 36,
        "temporal_incomplete_path": 36,
    }
    assert Counter(item.partition for item in dataset.queries) == {
        "sealed": 108,
        "adversarial": 36,
    }


def test_combined_dataset_has_cross_owner_name_collisions_by_design() -> None:
    dataset = load_dataset(DATASET)
    names_to_scopes: dict[str, set[str]] = {}
    for entity in dataset.entities:
        names_to_scopes.setdefault(entity.name, set()).add(entity.scope)

    repeated = {
        name: scopes for name, scopes in names_to_scopes.items() if len(scopes) >= 3
    }
    assert "黄铜星盘" in repeated
    assert "许澄" in repeated
    assert "临江公寓" in repeated
    assert all(len(scopes) == 3 for scopes in repeated.values())


def test_combined_v2_preserves_density_but_makes_provider_prompts_unique() -> None:
    committed = json.loads(DATASET_V2.read_text("utf-8"))
    assert committed == build_dataset_v2()
    dataset = load_dataset(DATASET_V2)

    assert dataset.fingerprint == EXPECTED_V2_FINGERPRINT
    assert len(dataset.scopes) == 36
    assert len(dataset.fixtures) == 3_600
    assert len(dataset.queries) == 144
    assert len({item.query for item in dataset.queries}) == 144
    assert len({(item.query, item.anchor) for item in dataset.queries}) == 144


def test_combined_dataset_separates_required_related_and_hard_forbidden() -> None:
    dataset = load_dataset(DATASET)
    by_category = {
        category: [item for item in dataset.queries if item.category == category]
        for category in {item.category for item in dataset.queries}
    }

    assert all(
        len(item.required_routes) == 1
        and len(item.required_routes[0]) == 1
        and len(item.required_memory_ids) == 1
        and item.answerable
        for item in by_category["one_hop_relation"]
    )
    assert all(
        len(item.required_routes) == 1
        and len(item.required_routes[0]) == 2
        and len(item.required_memory_ids) == 2
        and item.answerable
        for item in by_category["two_hop_relation"]
    )
    assert all(
        item.required_routes == []
        and len(item.required_memory_ids) == 1
        and item.answerable
        for item in by_category["semantic_nonrelation"]
    )
    assert all(
        len(item.required_routes[0]) == 2
        and item.required_memory_ids == []
        and len(item.related_memory_ids) == 1
        and len(item.hard_forbidden_memory_ids) == 1
        and not item.answerable
        for item in by_category["temporal_incomplete_path"]
    )


def test_combined_dataset_rejects_cross_scope_provenance_and_label_overlap() -> None:
    cross_scope = cast(dict[str, Any], build_dataset())
    cross_scope["edges"][0]["scope"] = "s99"
    with pytest.raises(ValueError, match="cross-scope topology"):
        CombinedRetrievalDataset.model_validate(cross_scope)

    overlapping = cast(dict[str, Any], build_dataset())
    query = next(item for item in overlapping["queries"] if item["answerable"])
    query["related_memory_ids"] = list(query["required_memory_ids"])
    with pytest.raises(ValueError, match="evidence labels overlap"):
        CombinedRetrievalDataset.model_validate(overlapping)


def test_combined_dataset_rejects_missing_category_coverage() -> None:
    raw = cast(dict[str, Any], build_dataset())
    raw["queries"] = [
        item for item in raw["queries"] if item["category"] != "semantic_nonrelation"
    ]
    raw["requirements"]["min_queries"] = 108
    raw["requirements"]["min_queries_per_scope"] = 3
    with pytest.raises(ValueError, match="category_semantic_nonrelation below minimum"):
        CombinedRetrievalDataset.model_validate(raw)
