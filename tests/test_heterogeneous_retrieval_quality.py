"""Offline contract tests for the frozen heterogeneous retrieval corpus."""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from benchmarks.build_heterogeneous_retrieval_v1 import build_dataset
from benchmarks.heterogeneous_retrieval_quality import (
    HeterogeneousRetrievalDataset,
    load_dataset,
)

DATASET_PATH = (
    Path(__file__).resolve().parents[1]
    / "benchmarks"
    / "datasets"
    / "heterogeneous-retrieval-zh-v1.json"
)


def _dataset() -> HeterogeneousRetrievalDataset:
    return load_dataset(DATASET_PATH)


def _mutable_dataset() -> dict[str, Any]:
    return _dataset().model_dump(mode="json")


def test_committed_corpus_is_deterministic_and_complete() -> None:
    committed = _dataset()
    rebuilt = HeterogeneousRetrievalDataset.model_validate(build_dataset())

    assert rebuilt.fingerprint == committed.fingerprint
    assert len(committed.scopes) == 48
    assert len(committed.memories) == 9_216
    assert len(committed.entities) == 144
    assert len(committed.edges) == 96
    assert len(committed.queries) == 480
    assert Counter(query.partition for query in committed.queries) == {
        "dev": 120,
        "sealed": 280,
        "adversarial": 80,
    }
    assert set(Counter(query.category for query in committed.queries).values()) == {
        48
    }
    assert set(Counter(query.scope for query in committed.queries).values()) == {10}
    assert set(Counter(memory.scope for memory in committed.memories).values()) == {
        192
    }


def test_partitions_are_owner_disjoint_and_queries_are_unique() -> None:
    dataset = _dataset()
    owners_by_partition = {
        partition: {
            scope.user_id
            for scope in dataset.scopes.values()
            if scope.partition == partition
        }
        for partition in ("dev", "sealed", "adversarial")
    }

    assert owners_by_partition["dev"].isdisjoint(owners_by_partition["sealed"])
    assert owners_by_partition["dev"].isdisjoint(
        owners_by_partition["adversarial"]
    )
    assert owners_by_partition["sealed"].isdisjoint(
        owners_by_partition["adversarial"]
    )
    assert len({query.query for query in dataset.queries}) == len(dataset.queries)


def test_temporal_count_and_relation_gold_are_explicit() -> None:
    dataset = _dataset()
    memories = {memory.memory_id: memory for memory in dataset.memories}
    queries = {query.case_id: query for query in dataset.queries}

    current = queries["q-u01-current-residence"]
    temporary = queries["q-u01-temporary-asof"]
    count = queries["q-u01-travel-count"]
    one_hop = queries["q-u01-holder"]
    two_hop = queries["q-u01-object-city"]

    assert memories[current.required_memory_ids[0]].fact_key == "residence:home"
    assert memories[temporary.required_memory_ids[0]].valid_to.startswith("2026-04")
    assert count.expected_count == 2
    assert len({memories[item].event_key for item in count.required_memory_ids}) == 2
    assert {
        memories[item].event_key for item in count.related_memory_ids
    } & {memories[item].event_key for item in count.required_memory_ids}
    assert all(
        memories[item].temporal_status == "cancelled"
        for item in count.hard_forbidden_memory_ids
    )
    assert [len(route) for route in one_hop.required_routes] == [1]
    assert [len(route) for route in two_hop.required_routes] == [2]


def test_cross_conversation_subject_correction_and_related_only_contracts() -> None:
    dataset = _dataset()
    memories = {memory.memory_id: memory for memory in dataset.memories}
    queries = {query.case_id: query for query in dataset.queries}

    cross = queries["q-u01-cross-conversation"]
    correction = queries["q-u01-subject-correction"]
    unknown = queries["q-u01-buyer-unknown"]

    assert all(
        memories[item].conversation_id != cross.conversation_id
        for item in cross.required_memory_ids
    )
    assert all(
        memories[item].subject_id == correction.subject_id
        for item in correction.required_memory_ids
    )
    assert any(
        memories[item].subject_id != correction.subject_id
        for item in correction.hard_forbidden_memory_ids
    )
    assert not unknown.answerable
    assert not unknown.required_memory_ids
    assert unknown.related_memory_ids


def test_validator_rejects_cross_scope_evidence_label() -> None:
    payload = _mutable_dataset()
    payload["queries"][0]["required_memory_ids"] = ["m-u02-home"]

    with pytest.raises(ValidationError, match="invalid evidence label"):
        HeterogeneousRetrievalDataset.model_validate(payload)


def test_validator_rejects_duplicate_query_text() -> None:
    payload = _mutable_dataset()
    payload["queries"][1]["query"] = payload["queries"][0]["query"]

    with pytest.raises(ValidationError, match="duplicate full query text"):
        HeterogeneousRetrievalDataset.model_validate(payload)


def test_validator_rejects_reversed_edge_validity() -> None:
    payload = _mutable_dataset()
    payload["edges"][0]["invalid_at"] = "2023-01-01T00:00:00+08:00"

    with pytest.raises(ValidationError, match="reversed validity"):
        HeterogeneousRetrievalDataset.model_validate(payload)
