from __future__ import annotations

import json
from types import SimpleNamespace

import httpx
import pytest

from benchmarks import public_memory_official_scoring as pinned
from benchmarks import public_memory_prompt_regrade as diagnostic
from benchmarks.public_memory_runtime import DurableCallLedger, PilotStructuredModel


def rows():
    return [
        {
            "identity": [c, p, s],
            "prompt": f"question/gold/answer {c}/{p}/{s}",
            "hypothesis": "unchanged answer",
            "category": "single-session-user",
            "abstention_case": "_abs" in c,
            "old_diagnostic_label": True,
        }
        for c in pinned.COHORT
        for p in pinned.PROFILES
        for s in pinned.POLICIES
    ]


def response(content="yes", model="deepseek-flash", finish="stop"):
    return {
        "model": model,
        "choices": [{"message": {"content": content}, "finish_reason": finish}],
        "usage": {
            "prompt_tokens": 100,
            "completion_tokens": 1,
            "total_tokens": 101,
            "prompt_cache_hit_tokens": 20,
            "prompt_cache_miss_tokens": 80,
            "completion_tokens_details": {"reasoning_tokens": 0},
        },
    }


async def fake_balance(key):
    assert key == "fake-deepseek-secret"
    return 5.0


def test_wire_and_plan_diagnostic_not_official(tmp_path):
    prepared = rows()
    request = pinned.request_for(prepared[0])
    wire = diagnostic.wire_request(request)
    assert wire["model"] == "deepseek-v4-flash"
    assert wire["thinking"] == {"type": "disabled"}
    assert wire["temperature"] == 0 and wire["max_tokens"] == 10
    assert wire["messages"] == pinned.wire_request(request)["messages"]
    assert "response_format" not in wire and "n" not in wire
    plan = diagnostic.build_plan(prepared, {}, {})
    assert plan["runner"] == diagnostic.RUNNER and plan["max_new_calls"] == 28
    assert not plan["official_scoring_protocol"] and plan["official_prompt_reused"]
    assert not plan["model_snapshot_pinned"] and not plan["aml_result"]
    assert pinned.MODEL == "gpt-4o-2024-08-06"
    assert pinned.wire_request(request)["model"] == pinned.MODEL


@pytest.mark.asyncio
async def test_complete_live_fake_and_no_key_replay(tmp_path, monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "fake-deepseek-secret")
    args = SimpleNamespace(run_dir=tmp_path, cache_only=False)
    calls = []

    def handler(request):
        calls.append(json.loads(request.content))
        return httpx.Response(200, json=response())

    prepared = rows()
    plan = diagnostic.build_plan(prepared, {}, {})
    live = await diagnostic.execute(
        args,
        prepared,
        plan,
        transport=httpx.MockTransport(handler),
        balance_reader=fake_balance,
    )
    assert live["status"] == "complete" and len(calls) == 28
    assert all(a["all"]["prompt_correct"] == 7 for a in live["summary"].values())
    assert all("official_label" not in r["grade"] for r in live["rows"])
    assert live["usage"]["ledger"]["reported_tokens"] == {
        "input_tokens": 2800,
        "output_tokens": 28,
        "total_tokens": 2828,
        "cached_input_tokens": 560,
        "cache_miss_input_tokens": 2240,
        "reasoning_tokens": 0,
    }
    monkeypatch.delenv("DEEPSEEK_API_KEY")
    args.cache_only = True
    replay = await diagnostic.execute(
        args,
        prepared,
        plan,
        transport=httpx.MockTransport(handler),
        balance_reader=fake_balance,
    )
    assert replay["status"] == "complete" and len(calls) == 28
    assert replay["rows"] == live["rows"] and replay["summary"] == live["summary"]
    assert replay["usage"]["cache_hits_this_instance"] == 28
    for path in tmp_path.rglob("*"):
        if path.is_file():
            assert b"fake-deepseek-secret" not in path.read_bytes()


