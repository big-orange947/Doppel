"""Same-sample continuation gates and costs, with no live models/databases."""

from copy import deepcopy

import pytest

from benchmarks import public_memory_continuation as continuation
from tests.test_public_memory_expansion import setup


def parent_fixture():
    cases, manifest, plan, _ = setup()
    parent = {
        "status": "observed-success",
        "parent_artifacts_preserved": True,
        "aggregate_calls": 11,
        "aggregate_reported_tokens": 100,
        "ingestion": {
            "plan": plan["ingestion_plan"],
            "audit": {
                "chunks": [
                    {"write_key": c["write_key"], "completed": True}
                    for c in plan["ingestion_plan"]["chunks"][:2]
                ]
            },
            "store_record_audit": {"provenance_failures": 0},
        },
    }
    return cases, manifest, parent


def build(cases, manifest, parent):
    return continuation.build_plan(
        cases,
        manifest,
        parent,
        parent_report_sha="a" * 64,
        journal_sha="b" * 64,
        cache_inventories=[{"one": "c" * 64}],
        reranker_identity={"name": "fake-local"},
    )


def test_budget_same_histories_and_generation_settings():
    cases, manifest, parent = parent_fixture()
    plan = build(cases, manifest, parent)
    assert plan["remaining_chunks"] == plan["ingestion_plan"]["total_chunks"] - 2
    assert plan["max_total_calls"] == plan["remaining_chunks"] + 60
    assert plan["max_reader_calls"] == plan["max_judge_calls"] == 30
    assert plan["ingestion_plan"] == parent["ingestion"]["plan"]
    assert plan["generation_settings_changed"] is False


@pytest.mark.parametrize(
    "mutation", ["failed", "changed-parent", "unfinished", "gap", "provenance"]
)
def test_incompatible_parent_rejected(mutation):
    cases, manifest, parent = parent_fixture()
    if mutation == "failed":
        parent["status"] = "failed"
    elif mutation == "changed-parent":
        parent["parent_artifacts_preserved"] = False
    elif mutation == "unfinished":
        parent["ingestion"]["audit"]["chunks"][0]["completed"] = False
    elif mutation == "gap":
        parent["ingestion"]["audit"]["chunks"][0]["write_key"] = "wrong"
    else:
        parent["ingestion"]["store_record_audit"]["provenance_failures"] = 1
    with pytest.raises(ValueError):
        build(cases, manifest, parent)


def test_all_costs_and_unknown_usage_remain_visible():
    plan = {"parent_calls": 234, "parent_reported_tokens": 1218411}
    ledger = {
        "attempts_reserved": 2,
        "token_accounting_complete": True,
        "reported_tokens": {"total_tokens": 20},
    }
    ingestion = {"usage_cumulative": {"ledger": ledger}}
    answers = {
        "usage": {
            "reader": {"ledger": deepcopy(ledger)},
            "judge": {"ledger": deepcopy(ledger)},
        }
    }
    assert continuation.aggregate_usage(plan, ingestion, answers) == {
        "calls_including_parents": 240,
        "reported_tokens_including_parents": 1218471,
    }
    answers["usage"]["judge"]["ledger"]["token_accounting_complete"] = False
    assert (
        continuation.aggregate_usage(plan, ingestion, answers)[
            "reported_tokens_including_parents"
        ]
        is None
    )


@pytest.mark.asyncio
async def test_failed_ingestion_never_runs_retrieval_or_answers(tmp_path, monkeypatch):
    cases, manifest, parent = parent_fixture()
    plan = build(cases, manifest, parent)
    monkeypatch.setattr(continuation, "clone_journal", lambda *args: None)

    async def ingest(*args, **kwargs):
        assert kwargs["continuation_budget"][1] == plan["remaining_chunks"]
        return {
            "status": "failed",
            "all_histories_ingested": False,
            "usage_cumulative": {
                "ledger": {
                    "attempts_reserved": 1,
                    "token_accounting_complete": False,
                    "reported_tokens": None,
                }
            },
        }

    async def forbidden(*args, **kwargs):
        raise AssertionError("downstream executed")

    monkeypatch.setattr(continuation, "run_live", ingest)
    monkeypatch.setattr(continuation, "run_comparison", forbidden)
    monkeypatch.setattr(continuation, "run_answers", forbidden)
    result = await continuation.run(
        cases,
        manifest,
        plan,
        run_dir=tmp_path / "run",
        parent_dir=tmp_path / "parent",
        cache_dirs=[],
        dsn="NOT_PERSISTED",
        api_key="NOT_PERSISTED",
        embedding_cache_dir=None,
        reranker=None,
    )
    assert result["stage"] == "ingestion" and not result["answers_executed"]
    assert result["usage"]["calls_including_parents"] == 12
    assert "NOT_PERSISTED" not in str(result)
