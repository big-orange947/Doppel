"""Fake-provider new-history pipeline tests, not benchmark performance."""

from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import replace
from pathlib import Path

import pytest

from benchmarks import public_memory_expansion as expansion
from benchmarks.public_context_baseline import select_diagnostic_cases
from benchmarks.public_memory_answer_comparison import AnswerRow
from benchmarks.public_memory_pilot import _hash, build_manifest
from benchmarks.public_memory_reader_v2 import ReaderV2Output
from tests.test_public_memory_answer_comparison import RecordingFactory
from tests.test_public_memory_pilot import records


def setup():
    source = records()
    for i in range(8, 14):
        item = deepcopy(source[0])
        item["question_id"] = f"synthetic-{i}"
        item["haystack_sessions"][0][1]["content"] = f"HISTORY-{i}"
        source.append(item)
    manifest = build_manifest(
        source,
        dataset_namespace="synthetic",
        run_namespace="expansion",
        source_sha256="a" * 64,
        diagnostic_count=10,
        reserved_count=3,
    )
    cases = select_diagnostic_cases(source, manifest, source_sha256="a" * 64)
    plan = expansion.build_plan(
        cases, manifest, reranker_identity={"name": "fake-local"}
    )
    context = (
        {
            "memory_id": "source-1",
            "channel": "raw",
            "role": "user",
            "authority": "human_self",
            "text": "The meeting is on Tuesday.",
            "observed_at": "2024-01-01T00:00:00+00:00",
            "temporal_status": None,
            "valid_from": None,
            "valid_to": None,
        },
    )
    rows = [
        AnswerRow(index, scoring.case_id, profile, runtime, scoring, context)
        for index, (runtime, scoring, profile) in enumerate(
            (r, s, p) for r, s in cases for p in expansion.PROFILES
        )
    ]
    return cases, manifest, plan, rows


def respond(request):
    if "reference_answer" in request.input:
        return {
            "answer_correct": True,
            "answer_rationale": "Fake judgment",
            "citation_support": "supported",
            "support_rationale": "Fake support",
            "citation_contradiction": False,
            "evidence": [
                {
                    "memory_id": "source-1",
                    "quote": "meeting is on Tuesday",
                    "reason": "Fake observation",
                }
            ],
        }
    return {
        "answer": "Tuesday",
        "abstained": False,
        "cited_memory_ids": ["source-1"],
        "derived": None,
    }


def test_plan_fixed_caps_and_raw_ingestion_is_gold_query_blind():
    cases, manifest, plan, _ = setup()
    assert plan["max_reader_calls"] == plan["max_judge_calls"] == 30
    assert plan["max_total_calls"] == plan["ingestion_plan"]["max_calls"] + 60
    changed = [
        (
            replace(r, query=replace(r.query, query="OTHER QUERY")),
            replace(s, answer="OTHER GOLD"),
        )
        for r, s in cases
    ]
    assert (
        expansion.build_plan(
            changed, manifest, reranker_identity={"name": "fake-local"}
        )
        == plan
    )
    assert "GOLD_NOT_IN_MANIFEST" not in json.dumps(plan)


def test_reader_sees_no_gold_old_judgments_or_profile():
    _, _, _, rows = setup()
    request = expansion.reader_request(rows[0])
    assert "GOLD_NOT_IN_MANIFEST" not in json.dumps(request.model_dump(mode="json"))
    assert set(request.input) == {
        "question",
        "question_reference_time",
        "context_items",
    }
    output = ReaderV2Output.model_validate(respond(request))
    judge = expansion.primary_request(rows[0], output)
    assert judge.input["reference_answer"] == rows[0].scoring.answer
    assert "profile" not in judge.input


@pytest.mark.asyncio
async def test_answers_and_judgments_replay_without_new_calls(tmp_path):
    _, _, plan, rows = setup()
    factory = RecordingFactory(respond)
    report = await expansion.run_answers(
        rows,
        plan,
        run_dir=tmp_path,
        api_key="FAKE-KEY",
        cache_only=False,
        provider_factory=factory,
    )
    assert report["status"] == "complete" and len(report["rows"]) == 30
    assert not report["judge_reliability_validated"]
    for summary in report["summary"].values():
        assert summary["questions"] == summary["correctness_denominator"] == 10
    replay = await expansion.run_answers(
        rows,
        plan,
        run_dir=tmp_path,
        api_key="",
        cache_only=True,
        provider_factory=factory,
    )
    assert replay["summary"] == report["summary"]
    assert all(v["new_calls"] == 0 for v in replay["usage"].values())
    assert [r["reader"]["output"] for r in report["rows"]] == [
        r["reader"]["output"] for r in replay["rows"]
    ]
    assert "FAKE-KEY" not in json.dumps(report)
    calls = factory.calls
    with pytest.raises(ValueError, match="cache-only"):
        await expansion.run_answers(
            rows,
            plan,
            run_dir=tmp_path,
            api_key="",
            cache_only=False,
            provider_factory=factory,
        )
    assert factory.calls == calls