@pytest.mark.parametrize(
    "fault",
    [
        "model",
        "http401",
        "empty",
        "invalid_json",
        "escaped_key",
        "timeout",
        "too_large",
    ],
)
@pytest.mark.asyncio
async def test_failures_redacted_accounted_no_retry(tmp_path, fault):
    calls = []

    def handler(request):
        calls.append(request)
        if fault == "http401":
            return httpx.Response(401, text="fake-deepseek-secret")
        if fault == "timeout":
            raise httpx.ReadTimeout("fake-deepseek-secret", request=request)
        if fault == "invalid_json":
            return httpx.Response(200, text="bad")
        if fault == "escaped_key":
            return httpx.Response(
                200,
                text=json.dumps(response("fake-deepseek-secret")).replace(
                    "secret", "\\u0073ecret"
                ),
            )
        if fault == "too_large":
            return httpx.Response(200, text="x" * 100_001)
        return httpx.Response(
            200,
            json=response(
                " " if fault == "empty" else "yes",
                model="gpt-4o" if fault == "model" else "deepseek-flash",
            ),
        )

    ledger = DurableCallLedger(
        tmp_path / "ledger.sqlite", budget_id="test", max_calls=1
    )
    model = PilotStructuredModel(
        diagnostic.DeepSeekPromptJudge(
            "fake-deepseek-secret", ledger, transport=httpx.MockTransport(handler)
        ),
        ledger=ledger,
        cache_dir=tmp_path / "cache",
    )
    try:
        with pytest.raises(RuntimeError) as error:
            await model.generate(pinned.request_for(rows()[0]))
        assert "fake-deepseek-secret" not in str(error.value)
        assert (
            len(calls) == 1 and ledger.report()["attempt_status_counts"]["failed"] == 1
        )
        with pytest.raises(RuntimeError):
            await model.generate(pinned.request_for(rows()[1]))
        assert len(calls) == 1
    finally:
        ledger.close()


@pytest.mark.parametrize(
    "content,finish",
    [("yes, because", "stop"), ("yes", "length"), ("no", "content_filter")],
)
@pytest.mark.asyncio
async def test_ambiguous_verdict_stop_preserve_no_retry(
    tmp_path, monkeypatch, content, finish
):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "fake-deepseek-secret")
    args = SimpleNamespace(run_dir=tmp_path, cache_only=False)
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(200, json=response(content, finish=finish))

    plan = diagnostic.build_plan(rows(), {}, {})
    live = await diagnostic.execute(
        args,
        rows(),
        plan,
        transport=httpx.MockTransport(handler),
        balance_reader=fake_balance,
    )
    repeat = await diagnostic.execute(
        args,
        rows(),
        plan,
        transport=httpx.MockTransport(handler),
        balance_reader=fake_balance,
    )
    assert live["status"] == "stopped" and len(calls) == 1
    assert repeat["rows"] == live["rows"]


@pytest.mark.asyncio
async def test_missing_key_never_uses_openai(tmp_path, monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "other-key")
    with pytest.raises(ValueError, match="missing"):
        await diagnostic.execute(
            SimpleNamespace(run_dir=tmp_path, cache_only=False), rows(), {}
        )
    assert not list(tmp_path.iterdir())


@pytest.mark.asyncio
async def test_observed_balance_stop_prevents_paid_call(tmp_path, monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "fake-deepseek-secret")
    values = iter([5.0, 3.9, 3.9])

    async def observed(key):
        return next(values)

    def handler(request):
        pytest.fail("must stop before generation HTTP")

    plan = diagnostic.build_plan(rows(), {}, {})
    result = await diagnostic.execute(
        SimpleNamespace(run_dir=tmp_path, cache_only=False),
        rows(),
        plan,
        transport=httpx.MockTransport(handler),
        balance_reader=observed,
    )
    assert (
        result["status"] == "stopped"
        and result["stopped_reason"] == "observed_balance_stop"
    )
    assert result["usage"]["ledger"]["attempts_reserved"] == 0
