from __future__ import annotations

import copy
from types import SimpleNamespace

import pytest

pytest.importorskip("graphiti_core")

from benchmarks import public_memory_fresh_query as runner
from benchmarks.public_memory_high_config_first import build_plan
from tests.test_public_memory_fresh_ingest import bound


def query_plan():
    from benchmarks.public_memory_fresh_ingest import prepare_stage
    from integrations.aml.contract import memory_scope
    from tests.test_public_memory_fresh_ingest import SHA

    raw, manifest, cohort = bound()
    cases, _ = prepare_stage(raw, manifest, cohort, source_sha=SHA)
    scope = memory_scope(manifest["run_namespace"], cases[0].user_id)
    base = build_plan(
        {},
        cases[0],
        scope,
        {"plan": {"source": {}}, "definitions": []},
        "corpus",
        {},
        SimpleNamespace(report=dict),
    )
    base["observation_clock"] = {"policy": "provided-history-v1"}
    return raw, manifest, cohort, base, scope


@pytest.mark.parametrize("ordinal", [1, 2])
def test_same_frozen_provider_configs_and_alternating_profile_order(ordinal):
    _, _, cohort, base, _ = query_plan()
    full = runner.profile_plan(base, cohort, ordinal, "full_high_config")
    raw = runner.profile_plan(base, cohort, ordinal, "raw_vector_reranked")
    assert sum(s["max_calls"] for s in full["stages"].values()) == 5
    assert sum(s["max_calls"] for s in raw["stages"].values()) == 3
    assert "planner" not in raw["stages"]
    assert full["stages"]["reader"] == raw["stages"]["reader"]
    assert full["profile_execution_order"] == list(
        runner.PROFILES if ordinal == 1 else reversed(runner.PROFILES)
    )
    assert full["graph_writer_calls"] == full["source_writer_calls"] == 0
    assert "PRIVATE GOLD" not in str(full)


@pytest.mark.parametrize("mutation", ["query", "hybrid", "rerank", "model", "call_cap"])
def test_cohort_configuration_change_is_rejected_before_calls(mutation):
    _, _, cohort, base, _ = query_plan()
    base = copy.deepcopy(base)
    if mutation in {"query", "hybrid", "rerank"}:
        base[mutation + "_config"]["changed"] = True
    elif mutation == "model":
        base["stages"]["reader"]["config"]["model"] = "other"
    else:
        base["stages"]["reader"]["max_calls"] = 100
    with pytest.raises(ValueError):
        runner.profile_plan(base, cohort, 1, "full_high_config")


def test_incomplete_graph_cannot_silently_become_raw_only_high_config():
    _, _, cohort, _, _ = query_plan()
    from benchmarks.public_memory_pilot import _hash

    plan = {
        "source_completion_certificate": {
            "scope_ordinal": 1,
            "cohort_plan_fingerprint": cohort["plan_fingerprint"],
        }
    }
    plan["plan_fingerprint"] = _hash(plan)
    with pytest.raises(ValueError):
        runner.validate_graph(
            {
                "plan": plan,
                "runner": "doppel.public-memory-fresh-scope-graph.v1",
                "status": "partial",
            },
            cohort,
            1,
        )


async def test_raw_execution_uses_exact_three_frozen_providers_without_planner_or_network(
    tmp_path, monkeypatch
):
    from benchmarks.public_longmemeval import prepare_case
    from benchmarks.public_memory_fresh_cohort import NAMESPACE

    raw, manifest, cohort, base, scope = query_plan()
    item = next(r for r in raw if r["question_id"] == manifest["cases"][0]["case_id"])
    prepared = prepare_case(item, dataset_namespace=NAMESPACE)
    plan = runner.profile_plan(base, cohort, 1, "raw_vector_reranked")
    configs, requests = [], []

    def factory(config, key, observer):
        configs.append(config.model_dump(mode="json"))

    class Model:
        def __init__(self, transport, *, ledger, cache_dir, cache_only):
            self.stage = cache_dir.name

        async def generate(self, request):
            requests.append((self.stage, request))
            return {
                "reader": {
                    "answer": "No information in the supplied items.",
                    "abstained": True,
                    "cited_memory_ids": [],
                },
                "task_judge": {
                    "answer_correct": False,
                    "rationale": "Synthetic control.",
                },
                "citation_judge": {
                    "answer_correct": False,
                    "answer_rationale": "Synthetic control.",
                    "citation_support": "not_applicable",
                    "support_rationale": "No factual claim.",
                    "citation_contradiction": False,
                    "evidence": [],
                },
            }[self.stage]

        def report(self):
            return {"provider_calls": 0}

    class Vector:
        async def search(self, *args, **kwargs):
            return []

    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-only-not-real")
    monkeypatch.setattr(runner, "_default_provider_factory", factory)
    monkeypatch.setattr(runner, "PilotStructuredModel", Model)
    result = await runner.raw_answer(
        SimpleNamespace(run_dir=tmp_path, cache_only=False),
        (prepared.runtime, prepared.scoring),
        scope,
        {},
        {},
        Vector(),
        SimpleNamespace(name="fake", version="1", report=dict),
        plan,
    )
    assert result["status"] == "complete", result
    assert [s for s, _ in requests] == ["reader", "task_judge", "citation_judge"]
    assert configs == [cohort["stage_configs"][s]["provider"] for s, _ in requests]
    assert "PRIVATE GOLD" not in str(requests[0][1].input)
    assert not (tmp_path / "planner.sqlite3").exists()
