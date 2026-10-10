from __future__ import annotations

import json
from copy import deepcopy
from types import SimpleNamespace

import httpx
import pytest

from benchmarks import aml_evidence_representation as experiment
from benchmarks.public_memory_reader_v2 import SCHEMA, build_request


def dataset():
    return json.loads(experiment.DEFAULT_CONTROLS.read_text(encoding="utf-8"))


@pytest.mark.parametrize("index", range(9))
async def test_representation_only_common_prompt_no_rubric_or_missing_roles(index):
    data = dataset()
    before = deepcopy(data)
    rows, requests = await experiment.prepare(data)
    row = rows[index]
    baseline, candidate = [requests[(row.case_id, arm)] for arm in experiment.ARMS]
    assert baseline.input == build_request(row).input
    assert baseline.instructions == candidate.instructions == experiment.INSTRUCTIONS
    assert baseline.output_schema == candidate.output_schema == SCHEMA
    assert candidate.input["question"] == baseline.input["question"]
    assert (
        candidate.input["question_reference_time"]
        == baseline.input["question_reference_time"]
    )
    for old, new in zip(
        baseline.input["context_items"], candidate.input["context_items"], strict=True
    ):
        body = json.loads(new["content"])
        source = body["source"]
        assert new["memory_id"] == old["memory_id"]
        assert source["text"] == old["text"]
        assert source["transport_role"] == old["role"]
        assert source["source_authority"] == old["authority"]
        assert source["observed_at"][:10] == old["observed_at"][:10]
        assert set(new) == {"memory_id", "content"}
    assert data == before
    assert data["cases"][index]["rubric"] not in candidate.model_dump_json()
    for domain in ("parcel", "pottery", "rowing", "music lesson", "notebook"):
        assert domain not in experiment.INSTRUCTIONS


async def test_plan_binds_sources_requests_config_and_fingerprints():
    data = experiment.DEFAULT_CONTROLS.read_bytes()
    rows, requests = await experiment.prepare(json.loads(data))
    plan = experiment.build_plan(data, rows, requests)
    assert plan["max_reader_calls"] == 18 and plan["max_judge_calls"] == 0
    assert len(plan["request_sha256"]) == 18
    assert not plan["baseline_role_authority_removed"]
    assert not plan["isolated_actor_label_effect"]
    assert plan["execution_order"][2][1] == experiment.ARMS[1]
    assert plan["reader_config"]["max_completion_tokens"] == 1024
    changed = dict(requests)
    row = rows[0]
    original = changed[(row.case_id, experiment.ARMS[0])]
    changed[(row.case_id, experiment.ARMS[0])] = original.model_copy(
        update={"instructions": "Changed"}
    )
    assert (
        experiment.build_plan(data, rows, changed)["plan_fingerprint"]
        != plan["plan_fingerprint"]
    )


def factory(cfg, key, observer):
    class Fake:
        name, version = "fake-evidence-representation", "1"

        async def generate(self, request):
            observer({"input_tokens": 10, "output_tokens": 2, "total_tokens": 12})
            return {
                "answer": "Synthetic answer; not evaluated.",
                "abstained": False,
                "cited_memory_ids": [request.input["context_items"][0]["memory_id"]],
            }

    return Fake()


async def unchanged(key):
    return 5.0


async def test_zero_key_replay_identical_and_no_provider_attempts(
    tmp_path, monkeypatch
):
    data = experiment.DEFAULT_CONTROLS.read_bytes()
    rows, requests = await experiment.prepare(json.loads(data))
    plan = experiment.build_plan(data, rows, requests)
    args = SimpleNamespace(run_dir=tmp_path, cache_only=False)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "fake-secret-never-persisted")
    live = await experiment.execute(
        args, rows, requests, plan, provider_factory=factory, balance_reader=unchanged
    )
    assert live["status"] == "complete" and live["semantic_scores"] is None
    assert live["usage"]["ledger"]["attempts_reserved"] == 18
    monkeypatch.delenv("DEEPSEEK_API_KEY")
    args.cache_only = True
    replay = await experiment.execute(
        args, rows, requests, plan, provider_factory=factory, balance_reader=unchanged
    )
    assert live["rows"] == replay["rows"]
    assert replay["usage"]["cache_hits_this_instance"] == 18
    assert replay["usage"]["cache_misses_this_instance"] == 0
    assert replay["usage"]["ledger"]["attempts_reserved"] == 18
    assert all(
        "fake-secret-never-persisted" not in p.read_text(encoding="utf-8")
        for p in tmp_path.rglob("*.json")
    )


