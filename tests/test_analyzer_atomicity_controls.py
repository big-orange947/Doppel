from __future__ import annotations

import hashlib
import json
from types import SimpleNamespace

import pytest

from benchmarks import analyzer_atomicity_controls as experiment
from benchmarks import analyzer_preservation_controls as runtime
from doppel_memory import (
    ReferencePersonalMemoryAnalyzer,
    ReferencePersonalMemoryAnalyzerV9,
    ReferencePersonalMemoryAnalyzerV10,
)
from doppel_memory.intelligence import (
    REFERENCE_PERSONAL_MEMORY_INSTRUCTIONS_V9,
    REFERENCE_PERSONAL_MEMORY_INSTRUCTIONS_V10,
)


async def test_prospective_contract_preserves_v9_and_same_schema_inputs():
    raw = experiment.DEFAULT_CONTROLS.read_bytes()
    bound, requests, plan = await experiment.prepare(raw)
    assert hashlib.sha256(
        REFERENCE_PERSONAL_MEMORY_INSTRUCTIONS_V9.encode()
    ).hexdigest() == (
        "08ac7b0a25ecded5b866b1c5d6b300069a57dec5f5d7c4f7673d0ee7f8dd6a13"
    )
    assert ReferencePersonalMemoryAnalyzer.version == "8"
    assert ReferencePersonalMemoryAnalyzerV9.version == "9"
    assert ReferencePersonalMemoryAnalyzerV10.version == "10"
    assert not plan["prior_preservation_gate_passed"]
    assert not plan["old_task_followup_allowed"]
    assert not plan["default_promotion_allowed"]
    assert plan["max_analyzer_calls"] == 16
    assert plan["max_reader_calls"] == plan["max_judge_calls"] == 0
    assert "docs/memory-atomicity.md" in plan["source_sha256"]
    for case in json.loads(raw)["cases"]:
        a, b = [requests[case["id"], p] for p in experiment.PROFILES]
        assert a.input == b.input and a.output_schema == b.output_schema
        assert a.instructions == REFERENCE_PERSONAL_MEMORY_INSTRUCTIONS_V9
        assert b.instructions == REFERENCE_PERSONAL_MEMORY_INSTRUCTIONS_V10
        assert case["rubric"] not in b.model_dump_json()
        for forbidden in (
            "bicycle",
            "dishwasher",
            "telescope",
            "Cedar",
            "LongMemEval",
            "Converse",
        ):
            assert forbidden not in b.instructions
    assert len(bound) == 8


def factory(cfg, key, observer):
    class Fake:
        name, version = "fake-atomicity", "1"

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


async def test_fresh_budget_identity_cache_only_replay_no_semantic_score(
    tmp_path, monkeypatch
):
    bound, _requests, plan = await experiment.prepare(
        experiment.DEFAULT_CONTROLS.read_bytes()
    )
    monkeypatch.setenv("DEEPSEEK_API_KEY", "fake-private")
    args = SimpleNamespace(run_dir=tmp_path, cache_only=False)
    live = await runtime.execute(
        args,
        bound,
        plan,
        profiles=experiment.PROFILES,
        provider_factory=factory,
        balance_reader=balance,
    )
    assert live["status"] == "complete"
    assert live["usage"]["ledger"]["attempts_reserved"] == 16
    assert all(
        r["analyzer_version"].startswith(r["profile"][1:] + ".") for r in live["rows"]
    )
    assert "rubric_pass" not in json.dumps(live)
    monkeypatch.delenv("DEEPSEEK_API_KEY")
    args.cache_only = True
    replay = await runtime.execute(
        args,
        bound,
        plan,
        profiles=experiment.PROFILES,
        provider_factory=factory,
        balance_reader=balance,
    )
    assert replay["rows"] == live["rows"]
    assert replay["usage"]["cache_hits_this_instance"] == 16
    assert replay["usage"]["cache_misses_this_instance"] == 0
    assert all(
        "fake-private" not in p.read_text(encoding="utf-8")
        for p in tmp_path.rglob("*.json")
    )


async def test_wrong_profile_refused_before_provider_or_ledger(tmp_path):
    bound, _requests, plan = await experiment.prepare(
        experiment.DEFAULT_CONTROLS.read_bytes()
    )
    with pytest.raises(ValueError, match="profiles mismatch"):
        await runtime.execute(
            SimpleNamespace(run_dir=tmp_path, cache_only=True), bound, plan
        )
    assert list(tmp_path.iterdir()) == []


async def test_contract_is_bound_and_preflight_is_deterministic():
    raw = experiment.DEFAULT_CONTROLS.read_bytes()
    _bound, requests, a = await experiment.prepare(raw)
    contract = experiment.CONTRACT
    _bound, more, b = await experiment.prepare(raw)
    assert a == b and requests == more
    assert (
        a["source_sha256"]["docs/memory-atomicity.md"]
        == hashlib.sha256(contract.read_bytes()).hexdigest()
    )


def test_old_frozen_fixture_unchanged_and_new_ids_disjoint():
    old = json.loads(runtime.DEFAULT_CONTROLS.read_bytes())
    new = json.loads(experiment.DEFAULT_CONTROLS.read_bytes())
    assert "one owner draft" in old["cases"][5]["rubric"]
    assert {c["id"] for c in old["cases"]}.isdisjoint(c["id"] for c in new["cases"])
    assert old["schema"] != new["schema"]
