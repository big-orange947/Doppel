from __future__ import annotations

import hashlib
import json
from types import SimpleNamespace

import pytest

from benchmarks import analyzer_preservation_controls as experiment
from doppel_memory import (
    ReferencePersonalMemoryAnalyzer,
    ReferencePersonalMemoryAnalyzerV9,
)
from doppel_memory.intelligence import REFERENCE_PERSONAL_MEMORY_INSTRUCTIONS


async def test_v8_unchanged_opt_in_v9_same_input_schema_no_rubric_or_case_rules():
    raw = experiment.DEFAULT_CONTROLS.read_bytes()
    dataset = json.loads(raw)
    bound, requests, plan = await experiment.prepare(raw)
    assert (
        hashlib.sha256(REFERENCE_PERSONAL_MEMORY_INSTRUCTIONS.encode()).hexdigest()
        == "ce598e5e628d6f1b23f6da601b209905dcdb97246b67fe699c224ac77dee92cb"
    )
    assert (
        ReferencePersonalMemoryAnalyzer.version == "8"
        and ReferencePersonalMemoryAnalyzerV9.version == "9"
    )
    assert (
        plan["max_analyzer_calls"] == 16
        and plan["max_reader_calls"] == plan["max_judge_calls"] == 0
    )
    for case in dataset["cases"]:
        a, b = [requests[case["id"], p] for p in experiment.PROFILES]
        assert a.input == b.input and a.output_schema == b.output_schema
        assert a.instructions == REFERENCE_PERSONAL_MEMORY_INSTRUCTIONS
        assert (
            a.instructions != b.instructions
            and "Sharing an entity alone" in b.instructions
        )
        assert case["rubric"] not in b.model_dump_json()
        assert "question" not in b.input
        for forbidden in (
            "Converse",
            "six times",
            "studio rental",
            "Colemak",
            "Redpine",
            "membership",
        ):
            assert forbidden not in b.instructions
    assert len(bound) == 8


def factory(cfg, key, observer):
    class Fake:
        name, version = "fake-preservation", "1"

        async def generate(self, request):
            observer({"input_tokens": 10, "output_tokens": 2, "total_tokens": 12})
            source = next(m for m in request.input["messages"] if m["actor"] == "owner")
            return {
                "memories": [
                    {
                        "content": source["text"],
                        "subject": "owner",
                        "evidence_ids": [source["evidence_id"]],
                    }
                ]
            }

    return Fake()


async def balance(key):
    return 5.0


async def test_offline_durable_budget_v9_identity_and_key_removed_replay(
    tmp_path, monkeypatch
):
    bound, _requests, plan = await experiment.prepare(
        experiment.DEFAULT_CONTROLS.read_bytes()
    )
    monkeypatch.setenv("DEEPSEEK_API_KEY", "fake-secret")
    args = SimpleNamespace(run_dir=tmp_path, cache_only=False)
    live = await experiment.execute(
        args, bound, plan, provider_factory=factory, balance_reader=balance
    )
    assert (
        live["status"] == "complete"
        and live["usage"]["ledger"]["attempts_reserved"] == 16
    )
    assert all(
        r["analyzer_version"].startswith(r["profile"][1:] + ".") for r in live["rows"]
    )
    versions = {r["analyzer_version"] for r in live["rows"]}
    assert len(versions) == 2
    monkeypatch.delenv("DEEPSEEK_API_KEY")
    args.cache_only = True
    replay = await experiment.execute(
        args, bound, plan, provider_factory=factory, balance_reader=balance
    )
    assert live["rows"] == replay["rows"]
    assert (
        replay["usage"]["cache_hits_this_instance"] == 16
        and replay["usage"]["cache_misses_this_instance"] == 0
    )
    assert all(
        "fake-secret" not in p.read_text(encoding="utf-8")
        for p in tmp_path.rglob("*.json")
    )


async def test_subject_source_gate_still_quarantines_owner_claim_from_agent(
    tmp_path, monkeypatch
):
    bound, _requests, plan = await experiment.prepare(
        experiment.DEFAULT_CONTROLS.read_bytes()
    )

    def source_factory(cfg, key, observer):
        class Fake:
            name, version = "fake-source-gate", "1"

            async def generate(self, request):
                observer({"input_tokens": 1, "output_tokens": 1, "total_tokens": 2})
                return {
                    "memories": [
                        {
                            "content": m["text"],
                            "subject": "owner",
                            "evidence_ids": [m["evidence_id"]],
                        }
                        for m in request.input["messages"]
                    ]
                }

        return Fake()

    monkeypatch.setenv("DEEPSEEK_API_KEY", "fake")
    result = await experiment.execute(
        SimpleNamespace(run_dir=tmp_path, cache_only=False),
        bound,
        plan,
        provider_factory=source_factory,
        balance_reader=balance,
    )
    for r in result["rows"]:
        if r["case_id"] == "preserve-control-08":
            assert len(r["proposals"]) == 1
            assert r["proposals"][0]["authority"] == "human_self"
            assert r["checkpoint"]["metadata"]["proposal_diagnostics"][
                "evidence_rejection_counts"
            ] == {"subject_source_mismatch": 1}


async def test_failure_not_retried_or_counted_as_semantic_pass(tmp_path, monkeypatch):
    bound, _requests, plan = await experiment.prepare(
        experiment.DEFAULT_CONTROLS.read_bytes()
    )
    calls = []

    def failing(cfg, key, observer):
        class Fake:
            name, version = "failure", "1"

            async def generate(self, request):
                calls.append(1)
                raise RuntimeError("PRIVATE_KEY_OUTPUT")

        return Fake()

    monkeypatch.setenv("DEEPSEEK_API_KEY", "fake")
    args = SimpleNamespace(run_dir=tmp_path, cache_only=False)
    for _ in range(2):
        r = await experiment.execute(
            args, bound, plan, provider_factory=failing, balance_reader=balance
        )
        assert r["status"] == "stopped" and r["rows"][0]["status"] == "failed"
        assert "PRIVATE_KEY_OUTPUT" not in json.dumps(r)
    assert len(calls) == 1


def test_controls_duplicate_source_or_case_fail_closed():
    data = json.loads(experiment.DEFAULT_CONTROLS.read_bytes())
    data["cases"][0]["messages"][1]["id"] = data["cases"][0]["messages"][0]["id"]
    with pytest.raises(ValueError, match="unique"):
        experiment.contexts(data)
