"""Live-runner contracts for V6 relation atoms over opened V2 regression data."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from benchmarks.relation_path_decision_quality import expected_decision
from benchmarks.relation_path_planner_live import DEFAULT_CATALOG
from benchmarks.relation_path_planner_quality import load_dataset, load_relation_catalog
from benchmarks.relation_path_two_stage_live import build_plan, execute_live
from doppel_memory.intelligence import StructuredGenerationRequest

ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "benchmarks/datasets/relation-path-planner-quality-zh-v2.json"


class _GoldAtomModel:
    name = "tests.gold-live-relation-atom-model"
    version = "1"

    def __init__(self, by_query: dict[str, Any]) -> None:
        self.by_query = by_query
        self.calls = 0

    async def generate(self, request: StructuredGenerationRequest) -> dict[str, Any]:
        self.calls += 1
        case = self.by_query[str(request.input["query"])]
        decision, reason = expected_decision(case)
        atoms: list[dict[str, str]] = []
        if decision == "execute":
            current = "anchor"
            for index, step in enumerate(case.expected_path_steps):
                next_ref = (
                    "answer"
                    if index == len(case.expected_path_steps) - 1
                    else f"middle_{index}"
                )
                relation_type = step.relation_types[0]
                if step.direction == "outbound":
                    source_ref, target_ref = current, next_ref
                else:
                    source_ref, target_ref = next_ref, current
                atoms.append(
                    {
                        "relation_type": relation_type,
                        "source_ref": source_ref,
                        "target_ref": target_ref,
                    }
                )
                current = next_ref
            semantics = "exact"
            confidence = 0.9
        elif reason == "over_bound":
            semantics = "exact"
            confidence = 0.9
            atoms = [
                {"relation_type": "HELD_BY", "source_ref": "anchor", "target_ref": "a"},
                {"relation_type": "EMPLOYED_BY", "source_ref": "a", "target_ref": "b"},
                {"relation_type": "LOCATED_AT", "source_ref": "b", "target_ref": "answer"},
            ]
        else:
            semantics = reason
            confidence = 0
        return {
            "schema_version": 6,
            "operation": "lookup",
            "temporal_view": "unbounded",
            "search_text": str(request.input["query"]),
            "entity_mentions": case.expected_entity_mentions,
            "relation_types": [],
            "observed_path_semantics": semantics,
            "anchor_ref": "anchor",
            "answer_ref": "answer",
            "relation_atoms": atoms,
            "relation_atoms_truncated": False,
            "path_confidence": confidence,
        }


def test_v6_dry_run_is_opened_regression_and_declares_atom_protocol() -> None:
    plan = build_plan(
        dataset_path=DATASET,
        catalog_path=DEFAULT_CATALOG,
        partitions=["heldout", "adversarial"],
        model="deepseek-v4-flash",
        base_url="https://api.deepseek.com",
        schema_mode="json_object",
        max_completion_tokens=1024,
        max_tokens_parameter="max_tokens",
        thinking="disabled",
        max_calls=48,
        cache_enabled=True,
        atom_protocol=True,
    )

    assert plan["corpus_role"] == "opened_regression"
    assert plan["eligible_as_unseen_evidence"] is False
    assert plan["planner_protocol"] == "v6_relation_atoms_host_compilation"


@pytest.mark.asyncio
async def test_v6_live_runner_compiles_gold_atoms(tmp_path: Path) -> None:
    dataset = load_dataset(DATASET)
    model = _GoldAtomModel({case.query: case for case in dataset.cases})

    report = await execute_live(
        dataset=dataset,
        definitions=load_relation_catalog(DEFAULT_CATALOG),
        model=model,
        partitions=["heldout", "adversarial"],
        cache_dir=tmp_path,
        max_calls=48,
        provider_metadata={"model": "fake"},
        atom_protocol=True,
    )

    assert model.calls == 48
    assert report["planner_protocol"] == "v6_relation_atoms_host_compilation"
    assert report["metrics"]["exact_path_accuracy"] == 1
    assert report["metrics"]["direction_accuracy"] == 1
    assert report["decision_metrics"]["wrong_execute_count"] == 0
