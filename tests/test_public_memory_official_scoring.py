from __future__ import annotations

import copy
import hashlib
import json
from types import SimpleNamespace

import httpx
import pytest

from benchmarks import public_memory_official_scoring as scoring
from benchmarks.public_memory_pilot import _hash
from benchmarks.public_memory_runtime import DurableCallLedger, PilotStructuredModel


def fixtures():
    bindings = {"source": "source-hash", "manifest": "manifest-hash"}
    source = [
        {
            "question_id": c,
            "question_type": "single-session-user",
            "question": "Q?",
            "answer": "A",
        }
        for c in scoring.COHORT
    ]
    manifest = {
        "source_sha256": bindings["source"],
        "cases": [{"case_id": c, "partition": "diagnostic"} for c in scoring.COHORT],
    }
    plan = {
        "input_sha256": bindings,
        "contexts": [[c, p] for c in scoring.COHORT for p in scoring.PROFILES],
        "policies": list(scoring.POLICIES),
    }
    plan["plan_fingerprint"] = _hash(plan)
    parent = {
        "runner": "doppel.public-memory-response-policy-paired.v1",
        "status": "complete",
        "plan": plan,
        "rows": [
            {
                "case_id": c,
                "context_profile": p,
                "policy": s,
                "category": "single-session-user",
                "abstention_case": "_abs" in c,
                "status": "complete",
                "reader": {"answer": f"answer for {c}/{p}/{s}"},
                "grade": {"answer_correct": True},
            }
            for c in scoring.COHORT
            for p in scoring.PROFILES
            for s in scoring.POLICIES
        ],
    }
    return parent, source, manifest, bindings


def rows():
    return scoring.prepare_rows(*fixtures())[0]


def response(content="yes", *, model=scoring.MODEL, finish="stop", usage=True):
    result = {
        "model": model,
        "choices": [{"message": {"content": content}, "finish_reason": finish}],
    }
    if usage:
        result["usage"] = {
            "prompt_tokens": 100,
            "completion_tokens": 1,
            "total_tokens": 101,
            "prompt_tokens_details": {"cached_tokens": 20},
        }
    return result


def model_at(
    tmp_path, handler, *, max_calls=28, cache_only=False, key="fake-test-secret"
):
    ledger = DurableCallLedger(
        tmp_path / "ledger.sqlite", budget_id="test", max_calls=max_calls
    )
    provider = scoring.OfficialChatModel(
        key, scoring.BASE_URL, ledger, transport=httpx.MockTransport(handler)
    )
    model = PilotStructuredModel(
        provider, ledger=ledger, cache_dir=tmp_path / "cache", cache_only=cache_only
    )
    return model, ledger


def test_snapshot_pinned_and_function_only():
    assert (
        hashlib.sha256(
            scoring.UPSTREAM.read_text(encoding="utf-8").encode()
        ).hexdigest()
        == scoring.UPSTREAM_SHA256
    )
    prompt = scoring.official_prompt("temporal-reasoning", "Question", "Gold", "Hyp")
    assert "off-by-one" in prompt and "Question: Question" in prompt
    assert "Model Response: Hyp" in prompt


@pytest.mark.parametrize(
    "task",
    [
        "single-session-user",
        "single-session-assistant",
        "multi-session",
        "knowledge-update",
        "single-session-preference",
        "temporal-reasoning",
    ],
)
def test_official_categories(task):
    assert scoring.official_prompt(task, "q", "a", "h").endswith(
        "Answer yes or no only."
    )
    assert "unanswerable" in scoring.official_prompt(
        task, "q", "a", "h", abstention=True
    )


def test_changed_upstream_rejected(tmp_path, monkeypatch):
    modified = tmp_path / "changed.txt"
    modified.write_text("def get_anscheck_prompt(): return 'yes'", encoding="utf-8")
    monkeypatch.setattr(scoring, "UPSTREAM", modified)
    with pytest.raises(ValueError, match="snapshot"):
        scoring.official_prompt("single-session-user", "q", "a", "h")


@pytest.mark.parametrize(
    "url",
    [
        "http://example.com/v1",
        "https://key@example.com/v1",
        "https://example.com/v1?key=secret",
        "https://example.com/v1#secret",
        "https://",
        "https://example.com/ v1",
        "https://example.com/v1/chat/completions",
    ],
)
def test_secret_or_insecure_base_rejected(url):
    with pytest.raises(ValueError):
        scoring.validate_base_url(url)


