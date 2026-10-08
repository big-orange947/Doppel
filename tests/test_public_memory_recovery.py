"""Recovery preflight/checkpoint/accounting contracts; no services or paid calls."""

from __future__ import annotations

import copy
import sqlite3

import pytest

from benchmarks import public_memory_recovery as recovery
from benchmarks.public_longmemeval import prepare_case
from benchmarks.public_memory_ingestion import build_ingestion_plan
from doppel_memory.openai_compatible import OpenAICompatibleStructuredOutputConfig


def fixture():
    case = prepare_case(
        {
            "question_id": "synthetic",
            "question_type": "single-session-user",
            "question": "NOT_FOR_EXTRACTION",
            "answer": "GOLD_NOT_FOR_EXTRACTION",
            "question_date": "2024/01/03 12:00",
            "answer_session_ids": ["s"],
            "haystack_session_ids": ["s"],
            "haystack_dates": ["2024/01/01 12:00"],
            "haystack_sessions": [
                [{"role": "user", "content": "Source", "has_answer": True}]
            ],
        },
        dataset_namespace="synthetic",
    ).runtime
    manifest = {
        "run_namespace": "synthetic-run",
        "max_messages": 1,
        "source_sha256": "a" * 64,
        "manifest_fingerprint": "b" * 64,
        "temporal_policy": "full-supplied-haystack",
    }
    ingestion = build_ingestion_plan(
        [case],
        manifest,
        OpenAICompatibleStructuredOutputConfig(model="fake", schema_mode="json_object"),
        max_calls=1,
    )
    key = ingestion["chunks"][0]["write_key"]
    parent = {
        "plan": ingestion,
        "status": "failed",
        "all_histories_ingested": False,
        "stopped": {
            "stage": "extraction",
            "code": "stage-execution-failed",
            "write_key": key,
        },
        "audit": {
            "chunks": [
                {
                    "write_key": key,
                    "completed": False,
                    "proposal_stage_persisted": False,
                    "analysis_diagnostics": None,
                }
            ]
        },
        "usage_cumulative": {
            "ledger": {
                "attempts_reserved": 1,
                "token_accounting_complete": True,
                "reported_tokens": {"total_tokens": 100},
            }
        },
    }
    return [case], manifest, parent


def plan_for(cases, manifest, parent, *, journal_sha="c" * 64):
    return recovery.build_plan(
        cases,
        manifest,
        parent,
        parent_report_sha="d" * 64,
        journal_sha=journal_sha,
        cache={"output.json": "e" * 64},
    )


def test_unchanged_request_and_new_budget_binding():
    cases, manifest, parent = fixture()
    plan = plan_for(cases, manifest, parent)
    assert plan["ingestion_plan"] == parent["plan"]
    assert plan["max_new_calls"] == plan["max_new_chunks"] == 1
    assert plan["generation_settings_changed"] is False
    assert "GOLD_NOT" not in str(plan) and "NOT_FOR_EXTRACTION" not in str(plan)
    changed = plan_for(cases, manifest, parent, journal_sha="f" * 64)
    assert changed["plan_fingerprint"] != plan["plan_fingerprint"]


@pytest.mark.parametrize(
    "field,value", [("status", "complete"), ("all_histories_ingested", True)]
)
def test_nonfailed_parent_rejected(field, value):
    cases, manifest, parent = fixture()
    parent[field] = value
    with pytest.raises(ValueError, match="failed extraction"):
        plan_for(cases, manifest, parent)


@pytest.mark.parametrize("mutation", ["write_key", "observed", "provider_config"])
def test_parent_binding_rejected(mutation):
    cases, manifest, parent = fixture()
    if mutation == "write_key":
        parent["audit"]["chunks"][0]["write_key"] = "wrong"
    elif mutation == "observed":
        parent["audit"]["chunks"][0]["analysis_diagnostics"] = {}
    else:
        parent["plan"]["provider_config"]["temperature"] = 0.9
    with pytest.raises(ValueError):
        plan_for(cases, manifest, parent)


