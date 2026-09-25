"""Offline contract tests for the frozen heterogeneous retrieval corpus."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from benchmarks.build_heterogeneous_retrieval_v1 import build_dataset
from benchmarks.heterogeneous_retrieval_live import (
    ANSWERABLE_CATEGORIES,
    _DatasetPlanner,
    _oracle_path_plan,
    _record,
    _select_queries,
    _summarize_slice,
    quality_gate,
)
from benchmarks.heterogeneous_retrieval_quality import (
    HeterogeneousRetrievalDataset,
    load_dataset,
)
from doppel_memory import MemoryScope, PersonalMemoryQueryRequest

DATASET_PATH = (
    Path(__file__).resolve().parents[1]
    / "benchmarks"
    / "datasets"
    / "heterogeneous-retrieval-zh-v1.json"
)
RESULT_SCHEMA_PATH = (
    Path(__file__).resolve().parents[1]
    / "benchmarks"
    / "heterogeneous-retrieval-result.schema.json"
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


def test_result_schema_is_bound_to_the_new_runner() -> None:
    schema = json.loads(RESULT_SCHEMA_PATH.read_text("utf-8"))

    assert schema["$schema"].endswith("2020-12/schema")
    assert (
        schema["$defs"]["base"]["properties"]["runner"]["const"]
        == "doppel.heterogeneous-retrieval-live.v1"
    )
    assert schema["$defs"]["rate"] == {
        "type": "number",
        "minimum": 0,
        "maximum": 1,
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


def test_live_runner_keeps_sealed_partitions_closed_without_switch() -> None:
    dataset = _dataset()

    assert len(_select_queries(dataset, "dev", sealed_first_run=False)) == 120
    with pytest.raises(ValueError, match="sealed-first-run"):
        _select_queries(dataset, "all", sealed_first_run=False)
    with pytest.raises(ValueError, match="only valid"):
        _select_queries(dataset, "dev", sealed_first_run=True)
    assert len(_select_queries(dataset, "all", sealed_first_run=True)) == 480


@pytest.mark.asyncio
async def test_oracle_planner_supplies_labels_but_no_scope_authority() -> None:
    dataset = _dataset()
    queries = {query.case_id: query for query in dataset.queries}
    scope = MemoryScope(user_id="owner-01:run", agent_id="agent")
    request = PersonalMemoryQueryRequest.model_validate(
        {
            "query": queries["q-u01-travel-count"].query,
            "now": "2026-09-25T00:00:00+00:00",
            "default_subject": "owner",
            "default_subject_id": scope.user_id,
        }
    )

    count = await _DatasetPlanner(
        queries["q-u01-travel-count"], scope
    ).plan(request)
    historical = await _DatasetPlanner(
        queries["q-u01-temporary-asof"], scope
    ).plan(request)

    assert count.operation == "count"
    assert count.temporal_view == "prior"
    assert historical.temporal_view == "as_of"
    assert historical.as_of is not None
    assert not hasattr(count, "scopes")


def test_oracle_path_and_memory_projection_preserve_contract_fields() -> None:
    dataset = _dataset()
    queries = {query.case_id: query for query in dataset.queries}
    memories = {memory.memory_id: memory for memory in dataset.memories}
    scope = MemoryScope(user_id="owner-01:run", agent_id="agent")

    one_hop = _oracle_path_plan(queries["q-u01-holder"], scope)
    two_hop = _oracle_path_plan(queries["q-u01-object-city"], scope)
    nonrelation = _oracle_path_plan(queries["q-u01-document"], scope)
    record = _record(memories["m-u01-trip-a"], scope)

    assert [len(route.steps) for route in one_hop.routes] == [1]
    assert [len(route.steps) for route in two_hop.routes] == [2]
    assert not nonrelation.routes
    assert record.metadata["event_key"] == "u01:trip-a"
    assert record.metadata["temporal_status"] == "historical"
    assert record.metadata["subject_id"] == scope.user_id


def test_retrieval_metrics_separate_related_context_from_answer_support() -> None:
    rows = [
        {
            "case_id": "answerable",
            "partition": "dev",
            "category": "document_fact",
            "ids": ["required"],
            "required": ["required"],
            "related": [],
            "hard_forbidden": [],
            "answerable": True,
            "expected_count": None,
            "scope_leakage": 0,
            "subject_violations": 0,
            "ineligible_hits": 0,
            "temporal_violations": 0,
            "orphan_provenance": 0,
            "latency_ms": 1.0,
            "estimated_context_characters": 8,
            "sources": [["semantic"]],
        },
        {
            "case_id": "related-only",
            "partition": "dev",
            "category": "no_answer_related",
            "ids": ["related"],
            "required": [],
            "related": ["related"],
            "hard_forbidden": [],
            "answerable": False,
            "expected_count": None,
            "scope_leakage": 0,
            "subject_violations": 0,
            "ineligible_hits": 0,
            "temporal_violations": 0,
            "orphan_provenance": 0,
            "latency_ms": 2.0,
            "estimated_context_characters": 8,
            "sources": [["semantic"]],
        },
    ]

    summary = _summarize_slice(rows)

    assert summary["evidence_recall_at_5"] == 1.0
    assert summary["complete_evidence_rate_at_10"] == 1.0
    assert summary["related_evidence_recall_at_10"] == 1.0
    assert summary["answerable_queries"] == 1


def test_first_run_gate_requires_complete_selection_and_all_safety_checks() -> None:
    by_category = {
        category: {
            "evidence_recall_at_10": 1.0,
            "related_evidence_recall_at_10": 1.0,
            "exact_episode_count_rate_at_10": 1.0,
        }
        for category in (*ANSWERABLE_CATEGORIES, "no_answer_related")
    }
    profile = {
        "evidence_recall_at_5": 1.0,
        "complete_evidence_rate_at_10": 1.0,
        "mrr": 1.0,
        "hard_forbidden_hits": 0,
        "scope_leakage": 0,
        "subject_violations": 0,
        "ineligible_hits": 0,
        "temporal_violations": 0,
        "orphan_provenance": 0,
        "max_candidates": 20,
        "by_category": by_category,
    }
    profiles = {
        "assembled_oracle_hybrid": profile,
        "assembled_oracle_hybrid_memory_reranking": profile,
    }

    passed = quality_gate(
        profiles,
        Counter(),
        selection_complete=True,
        expected_rerank_calls=480,
        rerank_statuses=Counter({"completed": 480}),
        reorder_membership_violations=0,
        graph_cleaned=True,
        postgres_reset=True,
    )
    diagnostic = quality_gate(
        profiles,
        Counter(),
        selection_complete=False,
        expected_rerank_calls=120,
        rerank_statuses=Counter({"completed": 120}),
        reorder_membership_violations=0,
        graph_cleaned=True,
        postgres_reset=True,
    )

    assert passed["ok"] is True
    assert diagnostic["ok"] is False
    assert diagnostic["status"] == "dev_diagnostic"
    assert diagnostic["failures"] == ["selection_complete"]
