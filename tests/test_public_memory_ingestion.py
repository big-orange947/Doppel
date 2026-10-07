"""Synthetic boundary tests; no model, database service or quality-score claims."""

from __future__ import annotations

import json
import sys
from dataclasses import replace
from pathlib import Path

import pytest

from benchmarks.public_longmemeval import prepare_case
from benchmarks.public_memory_ingestion import (
    _bind_json,
    build_ingestion_plan,
    ingest_histories,
    main,
    preflight_report,
)
from benchmarks.public_memory_pilot import build_manifest
from doppel_memory.consolidation import DeterministicMemoryConsolidator
from doppel_memory.openai_compatible import OpenAICompatibleStructuredOutputConfig
from integrations.aml.contract import write_key
from integrations.aml.ingestion import IngestionFailure


def source(i: int = 0) -> dict:
    return {
        "question_id": f"synthetic-{i}",
        "question_type": "single-session-user",
        "question": "QUESTION_NOT_FOR_INGESTION",
        "answer": "GOLD_NOT_FOR_INGESTION",
        "question_date": "2024/01/03 12:00",
        "answer_session_ids": ["session"],
        "haystack_session_ids": ["session"],
        "haystack_dates": ["2024/01/01 12:00"],
        "haystack_sessions": [
            [
                {
                    "role": "user",
                    "content": f" Raw user source {i} ",
                    "has_answer": True,
                },
                {
                    "role": "assistant",
                    "content": f"Raw assistant source {i}",
                    "has_answer": False,
                },
            ]
        ],
    }


def config() -> OpenAICompatibleStructuredOutputConfig:
    return OpenAICompatibleStructuredOutputConfig(
        model="fake-model",
        base_url="https://example.invalid/v1",
        schema_mode="json_object",
    )


def fixture():
    cases = [
        prepare_case(source(i), dataset_namespace="synthetic").runtime for i in range(2)
    ]
    manifest = {
        "run_namespace": "synthetic-run",
        "max_messages": 1,
        "source_sha256": "a" * 64,
        "manifest_fingerprint": "b" * 64,
        "temporal_policy": "full-supplied-haystack",
    }
    return cases, manifest


def test_plan_excludes_query_gold_preserves_roles_and_source_map() -> None:
    cases, manifest = fixture()
    plan = build_ingestion_plan(cases, manifest, config(), max_calls=4)
    rendered = json.dumps(plan)
    assert "QUESTION_NOT" not in rendered and "GOLD_NOT" not in rendered
    assert "Raw user source" not in rendered
    assert plan["total_messages"] == 4 and plan["total_chunks"] == 4
    assert [row["roles"] for row in plan["chunks"]] == [["user"], ["assistant"]] * 2
    assert [row["source_turn_indices"] for row in plan["chunks"]] == [[0], [1]] * 2
    changed_query = replace(cases[0].query, query="A different question")
    cases[0] = replace(cases[0], query=changed_query)
    assert build_ingestion_plan(cases, manifest, config(), max_calls=4) == plan
    other = config().model_copy(update={"model": "other-model"})
    assert (
        build_ingestion_plan(cases, manifest, other, max_calls=4)["plan_fingerprint"]
        != plan["plan_fingerprint"]
    )
    assert plan["miner_config"]["require_subject_matches_source_actor"] is True
    assert plan["miner_config"]["allowed_source_actors"] == ["agent", "owner"]
    assert preflight_report(plan)["quality_metrics_available"] is False


def test_run_binding_never_overwrites_another_profile(tmp_path: Path) -> None:
    path = tmp_path / "run" / "plan.json"
    _bind_json(path, {"profile": 1})
    original = path.read_bytes()
    _bind_json(path, {"profile": 1})
    with pytest.raises(ValueError, match="different plan"):
        _bind_json(path, {"profile": 2})
    assert path.read_bytes() == original


def test_quarantine_is_explicit_and_cannot_reuse_default_run_binding(
    tmp_path: Path,
) -> None:
    cases, manifest = fixture()
    default = build_ingestion_plan(cases, manifest, config(), max_calls=4)
    explicit_default = build_ingestion_plan(
        cases, manifest, config(), max_calls=4, evidence_error_policy="fail_batch"
    )
    quarantined = build_ingestion_plan(
        cases, manifest, config(), max_calls=4, evidence_error_policy="quarantine"
    )
    assert default == explicit_default
    assert "evidence_error_policy" not in default["miner_config"]
    assert quarantined["miner_config"]["evidence_error_policy"] == "quarantine"
    assert quarantined["plan_fingerprint"] != default["plan_fingerprint"]
    assert quarantined["chunks"] == default["chunks"]
    path = tmp_path / "plan.json"
    _bind_json(path, default)
    original = path.read_bytes()
    with pytest.raises(ValueError, match="different plan"):
        _bind_json(path, quarantined)
    assert path.read_bytes() == original


