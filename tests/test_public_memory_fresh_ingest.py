from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from benchmarks import public_memory_fresh_cohort as cohort
from benchmarks import public_memory_fresh_ingest as stage_runner
from tests.test_public_memory_fresh_cohort import SHA, dataset, prior


def bound():
    raw = dataset()
    manifest, ingestion = cohort.prepare(
        raw, source_sha=SHA, priors=[prior(raw)], observed=[], count=7, reserved=2
    )
    plan = cohort.build_plan(manifest, ingestion, input_bindings={"dataset": SHA})
    return raw, manifest, plan


def test_source_prefix_has_exact_attempt_cap_and_no_actual_questions_or_gold():
    raw, manifest, plan = bound()
    cases, stage = stage_runner.prepare_stage(raw, manifest, plan, source_sha=SHA)
    assert len(cases) == 7
    assert stage["prefix_history_count"] == 1
    assert stage["max_provider_attempts"] == manifest["cases"][0]["chunk_count"]
    assert stage["qa_calls"] == stage["graph_calls"] == 0
    assert all(c.query.query == "Withheld until frozen query execution" for c in cases)
    assert "PRIVATE GOLD" not in str(stage) and "PRIVATE QUESTION" not in str(stage)


@pytest.mark.parametrize("mutation", ["source", "manifest", "core"])
def test_stage_rejects_changed_bindings_before_provider_or_db(mutation):
    raw, manifest, plan = bound()
    source_sha = SHA
    if mutation == "source":
        source_sha = "b" * 64
    elif mutation == "manifest":
        manifest["seed"] += 1
    else:
        plan["clock_policy"] = "changed"
    with pytest.raises(ValueError):
        stage_runner.prepare_stage(raw, manifest, plan, source_sha=source_sha)


async def test_cache_only_uses_zero_new_chunk_budget_and_empty_key(
    tmp_path, monkeypatch
):
    raw, manifest, plan = bound()
    cases, stage = stage_runner.prepare_stage(raw, manifest, plan, source_sha=SHA)
    frozen = tmp_path / "stage.json"
    frozen.write_text(json.dumps({"stage": stage}), encoding="utf-8")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "fake-secret")
    monkeypatch.setattr(
        stage_runner, "local_diagnostic_dsn", lambda container: "fake-dsn"
    )

    async def fake(*args, **kwargs):
        assert kwargs["api_key"] == "" and kwargs["max_new_chunks"] == 0
        assert kwargs["cache_only"] and kwargs["continuation_budget"] is None
        return {"status": "partial", "llm_calls_this_invocation": 0}

    monkeypatch.setattr(stage_runner, "run_live", fake)
    args = SimpleNamespace(
        frozen_stage=frozen, run_dir=tmp_path / "run", cache_only=True
    )
    result = await stage_runner.execute(args, cases, manifest, plan, stage)
    assert result["ingestion"]["llm_calls_this_invocation"] == 0
    assert "fake-secret" not in json.dumps(result)


async def test_same_live_stage_cannot_accidentally_advance_past_completed_prefix(
    tmp_path,
):
    raw, manifest, plan = bound()
    cases, stage = stage_runner.prepare_stage(raw, manifest, plan, source_sha=SHA)
    frozen = tmp_path / "stage.json"
    frozen.write_text(json.dumps({"stage": stage}), encoding="utf-8")
    journal = tmp_path / "run"
    journal.mkdir()
    (journal / "ingestion.sqlite3").touch()
    args = SimpleNamespace(frozen_stage=frozen, run_dir=journal, cache_only=False)
    with pytest.raises(ValueError, match="existing journal"):
        await stage_runner.execute(args, cases, manifest, plan, stage)
