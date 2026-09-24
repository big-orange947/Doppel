"""Contracts for the frozen combined live retrieval runner."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import pytest

from benchmarks.combined_retrieval_live import (
    _summarize,
    load_topologies,
    retrieval_quality_gate,
)
from benchmarks.combined_retrieval_quality import load_dataset

ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "benchmarks/datasets/combined-retrieval-zh-v2.json"


def _topology_report() -> dict[str, object]:
    dataset = load_dataset(DATASET)
    return {
        "binding": {"dataset_fingerprint": dataset.fingerprint},
        "acquisition": {
            "complete": True,
            "completed_case_count": len(dataset.queries),
        },
        "quality_gate": {"passed": True, "failures": []},
        "metrics": {},
        "rows": [
            {
                "case_id": item.case_id,
                "observed_topologies": [],
                "error": "",
            }
            for item in dataset.queries
        ],
    }


def test_topology_report_requires_complete_fingerprint_bound_cases(
    tmp_path: Path,
) -> None:
    dataset = load_dataset(DATASET)
    path = tmp_path / "topology.json"
    path.write_text(json.dumps(_topology_report()), "utf-8")

    topologies, report = load_topologies(path, dataset)

    assert len(topologies) == 144
    assert all(not value for value in topologies.values())
    assert report["quality_gate"] == {"passed": True, "failures": []}

    wrong = _topology_report()
    wrong["binding"] = {"dataset_fingerprint": "wrong"}
    path.write_text(json.dumps(wrong), "utf-8")
    with pytest.raises(ValueError, match="fingerprint mismatch"):
        load_topologies(path, dataset)

    incomplete = _topology_report()
    incomplete["acquisition"] = {
        "complete": False,
        "completed_case_count": 143,
    }
    path.write_text(json.dumps(incomplete), "utf-8")
    with pytest.raises(ValueError, match="incomplete"):
        load_topologies(path, dataset)


def _row(
    case_id: str,
    category: str,
    ids: list[str],
    required: list[str],
    *,
    answerable: bool = True,
) -> dict[str, object]:
    return {
        "case_id": case_id,
        "category": category,
        "partition": "sealed" if answerable else "adversarial",
        "ids": ids,
        "required": required,
        "related": [],
        "hard_forbidden": [],
        "answerable": answerable,
        "scope_leakage": 0,
        "ineligible_hits": 0,
        "orphan_provenance": 0,
        "latency_ms": 10.0,
        "estimated_context_characters": 20,
        "sources": [["semantic"] for _ in ids],
        "complete_path_returned": False,
    }


def test_profile_metrics_and_gate_measure_two_hop_gain_separately() -> None:
    base_rows = [
        _row("one", "one_hop_relation", ["a"], ["a"]),
        _row("two", "two_hop_relation", ["b"], ["b", "c"]),
        _row("semantic", "semantic_nonrelation", ["d"], ["d"]),
        _row(
            "temporal", "temporal_incomplete_path", ["e"], [], answerable=False
        ),
    ]
    hybrid_rows = [
        base_rows[0],
        _row("two", "two_hop_relation", ["b", "c"], ["b", "c"]),
        base_rows[2],
        base_rows[3],
    ]
    path_rows = [
        _row("one", "one_hop_relation", ["a"], ["a"]),
        _row("two", "two_hop_relation", ["b", "c"], ["b", "c"]),
        _row("semantic", "semantic_nonrelation", [], ["d"]),
        _row("temporal", "temporal_incomplete_path", [], [], answerable=False),
    ]
    profiles = {
        "independent_lexical_vector": _summarize(base_rows),
        "typed_path": _summarize(path_rows),
        "assembled_hybrid": _summarize(hybrid_rows),
    }

    assert profiles["independent_lexical_vector"]["evidence_recall_at_5"] == 0.75
    assert profiles["assembled_hybrid"]["evidence_recall_at_5"] == 1.0
    assert profiles["independent_lexical_vector"]["by_category"][
        "two_hop_relation"
    ]["complete_evidence_rate_at_10"] == 0.0
    assert profiles["assembled_hybrid"]["by_category"]["two_hop_relation"][
        "complete_evidence_rate_at_10"
    ] == 1.0

    gate = retrieval_quality_gate(
        profiles,
        Counter(),
        topology_gate={"passed": True},
        graph_cleaned=True,
        postgres_reset=True,
    )
    assert gate["ok"] is True
    assert gate["failures"] == []


def test_gate_never_allows_topology_failure_to_hide_behind_vector_recall() -> None:
    rows = [
        _row("one", "one_hop_relation", ["a"], ["a"]),
        _row("two", "two_hop_relation", ["b", "c"], ["b", "c"]),
        _row("semantic", "semantic_nonrelation", ["d"], ["d"]),
        _row("temporal", "temporal_incomplete_path", [], [], answerable=False),
    ]
    summary = _summarize(rows)
    profiles = {
        "independent_lexical_vector": summary,
        "typed_path": summary,
        "assembled_hybrid": summary,
    }

    gate = retrieval_quality_gate(
        profiles,
        Counter(),
        topology_gate={"passed": False},
        graph_cleaned=True,
        postgres_reset=True,
    )

    assert gate["ok"] is False
    assert "topology_gate" in gate["failures"]
    assert "two_hop_complete_gain" in gate["failures"]