def test_changed_consolidator_identity_requires_new_run_binding(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cases, manifest = fixture()
    monkeypatch.setattr(DeterministicMemoryConsolidator, "version", "3")
    old = build_ingestion_plan(
        cases, manifest, config(), max_calls=4, evidence_error_policy="quarantine"
    )
    monkeypatch.setattr(DeterministicMemoryConsolidator, "version", "4")
    new = build_ingestion_plan(
        cases, manifest, config(), max_calls=4, evidence_error_policy="quarantine"
    )
    assert new["chunks"] == old["chunks"]
    assert new["provider_config"] == old["provider_config"]
    assert new["analyzer"] == old["analyzer"]
    assert new["miner_config"] == old["miner_config"]
    assert new["plan_fingerprint"] != old["plan_fingerprint"]
    path = tmp_path / "plan.json"
    _bind_json(path, old)
    snapshot = path.read_bytes()
    with pytest.raises(ValueError, match="different plan"):
        _bind_json(path, new)
    assert path.read_bytes() == snapshot


class ScriptedHost:
    def __init__(self) -> None:
        self.rows: dict[str, dict] = {}
        self.calls = []
        self.fail_at: int | None = None

    def audit_report(self):
        return {"chunks": list(self.rows.values()), "quality_metrics_available": False}

    async def ingest(self, scope, request):
        key = write_key(scope, request)
        self.calls.append(key)
        self.rows.setdefault(key, {"write_key": key, "completed": False})
        if len(self.calls) == self.fail_at:
            raise IngestionFailure("DO_NOT_PERSIST_ERROR_TEXT", stage="extraction")
        self.rows[key]["completed"] = True


async def test_prefix_is_partial_and_resume_revalidates_completed_chunks() -> None:
    cases, manifest = fixture()
    host = ScriptedHost()
    first = await ingest_histories(cases, manifest, host=host, max_new_chunks=1)
    assert first["status"] == "partial" and not first["all_histories_ingested"]
    assert first["new_chunks_completed"] == 1 and len(host.calls) == 1
    second = await ingest_histories(cases, manifest, host=host, max_new_chunks=1)
    assert second["status"] == "partial" and second["completed_chunks_replayed"] == 1
    assert second["new_chunks_completed"] == 1 and len(host.calls) == 3
    final = await ingest_histories(cases, manifest, host=host, max_new_chunks=2)
    assert final["status"] == "complete" and final["all_histories_ingested"]
    assert final["completed_chunks_replayed"] == 2
    assert final["new_chunks_completed"] == 2


async def test_first_failed_chunk_stops_and_is_not_skipped_on_resume() -> None:
    cases, manifest = fixture()
    host = ScriptedHost()
    host.fail_at = 2
    first = await ingest_histories(cases, manifest, host=host, max_new_chunks=4)
    assert first["status"] == "failed" and first["new_chunks_completed"] == 1
    failed = first["stopped"]["write_key"]
    assert first["stopped"]["stage"] == "extraction" and len(host.calls) == 2
    assert "DO_NOT_PERSIST" not in json.dumps(first)
    host.fail_at = None
    second = await ingest_histories(cases, manifest, host=host, max_new_chunks=1)
    assert host.calls[-1] == failed and second["new_chunks_completed"] == 1
    assert not second["all_histories_ingested"]


async def test_empty_duplicate_plan_and_invalid_bound_fail() -> None:
    cases, manifest = fixture()
    host = ScriptedHost()
    for histories, limit in [([], 1), (cases + cases, 1), (cases, -1)]:
        with pytest.raises(ValueError):
            await ingest_histories(histories, manifest, host=host, max_new_chunks=limit)
    assert not host.calls


async def test_zero_new_chunks_replays_only_completed_prefix() -> None:
    cases, manifest = fixture()
    host = ScriptedHost()
    await ingest_histories(cases, manifest, host=host, max_new_chunks=2)
    calls = len(host.calls)
    report = await ingest_histories(cases, manifest, host=host, max_new_chunks=0)
    assert report["status"] == "partial"
    assert report["new_chunks_attempted"] == report["new_chunks_completed"] == 0
    assert report["completed_chunks_replayed"] == 2
    assert len(host.calls) - calls == 2


async def test_foreign_journal_fails_before_any_ingestion() -> None:
    cases, manifest = fixture()
    host = ScriptedHost()
    host.rows["foreign"] = {"write_key": "foreign", "completed": True}
    with pytest.raises(ValueError, match="outside"):
        await ingest_histories(cases, manifest, host=host, max_new_chunks=4)
    assert not host.calls


def test_cli_preflight_never_opens_provider_or_database(
    tmp_path: Path, monkeypatch
) -> None:
    from benchmarks import public_memory_ingestion as module

    records = [source(i) for i in range(2)]
    data = tmp_path / "source.json"
    data.write_text(json.dumps(records), encoding="utf-8")
    import hashlib

    manifest = build_manifest(
        records,
        dataset_namespace="synthetic",
        run_namespace="synthetic-run",
        source_sha256=hashlib.sha256(data.read_bytes()).hexdigest(),
        diagnostic_count=1,
        reserved_count=1,
        max_messages=1,
    )
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    output = tmp_path / "preflight.json"

    def forbidden(*args, **kwargs):
        raise AssertionError("preflight touched live dependency")

    monkeypatch.setattr(module, "OpenAICompatibleStructuredOutputModel", forbidden)
    monkeypatch.setattr(module, "PostgreSQLStore", forbidden)
    monkeypatch.setenv("DOPPEL_API_KEY", "SECRET_MUST_NOT_BE_READ_OR_PERSISTED")
    monkeypatch.setenv("DOPPEL_PUBLIC_PILOT_PG_DSN", "invalid-and-never-read")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "pilot",
            "--dataset",
            str(data),
            "--manifest",
            str(manifest_path),
            "--output",
            str(output),
            "--model",
            "fake-model",
            "--base-url",
            "https://example.invalid/v1",
        ],
    )
    main()
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["llm_calls_this_invocation"] == 0
    assert report["mode"] == "preflight-no-provider-no-database"
    assert report["reserved_histories_executed"] is False
    assert "SECRET_MUST_NOT" not in output.read_text(encoding="utf-8")
    with pytest.raises(FileExistsError):
        main()
