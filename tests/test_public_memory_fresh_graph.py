from __future__ import annotations

import copy
import json
import sqlite3

import pytest

pytest.importorskip("graphiti_core")

from benchmarks.public_memory_fresh_graph import graph_plan, scoped_bindings
from benchmarks.public_memory_fresh_ingest import prepare_stage
from integrations.aml.contract import event_ids, payload_fingerprint, write_key
from tests.test_public_memory_fresh_ingest import SHA, bound
from tests.test_public_memory_graph_backfill import fixture


def journal(tmp_path):
    raw, manifest, plan = bound()
    cases, _ = prepare_stage(raw, manifest, plan, source_sha=SHA)
    from integrations.aml.contract import memory_scope

    scope = memory_scope(manifest["run_namespace"], cases[0].user_id)
    db = sqlite3.connect(tmp_path / "ingestion.sqlite3")
    db.executescript(
        "CREATE TABLE writes(key,payload,scope,events,proposals,consolidation,consolidation_done,completion); CREATE TABLE sources(scope,event,memory); CREATE TABLE analysis_observations(key,diagnostics); CREATE TABLE host_profile(id,fingerprint);"
    )
    db.execute("INSERT INTO host_profile VALUES (1,'test-profile')")
    for chunk in cases[0].ingestion_chunks(max_messages=manifest["max_messages"]):
        key = write_key(scope, chunk.request)
        ids = event_ids(scope, chunk.request)
        db.execute(
            "INSERT INTO writes VALUES (?,?,?,?,?,?,?,?)",
            (
                key,
                payload_fingerprint(chunk.request),
                scope.scope_key,
                json.dumps(["memory-" + event for event in ids]),
                "{}",
                "{}",
                1,
                json.dumps(
                    {
                        "completed": True,
                        "write_key": key,
                        "scope_key": scope.scope_key,
                        "payload_fingerprint": payload_fingerprint(chunk.request),
                        "raw_event_count": len(ids),
                    }
                ),
            ),
        )
        db.execute("INSERT INTO analysis_observations VALUES (?,?)", (key, "{}"))
        db.executemany(
            "INSERT INTO sources VALUES (?,?,?)",
            [(scope.scope_key, event, "memory-" + event) for event in ids],
        )
    db.commit()
    db.close()
    return (
        cases[0],
        manifest,
        {
            "plan": plan["ingestion_plan"],
            "audit": {"profile_fingerprint": "test-profile"},
        },
    )


def test_closed_scope_binding_does_not_claim_whole_cohort_complete(tmp_path):
    runtime, manifest, ingestion = journal(tmp_path)
    sources, receipt = scoped_bindings(runtime, manifest, ingestion, tmp_path)
    assert len(sources) == receipt["source_turns"] > 0
    assert receipt["all_fifty_histories_ingested_claimed"] is False
    assert "one-fixed-scope" in receipt["completion_domain"]
    assert "PRIVATE QUESTION" not in str(receipt) and "PRIVATE GOLD" not in str(receipt)


@pytest.mark.parametrize(
    "mutation", ["completion", "payload", "observation", "source", "events"]
)
def test_scoped_binding_rejects_incomplete_or_changed_journal(tmp_path, mutation):
    runtime, manifest, ingestion = journal(tmp_path)
    with sqlite3.connect(tmp_path / "ingestion.sqlite3") as db:
        db.execute(
            {
                "completion": "UPDATE writes SET completion=NULL",
                "payload": "UPDATE writes SET payload='changed'",
                "observation": "DELETE FROM analysis_observations",
                "source": "DELETE FROM sources",
                "events": "UPDATE writes SET events='[]'",
            }[mutation]
        )
    with pytest.raises(ValueError):
        scoped_bindings(runtime, manifest, ingestion, tmp_path)


def test_partial_whole_cohort_can_project_all_eligible_records_of_closed_scope():
    records, scopes, ingestion = fixture()
    ingestion = {**ingestion, "status": "partial", "all_histories_ingested": False}
    chosen = {k: r for k, r in records.items() if r.scope == scopes[0]}
    before = copy.deepcopy(ingestion)
    plan = graph_plan(
        chosen,
        scopes[0],
        ingestion,
        {
            "scope_key": scopes[0].scope_key,
            "source_closed": True,
            "completed_chunks": 1,
            "source_turns": 2,
        },
        max_calls=1500,
    )
    assert plan["selected_records"] == plan["eligible_records"] == 2
    assert "one-fixed-scope" in plan["completion_domain"]
    assert ingestion == before and ingestion["all_histories_ingested"] is False
    assert "source memory" not in str(plan)


def test_graph_plan_rejects_cross_scope_inventory():
    records, scopes, ingestion = fixture()
    with pytest.raises(ValueError, match="escaped"):
        graph_plan(
            records,
            scopes[0],
            ingestion,
            {
                "scope_key": scopes[0].scope_key,
                "source_closed": True,
                "completed_chunks": 1,
                "source_turns": 2,
            },
            max_calls=1500,
        )
