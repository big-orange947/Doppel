"""Contracts for the candidate relation-path retrieval ablation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

import pytest

from benchmarks.build_candidate_relation_path_v2 import build_dataset
from benchmarks.candidate_relation_path_ablation import (
    CandidatePathDataset,
    _draft,
    _profile_plan,
    _summarize_profile,
    load_dataset,
)
from doppel_memory import MemoryScope
from doppel_memory.relation_path_retrieval import build_relation_path_retrieval_plan

ROOT = Path(__file__).resolve().parents[1]
DATASET = (
    ROOT / "benchmarks" / "datasets" / "candidate-relation-path-ablation-zh-v2.json"
)
RESULT_SCHEMA = (
    ROOT / "benchmarks" / "candidate-relation-path-ablation-result.schema.json"
)


def test_committed_candidate_path_dataset_is_deterministic_and_draft() -> None:
    committed = json.loads(DATASET.read_text(encoding="utf-8"))
    assert committed == build_dataset()
    dataset = load_dataset(DATASET)

    assert dataset.frozen is False
    assert dataset.publication_ready is False
    assert len(dataset.scopes) == 9
    assert len(dataset.fixtures) == 19
    assert len(dataset.entities) == 29
    assert len(dataset.edges) == 20
    assert len(dataset.queries) == 36
    assert sum(item.recovery_expected for item in dataset.queries) == 8
    assert sum(item.dual_attribution_expected for item in dataset.queries) == 16
    assert {item.category for item in dataset.queries}.issuperset(
        {
            "candidate_recovers_ontology_drift",
            "candidate_topology_rejected",
            "second_hop_not_yet_valid",
            "orphan_second_hop",
        }
    )


def test_candidate_path_dataset_rejects_cross_scope_and_unknown_ontology() -> None:
    cross_scope = cast(dict[str, Any], build_dataset())
    cross_scope["edges"][0]["source_entity_id"] = "e-camera-b-anchor"
    with pytest.raises(ValueError, match="cross-scope topology"):
        CandidatePathDataset.model_validate(cross_scope)

    unknown = cast(dict[str, Any], build_dataset())
    unknown["queries"][0]["candidate_topologies"][0]["atoms"][0][
        "relation_types"
    ].append("UNKNOWN")
    with pytest.raises(ValueError, match="type outside ontology"):
        CandidatePathDataset.model_validate(unknown)


def test_dataset_driven_compilation_rejects_invalid_topologies_locally() -> None:
    dataset = load_dataset(DATASET)
    scope = MemoryScope(user_id="owner", agent_id="agent")
    cases = {
        item.query_id: item
        for item in dataset.queries
        if item.category == "candidate_topology_rejected"
    }

    disconnected = build_relation_path_retrieval_plan(
        _draft(cases["q-candidate-disconnected"], scope),
        candidate_topologies=cases["q-candidate-disconnected"].candidate_topologies,
        allowed_relation_types=dataset.relation_types,
    )
    over_bound = build_relation_path_retrieval_plan(
        _draft(cases["q-candidate-over-bound"], scope),
        candidate_topologies=cases["q-candidate-over-bound"].candidate_topologies,
        allowed_relation_types=dataset.relation_types,
    )

    assert disconnected.routes == []
    assert disconnected.compilation.ambiguous == 1
    assert over_bound.routes == []
    assert over_bound.compilation.over_bound == 1


def test_profile_plan_separates_exact_candidate_and_union_routes() -> None:
    dataset = load_dataset(DATASET)
    case = next(
        item for item in dataset.queries if item.query_id == "q-camera-a-two-hop"
    )
    scope = MemoryScope(user_id="owner", agent_id="agent")
    plan = build_relation_path_retrieval_plan(
        _draft(case, scope),
        candidate_topologies=case.candidate_topologies,
        allowed_relation_types=dataset.relation_types,
    )

    assert [route.mode for route in _profile_plan(plan, "exact").routes] == ["exact"]
    assert [route.mode for route in _profile_plan(plan, "candidate").routes] == [
        "candidate"
    ]
    assert [route.mode for route in _profile_plan(plan, "union").routes] == [
        "exact",
        "candidate",
    ]


def test_candidate_metrics_keep_recovery_noise_and_security_separate() -> None:
    rows = [
        {
            "query_id": "recovered",
            "memory_ids": ["a", "b", "noise"],
            "required_hop_memory_ids": [["a"], ["b"]],
            "forbidden_memory_ids": ["forbidden"],
            "candidate_noise_memory_ids": ["noise"],
            "authorized_scope_key": "scope-a",
            "scope_keys": ["scope-a"],
            "recovery_expected": True,
            "dual_attribution_expected": True,
            "both_attributed": True,
            "dedupe_ok": True,
            "latency_ms": 10.0,
        },
        {
            "query_id": "leak",
            "memory_ids": ["forbidden"],
            "required_hop_memory_ids": [],
            "forbidden_memory_ids": ["forbidden"],
            "candidate_noise_memory_ids": [],
            "authorized_scope_key": "scope-a",
            "scope_keys": ["scope-b"],
            "recovery_expected": False,
            "dual_attribution_expected": False,
            "both_attributed": False,
            "dedupe_ok": False,
            "latency_ms": 20.0,
        },
    ]

    metrics = _summarize_profile(rows)
    assert metrics["evidence_recall"] == 1.0
    assert metrics["recovery_rate"] == 1.0
    assert metrics["candidate_noise_hits"] == 1
    assert metrics["forbidden_hits"] == 1
    assert metrics["scope_leakage"] == 1
    assert metrics["dual_attribution_failures"] == 0
    assert metrics["deduplication_failures"] == 1


def test_candidate_result_schema_tracks_three_profiles() -> None:
    schema = json.loads(RESULT_SCHEMA.read_text(encoding="utf-8"))

    assert schema["properties"]["result_schema_version"]["const"] == 2
    assert schema["properties"]["runner"]["const"] == (
        "doppel.candidate-relation-path-ablation.v2"
    )
    assert set(schema["properties"]["profiles"]["required"]) == {
        "strict_path",
        "candidate_path",
        "exact_candidate_union",
    }
    profile_required = set(schema["$defs"]["profile"]["required"])
    assert {
        "evidence_recall",
        "candidate_noise_hits",
        "forbidden_hits",
        "recovery_rate",
        "dual_attribution_failures",
        "deduplication_failures",
    }.issubset(profile_required)