@pytest.mark.parametrize("mutation", ["missing", "duplicates", "profiles"])
def test_comparison_requires_every_new_profile_once(mutation):
    cases, _, _, rows = setup()
    source = {
        "status": "complete",
        "rows": [
            {"case_id": r.case_id, "profile": r.profile, "context": list(r.context)}
            for r in rows
        ],
    }
    if mutation == "missing":
        source["rows"].pop()
    elif mutation == "duplicates":
        source["rows"][1] = source["rows"][0]
    else:
        source["rows"][0]["profile"] = "wrong"
    with pytest.raises(ValueError):
        expansion.answer_rows(source, cases)


def test_quote_anchor_is_not_entailment_and_contradiction_is_not_repaired():
    _, _, _, rows = setup()
    output = expansion.PrimaryOutput.model_validate(
        respond(
            expansion.primary_request(
                rows[0],
                ReaderV2Output(
                    answer="Tuesday", abstained=False, cited_memory_ids=["source-1"]
                ),
            )
        )
    )
    assert expansion.primary_checks(rows[0], output)["quotes_anchored"]
    output.evidence[0].quote = "Not in the record"
    assert not expansion.primary_checks(rows[0], output)["quotes_anchored"]
    output.evidence[0].quote = "meeting is on Tuesday"
    output.citation_contradiction = True
    assert expansion.primary_checks(rows[0], output)["contradictory_support_fields"]
    assert output.citation_support == "supported"
    output.evidence = []
    assert expansion.primary_checks(rows[0], output)["missing_required_observations"]


@pytest.mark.asyncio
async def test_incomplete_history_stops_before_retrieval_and_reader(
    tmp_path, monkeypatch
):
    cases, manifest, plan, _ = setup()

    async def partial(*args, **kwargs):
        return {
            "status": "partial",
            "all_histories_ingested": False,
            "llm_calls_this_invocation": 1,
        }

    async def forbidden(*args, **kwargs):
        pytest.fail("downstream executed after incomplete history")

    monkeypatch.setattr(expansion, "ingest_live", partial)
    monkeypatch.setattr(expansion, "run_comparison", forbidden)
    monkeypatch.setattr(expansion, "run_answers", forbidden)
    result = await expansion.run_pipeline(
        cases,
        manifest,
        plan,
        run_dir=tmp_path,
        dsn="fake",
        api_key="",
        embedding_cache_dir=None,
        reranker=None,
        cache_only=False,
    )
    assert result["status"] == "stopped" and not result["answers_executed"]


def test_local_container_credentials_not_printed_or_saved(monkeypatch):
    class Process:
        stdout = json.dumps(
            [
                {
                    "Config": {
                        "Image": "pgvector/pgvector:pg15",
                        "Env": [
                            "POSTGRES_DB=doppel_ablation",
                            "POSTGRES_USER=postgres",
                            "POSTGRES_PASSWORD=FAKE PASSWORD",
                        ],
                    },
                    "State": {"Running": True},
                    "NetworkSettings": {
                        "Ports": {
                            "5432/tcp": [{"HostIp": "0.0.0.0", "HostPort": "5432"}]
                        }
                    },
                }
            ]
        )

    monkeypatch.setattr(expansion.subprocess, "run", lambda *args, **kwargs: Process())
    assert "FAKE%20PASSWORD" in expansion.local_diagnostic_dsn(
        "doppel-ablation-pgvector"
    )
    with pytest.raises(ValueError):
        expansion.local_diagnostic_dsn("unrelated-container")


@pytest.mark.asyncio
async def test_forged_budget_rejected_before_ledger_or_network(tmp_path):
    _, _, plan, rows = setup()
    plan["max_reader_calls"] = 31
    plan["plan_fingerprint"] = _hash(
        {k: v for k, v in plan.items() if k != "plan_fingerprint"}
    )
    factory = RecordingFactory(respond)
    with pytest.raises(ValueError):
        await expansion.run_answers(
            rows,
            plan,
            run_dir=tmp_path / "new",
            api_key="",
            cache_only=False,
            provider_factory=factory,
        )
    assert factory.calls == 0 and not (tmp_path / "new").exists()


@pytest.mark.asyncio
async def test_reranked_only_without_reranker_fails_before_store(monkeypatch):
    from benchmarks.public_memory_comparison import run_comparison

    with pytest.raises(ValueError, match="reranker"):
        await run_comparison(
            [],
            {},
            {},
            run_dir=Path("unused"),
            dsn="unused",
            embedding_cache_dir=None,
            profile_mode="reranked_only",
        )