async def test_failure_preserved_and_not_rebilled(tmp_path, monkeypatch):
    data = experiment.DEFAULT_CONTROLS.read_bytes()
    rows, requests = await experiment.prepare(json.loads(data))
    plan = experiment.build_plan(data, rows, requests)
    calls = []

    def broken_factory(cfg, key, observer):
        class Broken:
            name, version = "broken-evidence-model", "1"

            async def generate(self, request):
                calls.append(request)
                raise RuntimeError("PRIVATE_KEY_SOURCE")

        return Broken()

    args = SimpleNamespace(run_dir=tmp_path, cache_only=False)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "fake")
    first = await experiment.execute(
        args,
        rows,
        requests,
        plan,
        provider_factory=broken_factory,
        balance_reader=unchanged,
    )
    second = await experiment.execute(
        args,
        rows,
        requests,
        plan,
        provider_factory=broken_factory,
        balance_reader=unchanged,
    )
    assert first["status"] == second["status"] == "stopped"
    assert len(calls) == 1
    assert second["usage"]["ledger"]["attempts_reserved"] == 1
    assert "PRIVATE_KEY_SOURCE" not in json.dumps(second)


async def test_live_preflight_mismatch_rejected_before_provider(tmp_path):
    frozen = tmp_path / "wrong.json"
    frozen.write_text('{"plan":{}}', encoding="utf-8")
    args = SimpleNamespace(
        controls=experiment.DEFAULT_CONTROLS,
        live=True,
        frozen_preflight=frozen,
        run_dir=tmp_path / "run",
        cache_only=False,
    )
    with pytest.raises(ValueError, match="preflight"):
        await experiment.run(args)
    assert not args.run_dir.exists()


async def test_observed_provider_records_safe_model_metadata_no_headers(tmp_path):
    provider = experiment.ObservedProvider(
        experiment.config(1024), "fake-secret", lambda usage: None, tmp_path
    )
    await provider.client.aclose()

    old_hook = provider.client.event_hooks["response"][0]

    def transport(request):
        return httpx.Response(
            200,
            json={
                "model": "deepseek-flash",
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {
                            "content": '{"answer":"synthetic","abstained":false,"cited_memory_ids":[]}'
                        },
                    }
                ],
                "usage": {
                    "prompt_tokens": 1,
                    "completion_tokens": 1,
                    "total_tokens": 2,
                },
            },
        )

    provider.client = httpx.AsyncClient(
        transport=httpx.MockTransport(transport), event_hooks={"response": [old_hook]}
    )
    provider.model._client = provider.client
    rows, requests = await experiment.prepare(dataset())
    await provider.generate(requests[(rows[0].case_id, experiment.ARMS[0])])
    receipts = list(tmp_path.glob("*.json"))
    assert len(receipts) == 1
    assert json.loads(receipts[0].read_text()) == {
        "returned_model": "deepseek-flash",
        "finish_reason": "stop",
    }
    assert "fake-secret" not in receipts[0].read_text()
    await provider.aclose()


@pytest.mark.parametrize("fault", [None, "result", "quote", "missing", "dataset"])
async def test_review_binds_all_decisions_sources_and_exact_quotes(fault):
    data = dataset()
    rows, requests = await experiment.prepare(data)
    plan = experiment.build_plan(
        experiment.DEFAULT_CONTROLS.read_bytes(), rows, requests
    )
    report = {
        "runner": experiment.RUNNER,
        "status": "complete",
        "plan": plan,
        "rows": [
            {
                "case_id": r.case_id,
                "arm": arm,
                "reader": {"answer": "Synthetic answer."},
            }
            for r in rows
            for arm in experiment.ARMS
        ],
    }
    review = {
        "reviewer": "codex-manual",
        "independent_review": False,
        "result_sha256": experiment._hash(report),
        "decisions": [
            {
                "case_id": r.case_id,
                "arm": arm,
                "passes_rubric": True,
                "speaker_attribution": "not_applicable",
                "language_matches_question": True,
                "abstention_consistent": True,
                "plan_to_fact_error": False,
                "rationale": "Synthetic validation only, not semantic measurement.",
                "answer_quotes": ["Synthetic answer."],
                "source_quotes": [
                    {
                        "memory_id": r.context[0]["memory_id"],
                        "quote": r.context[0]["text"],
                    }
                ],
            }
            for r in rows
            for arm in experiment.ARMS
        ],
    }
    if fault == "result":
        review["result_sha256"] = "wrong"
    elif fault == "quote":
        review["decisions"][0]["answer_quotes"] = ["Not actually present"]
    elif fault == "missing":
        review["decisions"].pop()
    elif fault == "dataset":
        data["cases"][0]["items"][0]["text"] = "Altered source"
    if fault:
        with pytest.raises(ValueError):
            experiment.validate_review(report, data, review)
    else:
        result = experiment.validate_review(report, data, review)
        assert result["arms"][experiment.ARMS[0]]["reviewed"] == 9
        assert result["independent_review"] is False
