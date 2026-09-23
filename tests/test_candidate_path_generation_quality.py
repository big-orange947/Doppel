"""Candidate generation remains ontology-bound and is scored without graph access."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import pytest

from benchmarks.candidate_path_generation_live import (
    SEALED_THRESHOLDS,
    quality_gate,
)
from benchmarks.candidate_path_generation_live import (
    main as candidate_live_main,
)
from benchmarks.candidate_path_generation_quality import (
    CandidateGenerationCase,
    CandidateGenerationDataset,
    load_dataset,
    score_candidate_generation,
)
from benchmarks.relation_path_planner_quality import load_relation_catalog
from doppel_memory.intelligence import StructuredGenerationRequest
from doppel_memory.query_path_candidate import (
    REFERENCE_CANDIDATE_RELATION_PATH_INSTRUCTIONS,
    CandidateRelationGenerationRequest,
    ReferenceCandidateRelationPathGenerator,
    ReferenceCandidateRelationPathGeneratorV3,
)
from doppel_memory.relation import RelationPathStep

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "benchmarks/catalogs/personal-relations-v1.json"
DATASET = ROOT / "benchmarks/datasets/candidate-path-generation-zh-v1.json"


class FakeModel:
    name = "fake"
    version = "1"

    def __init__(self, output: dict[str, Any]) -> None:
        self.output = output
        self.request: StructuredGenerationRequest | None = None

    async def generate(self, request: StructuredGenerationRequest) -> dict[str, Any]:
        self.request = request
        return self.output


class SequenceModel:
    name = "sequence"
    version = "1"

    def __init__(self, outputs: list[dict[str, Any]]) -> None:
        self.outputs = list(outputs)
        self.requests: list[StructuredGenerationRequest] = []

    async def generate(self, request: StructuredGenerationRequest) -> dict[str, Any]:
        self.requests.append(request)
        return self.outputs.pop(0)


def _observation(*relation_types: str) -> dict[str, Any]:
    return {
        "topologies": [
            {
                "atoms": [
                    {
                        "relation_types": list(relation_types),
                        "source_ref": "anchor",
                        "target_ref": "answer",
                    }
                ]
            }
        ]
    }


def test_frozen_dataset_has_disjoint_queries_and_valid_gold() -> None:
    dataset = load_dataset(DATASET)
    cases = dataset.cases
    assert dataset.frozen and not dataset.publication_ready
    assert len(cases) == 18
    assert {case.partition for case in cases} == {"dev", "heldout", "adversarial"}
    assert sum(not case.required_routes for case in cases) == 4
    opened_queries = set()
    for name in (
        "relation-path-planner-quality-zh-v1.json",
        "relation-path-planner-quality-zh-v2.json",
        "candidate-relation-path-ablation-zh-v2.json",
    ):
        data = json.loads((ROOT / "benchmarks/datasets" / name).read_text("utf-8"))
        opened_queries.update(
            item["query"] for item in data.get("cases", data.get("queries", []))
        )
    assert not {case.query for case in cases}.intersection(opened_queries)
    catalog = {item.name for item in load_relation_catalog(CATALOG)}
    assert all(
        relation_type in catalog
        for case in cases
        for route in case.required_routes
        for step in route
        for relation_type in step.relation_types
    )


def test_generator_passes_only_question_anchor_and_definitions() -> None:
    model = FakeModel(_observation("stored_in", "located_at"))
    generator = ReferenceCandidateRelationPathGenerator(model)
    observation = asyncio.run(
        generator.generate(
            CandidateRelationGenerationRequest(
                query="收音机在哪里？",
                anchor="收音机",
                relation_type_definitions=load_relation_catalog(CATALOG),
            )
        )
    )
    assert observation.topologies[0].atoms[0].relation_types == [
        "STORED_IN",
        "LOCATED_AT",
    ]
    assert model.request is not None
    assert set(model.request.input) == {"query", "anchor", "relation_type_definitions"}
    assert "scope" not in str(model.request.input).lower()
    assert "折叠拐杖" not in REFERENCE_CANDIDATE_RELATION_PATH_INSTRUCTIONS
    assert "星河救助站" not in REFERENCE_CANDIDATE_RELATION_PATH_INSTRUCTIONS


def test_generator_rejects_unknown_type_and_provider_scope_field() -> None:
    definitions = load_relation_catalog(CATALOG)
    request = CandidateRelationGenerationRequest(
        query="箱子在哪里？", anchor="箱子", relation_type_definitions=definitions
    )
    with pytest.raises(ValueError, match="unknown relation types"):
        asyncio.run(
            ReferenceCandidateRelationPathGenerator(
                FakeModel(_observation("MADE_UP"))
            ).generate(request)
        )
    with pytest.raises(ValueError, match="scope"):
        asyncio.run(
            ReferenceCandidateRelationPathGenerator(
                FakeModel({**_observation("LOCATED_AT"), "scope": "all"})
            ).generate(request)
        )


def test_review_generator_repairs_a_missing_intermediate_hop() -> None:
    initial = _observation("ADOPTED_FROM")
    reviewed = {
        "topologies": [
            {
                "atoms": [
                    {
                        "relation_types": ["ADOPTED_FROM"],
                        "source_ref": "pet",
                        "target_ref": "anchor",
                    },
                    {
                        "relation_types": ["OWNED_BY"],
                        "source_ref": "pet",
                        "target_ref": "answer",
                    },
                ],
                "confidence": 0.9,
            }
        ]
    }
    model = SequenceModel([initial, reviewed])
    observation = asyncio.run(
        ReferenceCandidateRelationPathGeneratorV3(model).generate(
            CandidateRelationGenerationRequest(
                query="从救助站领养的宠物归谁所有？",
                anchor="救助站",
                relation_type_definitions=load_relation_catalog(CATALOG),
            )
        )
    )
    assert observation.model_dump(mode="json") == reviewed
    assert len(model.requests) == 2
    review_input = model.requests[1].input
    assert (
        review_input["candidate_observation"]["topologies"][0]["atoms"]
        == initial["topologies"][0]["atoms"]
    )
    assert "scope" not in review_input
    assert "memory_id" not in str(review_input)


def test_scorer_separates_coverage_from_extra_types_and_no_path() -> None:
    definitions = load_relation_catalog(CATALOG)
    dataset = CandidateGenerationDataset(
        suite="test",
        version="1",
        frozen=False,
        publication_ready=False,
        relation_catalog="test",
        cases=[
            CandidateGenerationCase(
                case_id="yes",
                partition="dev",
                query="钥匙在哪里",
                anchor="钥匙",
                required_routes=[
                    [
                        RelationPathStep(
                            relation_types=["LOCATED_AT"], direction="outbound"
                        )
                    ]
                ],
            ),
            CandidateGenerationCase(
                case_id="no",
                partition="adversarial",
                query="喜欢什么",
                anchor="我",
            ),
        ],
    )
    model = FakeModel(_observation("LOCATED_AT", "STORED_IN"))
    report = asyncio.run(
        score_candidate_generation(
            dataset, ReferenceCandidateRelationPathGenerator(model), definitions
        )
    )
    metrics = report["metrics"]
    assert metrics["required_route_recall"] == 1.0
    assert metrics["extra_types"] == 3  # two on no-path, one on covered route
    assert metrics["false_candidate_on_no_path"] == 1
    assert metrics["extra_routes"] == 1
    assert metrics["errors"] == 0
    assert metrics["one_hop_route_recall"] == 1.0
    assert metrics["no_path_false_candidate_rate"] == 1.0
    assert report["partition_metrics"]["dev"]["required_route_recall"] == 1.0
    assert (
        report["partition_metrics"]["adversarial"]["no_path_false_candidate_rate"]
        == 1.0
    )
    assert report["rows"][0]["observed_topologies"][0]["atoms"][0][
        "relation_types"
    ] == ["LOCATED_AT", "STORED_IN"]


def test_quality_gate_reports_recall_and_noise_failures_separately() -> None:
    passing = {
        "required_one_hop": 1,
        "required_two_hop": 1,
        "no_path_cases": 1,
        "required_route_recall": 0.9,
        "one_hop_route_recall": 0.9,
        "two_hop_route_recall": 0.75,
        "no_path_false_candidate_rate": 0.25,
        "extra_routes_per_case": 0.5,
        "extra_types_per_generated_route": 1.0,
        "invalid_compilation_count": 0,
        "errors": 0,
    }
    assert quality_gate(passing, SEALED_THRESHOLDS)["passed"]
    failing = {**passing, "required_route_recall": 0.5, "extra_routes_per_case": 0.75}
    result = quality_gate(failing, SEALED_THRESHOLDS)
    assert not result["passed"]
    assert result["failures"] == ["required_route_recall", "extra_routes_per_case"]


def test_quality_gate_cannot_pass_an_incomplete_partition_matrix() -> None:
    metrics = {
        "required_one_hop": 6,
        "required_two_hop": 0,
        "no_path_cases": 0,
        "required_route_recall": 1.0,
        "one_hop_route_recall": 1.0,
        "two_hop_route_recall": 1.0,
        "no_path_false_candidate_rate": 0.0,
        "extra_routes_per_case": 0.0,
        "extra_types_per_generated_route": 0.0,
        "invalid_compilation_count": 0,
        "errors": 0,
    }
    result = quality_gate(metrics, SEALED_THRESHOLDS)
    assert not result["passed"]
    assert result["failures"] == ["coverage_matrix_complete"]


def test_dry_run_never_requires_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DOPPEL_API_KEY", raising=False)
    assert candidate_live_main(["--partition", "dev", "--max-calls", "0"]) == 0


def test_cache_only_live_run_never_requires_key_or_network(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("DOPPEL_API_KEY", raising=False)
    output = tmp_path / "cache-only.json"
    assert (
        candidate_live_main(
            [
                "--live",
                "--max-calls",
                "0",
                "--cache-dir",
                str(tmp_path / "empty-cache"),
                "--output",
                str(output),
            ]
        )
        == 1
    )
    report = json.loads(output.read_text("utf-8"))
    assert report["budget"]["provider_calls"] == 0
    assert report["usage"]["calls_with_usage"] == 0
    assert report["metrics"]["errors"] == 18


def test_sealed_review_budget_must_cover_two_calls_per_case(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("DOPPEL_API_KEY", raising=False)
    with pytest.raises(ValueError, match="call budget"):
        candidate_live_main(
            [
                "--live",
                "--sealed-first-run",
                "--review-protocol",
                "--max-calls",
                "18",
                "--output",
                str(tmp_path / "sealed.json"),
            ]
        )