def make_journal(path):
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE example (id INTEGER PRIMARY KEY, status TEXT)")
        db.execute("INSERT INTO example VALUES (1,'pending')")


def test_clone_preserves_parent_and_refuses_overwrite(tmp_path):
    source, destination = tmp_path / "old.sqlite3", tmp_path / "new.sqlite3"
    make_journal(source)
    digest = recovery.file_sha(source)
    recovery.clone_journal(source, destination, digest)
    assert recovery.file_sha(source) == digest
    with sqlite3.connect(destination) as db:
        assert db.execute("SELECT status FROM example").fetchone() == ("pending",)
    with pytest.raises(ValueError, match="fresh"):
        recovery.clone_journal(source, destination, digest)
    with pytest.raises(ValueError, match="changed"):
        recovery.clone_journal(source, tmp_path / "other.sqlite3", "wrong")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "identity,limit,chunks",
    [
        ("invalid", 1, 1),
        ("recovery-observe-v1:" + "a" * 64, 2, 1),
        ("recovery-observe-v1:" + "a" * 64, 1, 2),
        ("recovery-observe-v1:" + "g" * 64, 1, 1),
    ],
)
async def test_invalid_recovery_caps_rejected_before_provider_or_database(
    tmp_path, identity, limit, chunks
):
    cases, manifest, parent = fixture()
    with pytest.raises(ValueError, match="one-call/one-chunk"):
        await recovery.run_live(
            cases,
            manifest,
            parent["plan"],
            run_dir=tmp_path / "run",
            dsn="UNREACHABLE",
            api_key="NOT_PERSISTED",
            max_new_chunks=chunks,
            embedding_cache_dir=None,
            recovery_budget=(identity, limit),
        )
    assert not (tmp_path / "run" / "usage.sqlite3").exists()


@pytest.mark.asyncio
@pytest.mark.parametrize("success", [True, False])
async def test_one_call_no_downstream_and_original_cost_retained(
    tmp_path, monkeypatch, success
):
    cases, manifest, parent = fixture()
    parent_dir = tmp_path / "parent"
    parent_dir.mkdir()
    make_journal(parent_dir / "ingestion.sqlite3")
    plan = plan_for(
        cases,
        manifest,
        parent,
        journal_sha=recovery.file_sha(parent_dir / "ingestion.sqlite3"),
    )
    observed = []

    async def ingest(*args, **kwargs):
        observed.append(copy.deepcopy(kwargs))
        return {
            "status": "partial" if success else "failed",
            "audit": {
                "chunks": [
                    {"write_key": plan["pending_write_key"], "completed": success}
                ]
            },
            "usage_cumulative": {
                "ledger": {
                    "attempts_reserved": 1,
                    "token_accounting_complete": True,
                    "reported_tokens": {"total_tokens": 50},
                }
            },
        }

    monkeypatch.setattr(recovery, "run_live", ingest)
    result = await recovery.run(
        cases,
        manifest,
        plan,
        run_dir=tmp_path / "run",
        parent_dir=parent_dir,
        dsn="NOT_PERSISTED",
        api_key="NOT_PERSISTED",
        embedding_cache_dir=None,
    )
    assert len(observed) == 1
    assert observed[0]["max_new_chunks"] == observed[0]["recovery_budget"][1] == 1
    assert observed[0]["read_only_cache_dirs"] == [parent_dir / "provider-cache"]
    assert result["status"] == ("observed-success" if success else "failed")
    assert result["aggregate_calls"] == 2 and result["aggregate_reported_tokens"] == 150
    assert result["answers_executed"] is False and result["retrieval_executed"] is False
    assert "NOT_PERSISTED" not in str(result)
    with pytest.raises(ValueError, match="already attempted"):
        await recovery.run(
            cases,
            manifest,
            plan,
            run_dir=tmp_path / "run",
            parent_dir=parent_dir,
            dsn="",
            api_key="",
            embedding_cache_dir=None,
        )
