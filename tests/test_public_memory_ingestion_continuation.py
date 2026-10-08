from __future__ import annotations

import hashlib
import json
import sqlite3

import pytest

from benchmarks import public_memory_ingestion_continuation as continuation


def _fixture(
    tmp_path,
    monkeypatch,
    *,
    prefix=("k0", "k1"),
    cap=2,
    recovered=False,
):
    dataset = tmp_path / "dataset.json"
    dataset.write_text("[]", encoding="utf-8")
    dataset_sha = hashlib.sha256(dataset.read_bytes()).hexdigest()
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"source_sha256": dataset_sha}), encoding="utf-8")
    run_dir = tmp_path / "run"
    ingestion_dir = run_dir / "ingestion"
    cache_dir = ingestion_dir / "provider-cache"
    cache_dir.mkdir(parents=True)
    journal = ingestion_dir / "ingestion.sqlite3"
    journal.write_bytes(b"journal")
    usage = ingestion_dir / "usage.sqlite3"
    database = sqlite3.connect(usage)
    database.execute(
        "CREATE TABLE pilot_calls (call_id INTEGER PRIMARY KEY, status TEXT, usage TEXT)"
    )
    local_attempts = len(prefix) - int(recovered)
    database.executemany(
        "INSERT INTO pilot_calls(status, usage) VALUES (?, '{}')",
        [("succeeded",)] * local_attempts,
    )
    database.commit()
    database.close()
    chunks = [{"write_key": f"k{i}"} for i in range(4)]
    source_plan = {
        "plan_fingerprint": "frozen-plan",
        "source_sha256": dataset_sha,
        "max_calls": 4,
        "provider_config": {"model": "fixture"},
        "miner_config": {},
        "chunks": chunks,
    }
    ingestion_report = {
        "runner": "doppel.public-memory-ingestion.v1",
        "status": "partial",
        "plan": source_plan,
        "audit": {
            "chunks": [
                {"write_key": key, "completed": True} for key in prefix
            ]
        },
        "store_record_audit": {"provenance_failures": 0},
        "usage_cumulative": {
            "ledger": {
                "attempts_reserved": local_attempts,
                "failed_calls_without_diagnostics": 0,
                "token_accounting_complete": True,
            }
        },
        "llm_calls_this_invocation": local_attempts,
    }
    parent = (
        {
            "runner": "doppel.public-memory-recovery-observation.v1",
            "status": "observed-success",
            "plan": {"completed_prefix_chunks": int(recovered)},
            "parent_artifacts_preserved": True,
            "ingestion": ingestion_report,
        }
        if recovered
        else ingestion_report
    )
    parent_report = tmp_path / "parent.json"
    parent_report.write_text(json.dumps(parent), encoding="utf-8")
    monkeypatch.setattr(continuation, "select_diagnostic_cases", lambda *a, **k: [(object(), object())])
    monkeypatch.setattr(continuation, "build_ingestion_plan", lambda *a, **k: source_plan)
    plan = continuation.build_plan(
        dataset,
        manifest,
        parent_report,
        run_dir,
        max_new_chunks=cap,
    )
    return plan, parent, dataset, manifest, parent_report, run_dir


def test_freezes_exact_prefix_and_separate_call_cap(tmp_path, monkeypatch):
    plan, *_ = _fixture(tmp_path, monkeypatch)
    assert plan["parent_completed_chunks"] == 2
    assert plan["remaining_before_block"] == 2
    assert plan["max_new_calls"] == 2
    assert plan["qa_calls"] == 0
    assert plan["plan_fingerprint"]


def test_accepts_recovered_prefix_with_separate_local_ledger(tmp_path, monkeypatch):
    plan, *_ = _fixture(tmp_path, monkeypatch, recovered=True)
    assert plan["parent_completed_chunks"] == 2
    assert plan["inherited_completed_chunks"] == 1
    assert plan["prior_durable_attempts"] == 1


def test_unwraps_ingestion_plan_from_recovery_observation(tmp_path, monkeypatch):
    _, parent, *_ = _fixture(tmp_path, monkeypatch, recovered=True)
    assert continuation._ingestion_report(parent) is parent["ingestion"]


def test_rejects_recovery_parent_that_did_not_preserve_artifacts(tmp_path, monkeypatch):
    _, parent, dataset, manifest, parent_report, run_dir = _fixture(
        tmp_path, monkeypatch, recovered=True
    )
    parent["parent_artifacts_preserved"] = False
    parent_report.write_text(json.dumps(parent), encoding="utf-8")
    with pytest.raises(ValueError, match="preserved recovery"):
        continuation.build_plan(
            dataset, manifest, parent_report, run_dir, max_new_chunks=2
        )


@pytest.mark.parametrize(
    "prefix,cap",
    [(("k1", "k0"), 1), (("k0", "k1", "k2", "k3"), 1), (("k0", "k1"), 0)],
)
def test_rejects_non_prefix_or_incomplete_history_boundary(
    tmp_path, monkeypatch, prefix, cap
):
    with pytest.raises(ValueError):
        _fixture(tmp_path, monkeypatch, prefix=prefix, cap=cap)


def test_rejects_parent_usage_that_does_not_match_prefix(tmp_path, monkeypatch):
    _plan, parent, dataset, manifest, parent_report, run_dir = _fixture(
        tmp_path, monkeypatch
    )
    usage = run_dir / "ingestion" / "usage.sqlite3"
    database = sqlite3.connect(usage)
    database.execute("INSERT INTO pilot_calls(status, usage) VALUES ('failed', '{}')")
    database.commit()
    database.close()
    parent_report.write_text(json.dumps(parent), encoding="utf-8")
    with pytest.raises(ValueError):
        continuation.build_plan(
            dataset, manifest, parent_report, run_dir, max_new_chunks=2
        )


def test_rejects_changed_dataset_source_hash(tmp_path, monkeypatch):
    _, _, dataset, manifest, parent_report, run_dir = _fixture(tmp_path, monkeypatch)
    dataset.write_text("[1]", encoding="utf-8")
    with pytest.raises(ValueError):
        continuation.build_plan(
            dataset, manifest, parent_report, run_dir, max_new_chunks=2
        )
