"""Score model-generated relation candidates without granting graph access.

Gold is never sent to the generator. This is a topology test, not retrieval quality.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from doppel_memory.query_path import PersonalMemoryRelationPathDraftV4
from doppel_memory.query_path_candidate import (
    CandidateRelationGenerationRequest,
    CandidateRelationPathGenerator,
)
from doppel_memory.relation import RelationPathStep, RelationTypeDefinition
from doppel_memory.relation_path_retrieval import build_relation_path_retrieval_plan


class CandidateGenerationCase(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    case_id: str
    partition: Literal["dev", "heldout", "adversarial"]
    query: str
    anchor: str
    required_routes: list[list[RelationPathStep]] = Field(default_factory=list)


class CandidateGenerationDataset(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    suite: str
    version: str
    frozen: bool
    publication_ready: bool
    relation_catalog: str
    cases: list[CandidateGenerationCase] = Field(min_length=1)

    @model_validator(mode="after")
    def _validate_cases(self) -> CandidateGenerationDataset:
        ids = [case.case_id for case in self.cases]
        queries = [case.query for case in self.cases]
        if len(ids) != len(set(ids)) or len(queries) != len(set(queries)):
            raise ValueError("case IDs and queries must be unique")
        for case in self.cases:
            if any(not 1 <= len(route) <= 2 for route in case.required_routes):
                raise ValueError("gold routes must have one or two hops")
        return self


def load_dataset(path: Path) -> CandidateGenerationDataset:
    return CandidateGenerationDataset.model_validate_json(path.read_text("utf-8"))


async def score_candidate_generation(
    dataset: CandidateGenerationDataset,
    generator: CandidateRelationPathGenerator,
    definitions: list[RelationTypeDefinition],
) -> dict[str, Any]:
    """Measure required-path coverage and extra graph routes independently."""

    rows: list[dict[str, Any]] = []
    totals: Counter[str] = Counter()
    partition_totals: dict[str, Counter[str]] = {
        partition: Counter() for partition in ("dev", "heldout", "adversarial")
    }
    for case in dataset.cases:
        error = ""
        routes: list[list[RelationPathStep]] = []
        compilation: dict[str, int] = {}
        try:
            observation = await generator.generate(
                CandidateRelationGenerationRequest(
                    query=case.query,
                    anchor=case.anchor,
                    relation_type_definitions=definitions,
                )
            )
            # A scope-free dummy draft only invokes the same production compiler.
            # No candidate is passed to a graph index by this scorer.
            plan = build_relation_path_retrieval_plan(
                PersonalMemoryRelationPathDraftV4(
                    search_text=case.query,
                    path_decision="abstain",
                    path_reason="nonrelation",
                ),
                candidate_topologies=observation.topologies,
                allowed_relation_types=[item.name for item in definitions],
            )
            routes = [route.steps for route in plan.routes]
            compilation = plan.compilation.model_dump()
        except Exception as exc:  # noqa: BLE001 - report each failed observation
            error = type(exc).__name__
        matched_indexes = {
            index
            for index, gold in enumerate(case.required_routes)
            if any(_route_covers(candidate, gold) for candidate in routes)
        }
        extra_routes = sum(
            not any(_route_covers(route, gold) for gold in case.required_routes)
            for route in routes
        )
        extra_types = sum(
            len(set(step.relation_types) - _gold_types_at_step(case, route, hop))
            for route in routes
            for hop, step in enumerate(route)
        )
        required_one_hop = sum(len(route) == 1 for route in case.required_routes)
        required_two_hop = sum(len(route) == 2 for route in case.required_routes)
        covered_one_hop = sum(
            len(case.required_routes[index]) == 1 for index in matched_indexes
        )
        covered_two_hop = sum(
            len(case.required_routes[index]) == 2 for index in matched_indexes
        )
        row = {
            "case_id": case.case_id,
            "partition": case.partition,
            "required_route_count": len(case.required_routes),
            "covered_route_count": len(matched_indexes),
            "generated_route_count": len(routes),
            "extra_route_count": extra_routes,
            "extra_type_count": extra_types,
            "required_one_hop_count": required_one_hop,
            "covered_one_hop_count": covered_one_hop,
            "required_two_hop_count": required_two_hop,
            "covered_two_hop_count": covered_two_hop,
            "false_candidate_on_no_path": not case.required_routes and bool(routes),
            "compiled_routes": [
                [step.model_dump(mode="json") for step in route] for route in routes
            ],
            "compilation": compilation,
            "error": error,
        }
        rows.append(row)
        for counter in (totals, partition_totals[case.partition]):
            counter["cases"] += 1
            counter["required_routes"] += len(case.required_routes)
            counter["covered_routes"] += len(matched_indexes)
            counter["required_one_hop"] += required_one_hop
            counter["covered_one_hop"] += covered_one_hop
            counter["required_two_hop"] += required_two_hop
            counter["covered_two_hop"] += covered_two_hop
            counter["generated_routes"] += len(routes)
            counter["extra_routes"] += extra_routes
            counter["extra_types"] += extra_types
            counter["no_path_cases"] += not case.required_routes
            counter["false_candidate_on_no_path"] += int(
                row["false_candidate_on_no_path"]
            )
            counter["errors"] += bool(error)
            counter["ambiguous"] += compilation.get("ambiguous", 0)
            counter["over_bound"] += compilation.get("over_bound", 0)
    return {
        "runner": "doppel.candidate-path-generation-quality.v1",
        "dataset": {"suite": dataset.suite, "version": dataset.version},
        "metrics": _summarize(totals),
        "partition_metrics": {
            partition: _summarize(counter)
            for partition, counter in partition_totals.items()
            if counter["cases"]
        },
        "rows": rows,
        "limitations": [
            "Topology coverage does not establish retrieved evidence relevance.",
            "No Neo4j, scope, time, provenance, latency, or answer quality is measured.",
            "Synthetic questions alone are not publication-grade evidence.",
        ],
    }


def _summarize(totals: Counter[str]) -> dict[str, int | float]:
    def ratio(numerator: str, denominator: str, *, empty: float) -> float:
        return totals[numerator] / totals[denominator] if totals[denominator] else empty

    return {
        **dict(totals),
        "required_route_recall": ratio("covered_routes", "required_routes", empty=1.0),
        "one_hop_route_recall": ratio("covered_one_hop", "required_one_hop", empty=1.0),
        "two_hop_route_recall": ratio("covered_two_hop", "required_two_hop", empty=1.0),
        "no_path_false_candidate_rate": ratio(
            "false_candidate_on_no_path", "no_path_cases", empty=0.0
        ),
        "extra_routes_per_case": ratio("extra_routes", "cases", empty=0.0),
        "extra_types_per_generated_route": ratio(
            "extra_types", "generated_routes", empty=0.0
        ),
        "invalid_compilation_count": totals["ambiguous"] + totals["over_bound"],
    }


def _route_covers(
    candidate: list[RelationPathStep], gold: list[RelationPathStep]
) -> bool:
    return len(candidate) == len(gold) and all(
        selected.direction == expected.direction
        and set(expected.relation_types).issubset(selected.relation_types)
        for selected, expected in zip(candidate, gold, strict=True)
    )


def _gold_types_at_step(
    case: CandidateGenerationCase, route: list[RelationPathStep], hop: int
) -> set[str]:
    return {
        relation_type
        for gold in case.required_routes
        if len(gold) == len(route)
        and all(a.direction == b.direction for a, b in zip(route, gold, strict=True))
        for relation_type in gold[hop].relation_types
    }


def report_json(report: dict[str, Any]) -> str:
    return json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
