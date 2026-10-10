from __future__ import annotations

import json
from copy import deepcopy
from types import SimpleNamespace

import httpx
import pytest

from benchmarks import public_memory_grounded_reader as grounded
from benchmarks.public_memory_pilot import _hash
from benchmarks.public_memory_reader_v2 import SCHEMA
from benchmarks.public_memory_response_policy import ADVICE_INSTRUCTIONS


def dataset():
    return json.loads(grounded.DEFAULT_CONTROLS.read_text(encoding="utf-8"))


@pytest.mark.parametrize("index", range(9))
def test_policy_changes_only_instructions_no_gold_rubric_or_domain_rules(index):
    data = dataset()
    row = grounded.control_rows(data)[index]
    before = deepcopy(row)
    baseline, candidate = [grounded.reader_request(row, p) for p in grounded.POLICIES]
    assert baseline.instructions == ADVICE_INSTRUCTIONS
    assert candidate.instructions == grounded.INSTRUCTIONS
    assert (
        baseline.input == candidate.input
        and baseline.output_schema == candidate.output_schema == SCHEMA
    )
    assert row == before
    assert set(candidate.input) == {
        "question",
        "question_reference_time",
        "context_items",
    }
    assert data["cases"][index]["rubric"] not in candidate.model_dump_json()
    assert "unused-scoring-only" not in candidate.model_dump_json()
    for text in (
        "parcel",
        "workshop",
        "outage",
        "pottery",
        "turbinado",
        "fun run",
        "21d02d0d",
        "38146c39",
    ):
        assert text not in candidate.instructions


def test_control_completion_timestamp_and_authority_are_preserved():
    rows = grounded.control_rows(dataset())
    assert rows[2].context[1]["observed_at"] == "2026-08-18T00:00:00Z"
    assert rows[6].context[0]["authority"] == "human_self"
    assert rows[6].context[1]["authority"] == "agent_output"
    assert rows[7].context[0]["role"] == "assistant"
    assert len({r.case_id for r in rows}) == 9


@pytest.mark.parametrize("fault", ["duplicate", "empty", "role"])
def test_bad_controls_rejected(fault):
    data = dataset()
    if fault == "duplicate":
        data["cases"][1]["id"] = data["cases"][0]["id"]
    elif fault == "empty":
        data["cases"][0]["items"] = []
    else:
        data["cases"][0]["items"][0]["role"] = "system"
    with pytest.raises(ValueError):
        grounded.control_rows(data)


def factory(config, key, observer):
    class Fake:
        name, version = "fake-grounded-controls", "1"

        async def generate(self, request):
            observer({"input_tokens": 10, "output_tokens": 5, "total_tokens": 15})
            return {
                "answer": "Synthetic answer; semantics not measured.",
                "abstained": False,
                "cited_memory_ids": [request.input["context_items"][0]["memory_id"]],
            }

    return Fake()


async def unchanged(key):
    return 5.0


