"""Dry-run, cache, and budget contracts for the V4 decision runner."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from benchmarks.relation_path_decision_live import build_plan, execute_live
from benchmarks.relation_path_decision_quality import expected_decision
from benchmarks.relation_path_planner_live import DEFAULT_CATALOG, DEFAULT_DATASET
from benchmarks.relation_path_planner_quality import (
    load_dataset,
    load_relation_catalog,
)
from doppel_memory.intelligence import StructuredGenerationRequest


class _GoldDecisionModel:
    name = "tests.gold-live-path-decision-model"
    version = "1"

    def __init__(self, by_query: dict[str, Any]) -> None:
        self.by_query = by_query
        self.calls = 0

    async def generate(self, request: StructuredGenerationRequest) -> dict[str, Any]:
        self.calls += 1
        case = self.by_query[str(request.input["query"])]
        decision, reason = expected_decision(case)
        return {
            "schema_version": 4,
            "operation": "lookup",
            "temporal_view": "unbounded",
            "search_text": str(request.input["query"]),
            "entity_mentions": case.expected_entity_mentions,
            "relation_types": [],
            "subject": "owner",
            "subject_id": "untrusted",
            "path_decision": decision,
            "path_reason": reason,
            "path_steps": [
                step.model_dump(mode="json") for step in case.expected_path_steps
            ],
            "path_confidence": 0.9 if case.expected_path_steps else 0,
        }


def _model() -> _GoldDecisionModel:
    dataset = load_dataset(DEFAULT_DATASET)
    return _GoldDecisionModel({case.query: case for case in dataset.cases})


def test_v4_dry_run_labels_every_partition_as_opened_and_has_no_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DOPPEL_API_KEY", "must-not-appear")
    plan = build_plan(
        dataset_path=DEFAULT_DATASET,
        catalog_path=DEFAULT_CATALOG,
        partitions=["dev", "heldout", "adversarial"],
        model="deepseek-v4-flash",
        base_url="https://api.deepseek.com",
        schema_mode="json_object",
        max_completion_tokens=1024,
        max_tokens_parameter="max_tokens",
        thinking="disabled",
        max_calls=32,
        cache_enabled=True,
    )

    assert plan["case_counts"] == {"dev": 11, "heldout": 12, "adversarial": 9}
    assert plan["selected_case_count"] == 32
    assert plan["corpus_role"] == "opened_regression"
    assert plan["eligible_as_unseen_evidence"] is False
    assert plan["paid_calls_enabled"] is False
    assert "must-not-appear" not in json.dumps(plan)


@pytest.mark.asyncio
async def test_v4_live_regression_caches_all_raw_outputs(tmp_path: Path) -> None:
    dataset = load_dataset(DEFAULT_DATASET)
    definitions = load_relation_catalog(DEFAULT_CATALOG)
    model = _model()
    partitions = ["dev", "heldout", "adversarial"]

    first = await execute_live(
        dataset=dataset,
        definitions=definitions,
        model=model,
        partitions=partitions,
        cache_dir=tmp_path,
        max_calls=32,
        provider_metadata={"model": "fake"},
    )
    second = await execute_live(
        dataset=dataset,
        definitions=definitions,
        model=model,
        partitions=partitions,
        cache_dir=tmp_path,
        max_calls=0,
        provider_metadata={"model": "fake"},
    )

    assert model.calls == 32
    assert first["decision_metrics"]["decision_accuracy"] == 1
    assert first["decision_metrics"]["over_bound_reason_accuracy"] == 1
    assert first["budget"]["provider_calls"] == 32
    assert second["cache"]["hits"] == 32
    assert second["budget"]["provider_calls"] == 0
    assert second["execution"]["complete"] is True