def test_parent_selection_exports_and_requests(tmp_path):
    parent, source, manifest, binding = fixtures()
    prepared, refs = scoring.prepare_rows(parent, source, manifest, binding)
    assert len(prepared) == 28 and len(refs) == 7
    hashes = scoring.export_inputs(tmp_path, prepared, refs)
    assert hashes == scoring.export_inputs(tmp_path, prepared, refs)
    for path in (tmp_path / "exports").glob("*.jsonl"):
        exported = [
            json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
        ]
        assert len(exported) == 7
        assert [r["question_id"] for r in exported] == list(scoring.COHORT)
        assert all(set(r) == {"question_id", "hypothesis"} for r in exported)
    wire = scoring.wire_request(scoring.request_for(prepared[0]))
    assert set(wire) == {"model", "messages", "n", "temperature", "max_tokens"}
    assert len(wire["messages"]) == 1 and wire["messages"][0]["role"] == "user"
    assert wire["messages"][0]["content"] == prepared[0]["prompt"]
    assert "old_diagnostic_label" not in wire["messages"][0]["content"]


@pytest.mark.parametrize(
    "mutation", ["missing", "duplicate", "reserved", "category", "incomplete", "parent"]
)
def test_parent_tamper_rejected(mutation):
    parent, source, manifest, binding = fixtures()
    if mutation == "missing":
        parent["rows"].pop()
    elif mutation == "duplicate":
        parent["rows"][-1] = copy.deepcopy(parent["rows"][0])
    elif mutation == "reserved":
        manifest["cases"][0]["partition"] = "reserved"
    elif mutation == "category":
        parent["rows"][0]["category"] = "knowledge-update"
    elif mutation == "incomplete":
        parent["rows"][0]["status"] = "failed"
    else:
        parent["plan"]["policies"].reverse()
    with pytest.raises(ValueError):
        scoring.prepare_rows(parent, source, manifest, binding)


@pytest.mark.parametrize(
    "text,label,valid",
    [
        (" YES \n", True, True),
        ("no", False, True),
        ("Yes, but", True, False),
        ("not yes", True, False),
        ("yesterday", True, False),
    ],
)
def test_upstream_label_not_silently_rewritten(text, label, valid):
    output = scoring.OfficialOutput(
        raw_response=text, returned_model=scoring.MODEL, finish_reason="stop"
    )
    result = scoring.verdict(output)
    assert result["official_label"] is label
    assert result["strict_yes_no_valid"] is valid


@pytest.mark.asyncio
async def test_http_usage_cache_replay_and_no_secrets(tmp_path):
    calls = []

    def handler(request):
        calls.append(json.loads(request.content))
        assert request.headers["authorization"] == "Bearer fake-test-secret"
        return httpx.Response(200, json=response())

    model, ledger = model_at(tmp_path, handler)
    request = scoring.request_for(rows()[0])
    first = await model.generate(request)
    assert await model.generate(request) == first
    assert calls == [scoring.wire_request(request)]
    assert ledger.report()["reported_tokens"]["total_tokens"] == 101
    ledger.close()
    model, ledger = model_at(tmp_path, handler, cache_only=True, key="")
    assert await model.generate(request) == first
    assert len(calls) == 1
    assert model.report()["cache_hits_this_instance"] == 1
    ledger.close()
    for path in tmp_path.rglob("*"):
        if path.is_file():
            assert b"fake-test-secret" not in path.read_bytes()


@pytest.mark.parametrize(
    "fault",
    [
        "http400",
        "http401",
        "http429",
        "redirect",
        "timeout",
        "invalid_json",
        "empty",
        "model",
        "echo_key",
        "escaped_key",
        "too_large",
        "choices",
    ],
)
@pytest.mark.asyncio
async def test_failed_attempt_no_retry_or_leaked_details(tmp_path, fault):
    calls = []

    def handler(request):
        calls.append(request)
        if fault.startswith("http"):
            return httpx.Response(int(fault[4:]), text="fake-test-secret")
        if fault == "redirect":
            return httpx.Response(
                307, headers={"Location": "https://elsewhere.example"}
            )
        if fault == "timeout":
            raise httpx.ReadTimeout("fake-test-secret", request=request)
        if fault == "invalid_json":
            return httpx.Response(200, text="invalid")
        if fault == "too_large":
            return httpx.Response(200, text="x" * 100_001)
        if fault == "escaped_key":
            text = json.dumps(response("fake-test-secret"))
            return httpx.Response(
                200, text=text.replace("fake-test-secret", "fake-test-\\u0073ecret")
            )
        data = response()
        if fault == "empty":
            data["choices"][0]["message"]["content"] = " "
        elif fault == "model":
            data["model"] = "deepseek-v4-flash"
        elif fault == "echo_key":
            data["choices"][0]["message"]["content"] = "fake-test-secret"
        elif fault == "choices":
            data["choices"] = []
        return httpx.Response(200, json=data)

    model, ledger = model_at(tmp_path, handler)
    with pytest.raises(RuntimeError) as error:
        await model.generate(scoring.request_for(rows()[0]))
    assert "fake-test-secret" not in str(error.value)
    assert len(calls) == 1
    assert ledger.report()["attempt_status_counts"]["failed"] == 1
    assert not list((tmp_path / "cache").rglob("*.json"))
    ledger.close()