@pytest.mark.asyncio
async def test_control_run_no_judge_replay_and_manual_gate(tmp_path, monkeypatch):
    data, key = dataset(), "fake-control-key-not-persisted"
    rows = grounded.control_rows(data)
    plan = grounded.build_plan(rows, {}, "controls")
    assert plan["max_reader_calls"] == 18 and plan["max_judge_calls"] == 0
    monkeypatch.setenv("DEEPSEEK_API_KEY", key)
    args = SimpleNamespace(run_dir=tmp_path, cache_only=False)
    live = await grounded.execute(
        args, rows, plan, provider_factory=factory, balance_reader=unchanged
    )
    assert live["status"] == "complete" and set(live["usage"]) == {"reader"}
    assert live["semantic_control_review"] == "not_automatically_measured"
    assert live["usage"]["reader"]["ledger"]["attempts_reserved"] == 18
    monkeypatch.delenv("DEEPSEEK_API_KEY")
    args.cache_only = True
    replay = await grounded.execute(
        args, rows, plan, provider_factory=factory, balance_reader=unchanged
    )
    assert (
        replay["rows"] == live["rows"]
        and replay["usage"]["reader"]["cache_hits_this_instance"] == 18
    )
    report = {**live, "runner": grounded.RUNNER, "plan": plan}
    review = {
        "reviewer": "codex-manual",
        "independent_review": False,
        "result_sha256": _hash(report),
        "decisions": [
            {
                "case_id": row.case_id,
                "policy": p,
                "passes_rubric": p == grounded.POLICIES[1],
                "rationale": "Fake protocol decision, not a semantic finding.",
                "answer_quotes": ["Synthetic answer"],
                "source_quotes": [
                    {
                        "memory_id": row.context[0]["memory_id"],
                        "quote": row.context[0]["text"],
                    }
                ],
            }
            for row in rows
            for p in grounded.POLICIES
        ],
    }
    assert grounded.review_controls(report, data, review)["ok"]
    bad = deepcopy(review)
    bad["decisions"][1]["passes_rubric"] = False
    assert not grounded.review_controls(report, data, bad)["ok"]
    bad["decisions"][1]["answer_quotes"] = ["not in the answer"]
    with pytest.raises(ValueError, match="quote"):
        grounded.review_controls(report, data, bad)
    bad = deepcopy(review)
    bad["decisions"].pop()
    with pytest.raises(ValueError, match="all controls"):
        grounded.review_controls(report, data, bad)
    bad = deepcopy(review)
    bad["independent_review"] = True
    with pytest.raises(ValueError):
        grounded.review_controls(report, data, bad)
    for path in tmp_path.rglob("*"):
        if path.is_file():
            assert key.encode() not in path.read_bytes()


@pytest.mark.asyncio
async def test_failed_stage_preserved_not_retried(tmp_path, monkeypatch):
    calls = []

    def failing(config, key, observer):
        class Fake:
            name, version = "fake-failing-controls", "1"

            async def generate(self, request):
                calls.append(request)
                raise RuntimeError("sensitive provider error")

        return Fake()

    monkeypatch.setenv("DEEPSEEK_API_KEY", "fake-key")
    args = SimpleNamespace(run_dir=tmp_path, cache_only=False)
    rows = grounded.control_rows(dataset())
    plan = grounded.build_plan(rows, {}, "controls")
    one = await grounded.execute(
        args, rows, plan, provider_factory=failing, balance_reader=unchanged
    )
    two = await grounded.execute(
        args, rows, plan, provider_factory=failing, balance_reader=unchanged
    )
    assert one["status"] == two["status"] == "stopped" and len(calls) == 1
    assert "sensitive provider error" not in json.dumps(one)


@pytest.mark.asyncio
async def test_paired_fake_judge_is_reference_only_and_diagnostic(
    tmp_path, monkeypatch
):
    calls = []

    def handler(request):
        wire = json.loads(request.content)
        calls.append(wire)
        assert "context_items" not in wire["messages"][0]["content"]
        assert "grounded_advice_v2" not in wire["messages"][0]["content"]
        return httpx.Response(
            200,
            json={
                "model": "deepseek-flash",
                "choices": [{"message": {"content": "yes"}, "finish_reason": "stop"}],
            },
        )

    monkeypatch.setenv("DEEPSEEK_API_KEY", "fake-key")
    rows = grounded.control_rows(dataset())[:1]
    plan = grounded.build_plan(rows, {}, "paired")
    result = await grounded.execute(
        SimpleNamespace(run_dir=tmp_path, cache_only=False),
        rows,
        plan,
        provider_factory=factory,
        balance_reader=unchanged,
        judge_transport=httpx.MockTransport(handler),
    )
    assert result["status"] == "complete"
    assert len(calls) == 1  # identical fake answers share the judge cache
    assert result["rows"][0]["grade"]["upstream_parser_label"]
    assert not plan["official_longmemeval_metric"] and not plan["core_default_changed"]


def test_oversize_and_unknown_policy_fail_closed():
    row = grounded.control_rows(dataset())[0]
    with pytest.raises(ValueError, match="unknown"):
        grounded.reader_request(row, "unfrozen")
    context = ({**row.context[0], "text": "x" * 120_000},)
    from dataclasses import replace

    with pytest.raises(ValueError, match="oversize"):
        grounded.build_plan([replace(row, context=context)], {}, "controls")
