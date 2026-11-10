"""Durable provider attempt accounting, without any external HTTP or API keys."""

import asyncio
import json

import httpx
import pytest

from doppel_memory import (
    OpenAICompatibleStructuredOutputConfig,
    StructuredGenerationRequest,
)
from doppel_memory.openai_compatible import StructuredOutputProviderError
from examples.workflow_analyzer import WorkflowAnalyzerSession

CONFIG = OpenAICompatibleStructuredOutputConfig(
    model="fixture",
    base_url="https://fixture.invalid/v1",
    schema_mode="json_object",
    max_completion_tokens=2048,
    max_tokens_parameter="max_tokens",
    thinking="disabled",
    temperature=0,
)
REQUEST = StructuredGenerationRequest(
    instructions="fixture", input={}, output_schema={"type": "object"}
)


def session(path, http, **kwargs):
    return WorkflowAnalyzerSession(
        path,
        binding="db-fixture",
        config=kwargs.pop("config", CONFIG),
        api_key="private-fixture-key",
        client=http,
        **kwargs,
    )


@pytest.mark.parametrize("failure", ["ok", "invalid_json", "http400", "timeout"])
async def test_reservations_survive_new_session_and_failures(tmp_path, failure):
    calls = []

    async def respond(request):
        calls.append(json.loads(request.content))
        if failure == "timeout":
            raise httpx.ReadTimeout("private-fixture-key", request=request)
        if failure == "http400":
            return httpx.Response(400, text="private-fixture-key")
        return httpx.Response(
            200,
            json={
                "choices": [
                    {"message": {"content": "{}" if failure == "ok" else "bad-json"}}
                ],
                "usage": {
                    "prompt_tokens": 10,
                    "completion_tokens": 2,
                    "total_tokens": 12,
                },
            },
        )

    path = tmp_path / "ledger.jsonl"
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http:
        for _ in range(2):
            async with session(path, http) as provider:
                if failure == "ok":
                    assert await provider.generate(REQUEST) == {}
                else:
                    with pytest.raises(StructuredOutputProviderError):
                        await provider.generate(REQUEST)
        async with session(path, http) as provider:
            with pytest.raises(RuntimeError, match="cap exhausted"):
                await provider.generate(REQUEST)
            usage = provider.report()
            assert usage["reserved_calls"] == 2 and usage["new_calls"] == 0
            assert usage["usage_missing_calls"] == (
                0 if failure in {"ok", "invalid_json"} else 2
            )
    assert len(calls) == 2
    assert all(
        item["max_tokens"] == 2048 and item["response_format"]["type"] == "json_object"
        for item in calls
    )
    assert "private-fixture-key" not in path.read_text()


async def test_concurrent_requests_allow_only_one_inflight_call(tmp_path):
    entered, release = asyncio.Event(), asyncio.Event()

    async def respond(request):
        entered.set()
        await release.wait()
        return httpx.Response(200, json={"choices": [{"message": {"content": "{}"}}]})

    async with (
        httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http,
        session(tmp_path / "ledger", http) as provider,
    ):
        running = asyncio.create_task(provider.generate(REQUEST))
        await entered.wait()
        try:
            with pytest.raises(RuntimeError, match="concurrent"):
                await provider.generate(REQUEST)
        finally:
            release.set()
            await running
        assert provider.report()["reserved_calls"] == 1


@pytest.mark.parametrize("change", ["model", "cap", "corrupt"])
async def test_identity_or_corrupt_ledger_is_not_reset(tmp_path, change):
    path = tmp_path / "ledger"
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: pytest.fail("unexpected network"))
    ) as http:
        async with session(path, http):
            pass
        if change == "corrupt":
            with path.open("a") as stream:
                stream.write("broken-tail")
        before = path.read_bytes()
        with pytest.raises(ValueError):
            session(
                path,
                http,
                config=CONFIG.model_copy(update={"model": "other"})
                if change == "model"
                else CONFIG,
                max_calls=3 if change == "cap" else 2,
            )
        assert path.read_bytes() == before


async def test_interrupted_reservation_still_consumes_cap(tmp_path):
    path = tmp_path / "ledger"
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: pytest.fail("unexpected network"))
    ) as http:
        async with session(path, http, max_calls=1) as provider:
            provider._append({"event": "reserved", "attempt": 1})
        async with session(path, http, max_calls=1) as provider:
            with pytest.raises(RuntimeError, match="cap exhausted"):
                await provider.generate(REQUEST)
            assert provider.report()["usage_missing_calls"] == 1