@pytest.mark.asyncio
async def test_missing_usage_unknown_and_budget_before_network(tmp_path):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(200, json=response(usage=False))

    model, ledger = model_at(tmp_path, handler, max_calls=1)
    prepared = rows()
    await model.generate(scoring.request_for(prepared[0]))
    assert ledger.report()["reported_tokens"] is None
    assert ledger.report()["calls_without_usage"] == 1
    assert not ledger.report()["token_accounting_complete"]
    with pytest.raises(RuntimeError):
        await model.generate(scoring.request_for(prepared[1]))
    assert len(calls) == 1
    ledger.close()


@pytest.mark.asyncio
async def test_complete_execution_and_keyless_replay(tmp_path, monkeypatch):
    prepared = rows()
    args = SimpleNamespace(
        cache_only=False, run_dir=tmp_path, base_url=scoring.BASE_URL
    )
    monkeypatch.setenv("OPENAI_API_KEY", "fake-test-secret")
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(200, json=response())

    plan = {"plan_fingerprint": "execution-test"}
    live = await scoring.execute(
        args, prepared, plan, transport=httpx.MockTransport(handler)
    )
    assert live["status"] == "complete" and len(calls) == 28
    assert all(a["all"]["graded"] == 7 for a in live["summary"].values())
    monkeypatch.delenv("OPENAI_API_KEY")
    args.cache_only = True
    replay = await scoring.execute(
        args, prepared, plan, transport=httpx.MockTransport(handler)
    )
    assert len(calls) == 28 and replay["rows"] == live["rows"]
    assert replay["summary"] == live["summary"]
    assert replay["usage"]["cache_hits_this_instance"] == 28


@pytest.mark.asyncio
async def test_missing_key_stops_before_writes(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    args = SimpleNamespace(
        cache_only=False, run_dir=tmp_path, base_url=scoring.BASE_URL
    )
    with pytest.raises(ValueError, match="missing"):
        await scoring.execute(args, rows(), {"plan_fingerprint": "test"})
    assert not list(tmp_path.iterdir())


@pytest.mark.asyncio
async def test_failed_receipt_cannot_silently_rebill(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "fake-test-secret")
    args = SimpleNamespace(
        cache_only=False, run_dir=tmp_path, base_url=scoring.BASE_URL
    )
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(401, text="fake-test-secret")

    plan = {"plan_fingerprint": "execution-test"}
    live = await scoring.execute(
        args, rows(), plan, transport=httpx.MockTransport(handler)
    )
    assert live["status"] == "stopped" and len(calls) == 1
    assert live["usage"]["ledger"]["failure_diagnostics"][0]["http_status"] == 401
    await scoring.execute(args, rows(), plan, transport=httpx.MockTransport(handler))
    assert len(calls) == 1


def test_plan_binds_endpoint_exports_requests_and_code(tmp_path):
    prepared, refs = scoring.prepare_rows(*fixtures())
    exports = scoring.export_inputs(tmp_path, prepared, refs)
    plan = scoring.build_plan(prepared, fixtures()[3], exports, scoring.BASE_URL)
    assert len(plan["wire_sha256"]) == 28 and plan["max_new_calls"] == 28
    assert plan["opened_cases"] == 7 and not plan["formal_longmemeval_result"]
    changed = scoring.build_plan(
        prepared, fixtures()[3], exports, "https://compatible.example/v1"
    )
    assert plan["plan_fingerprint"] != changed["plan_fingerprint"]
    payload = dict(plan)
    fingerprint = payload.pop("plan_fingerprint")
    assert fingerprint == _hash(payload)


def test_export_tampering_preserved_and_rejected(tmp_path):
    prepared, refs = scoring.prepare_rows(*fixtures())
    scoring.export_inputs(tmp_path, prepared, refs)
    path = tmp_path / "exports" / "references.json"
    path.write_text("corrupt", encoding="utf-8")
    with pytest.raises(ValueError, match="immutable"):
        scoring.export_inputs(tmp_path, prepared, refs)
    assert path.read_text(encoding="utf-8") == "corrupt"


@pytest.mark.parametrize(
    "content,finish",
    [("yes, but", "stop"), ("yes", "length"), ("no", "content_filter")],
)
@pytest.mark.asyncio
async def test_invalid_verdict_stops_and_preserves_not_rebilled(
    tmp_path, monkeypatch, content, finish
):
    monkeypatch.setenv("OPENAI_API_KEY", "fake-test-secret")
    args = SimpleNamespace(
        cache_only=False, run_dir=tmp_path, base_url=scoring.BASE_URL
    )
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(200, json=response(content, finish=finish))

    plan = {"plan_fingerprint": "execution-test"}
    result = await scoring.execute(
        args, rows(), plan, transport=httpx.MockTransport(handler)
    )
    assert result["status"] == "stopped" and len(calls) == 1
    assert result["rows"][0]["grade"]["official_label"] == ("yes" in content)
    repeat = await scoring.execute(
        args, rows(), plan, transport=httpx.MockTransport(handler)
    )
    assert repeat["rows"] == result["rows"] and len(calls) == 1
