import json

import httpx
import pytest
from pydantic import BaseModel

pytest.importorskip("graphiti_core")

from graphiti_core.prompts.models import Message

from benchmarks.graphiti_runtime import (
    DurableGraphitiLLMClient,
    GraphitiChatTransport,
)
from benchmarks.public_memory_expansion import config
from benchmarks.public_memory_runtime import (
    DurableCallLedger,
    PilotRuntimeError,
    PilotStructuredModel,
)


class Output(BaseModel):
    value: str


def response():
    return httpx.Response(
        200,
        json={
            "choices": [
                {"finish_reason": "stop", "message": {"content": '{"value":"ok"}'}}
            ],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        },
    )


async def setup(tmp_path, handler, *, key="SYNTHETIC_PRIVATE_KEY", max_calls=2):
    ledger = DurableCallLedger(
        tmp_path / "budget.sqlite3", budget_id="synthetic", max_calls=max_calls
    )
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    transport = GraphitiChatTransport(
        config(8192), api_key=key, client=client, usage_observer=ledger.observe_usage
    )
    model = PilotStructuredModel(transport, ledger=ledger, cache_dir=tmp_path / "cache")
    return DurableGraphitiLLMClient(model, output_cap=8192), ledger, client, model


@pytest.mark.asyncio
async def test_chat_protocol_schema_cap_accounting_and_cache_without_key(tmp_path):
    requests = []

    def handler(request):
        requests.append(json.loads(request.content))
        assert request.url.path == "/chat/completions"
        return response()

    bridge, ledger, client, model = await setup(tmp_path, handler)
    messages = [
        Message(role="system", content="extract"),
        Message(role="user", content="memory"),
    ]
    before = [m.model_dump() for m in messages]
    assert await bridge.generate_response(
        messages, Output, 16384, group_id="scope"
    ) == {"value": "ok"}
    assert await bridge.generate_response(
        messages, Output, 16384, group_id="scope"
    ) == {"value": "ok"}
    assert [m.model_dump() for m in messages] == before
    assert len(requests) == 1
    request = requests[0]
    assert request["max_tokens"] == 8192
    assert request["response_format"] == {"type": "json_object"}
    assert request["thinking"] == {"type": "disabled"}
    assert request["temperature"] == 0
    assert '"value"' in request["messages"][0]["content"]
    assert model.report()["ledger"]["reported_tokens"]["total_tokens"] == 15
    await client.aclose()
    ledger.close()
    bridge, ledger, client, model = await setup(tmp_path, handler, key="")
    assert await bridge.generate_response(
        messages, Output, 16384, group_id="scope"
    ) == {"value": "ok"}
    assert len(requests) == 1
    assert model.report()["cache_hits_this_instance"] == 1
    for path in tmp_path.rglob("*"):
        if path.is_file():
            assert b"SYNTHETIC_PRIVATE_KEY" not in path.read_bytes()
    await client.aclose()
    ledger.close()


@pytest.mark.asyncio
async def test_smaller_requested_limit_is_honored(tmp_path):
    requests = []
    bridge, ledger, client, _ = await setup(
        tmp_path, lambda r: (requests.append(json.loads(r.content)), response())[1]
    )
    await bridge.generate_response(
        [Message(role="user", content="memory")], Output, 1024
    )
    assert requests[0]["max_tokens"] == 1024
    await client.aclose()
    ledger.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["group", "schema", "cap", "attribute"])
async def test_every_extraction_setting_binds_cache(tmp_path, change):
    count = []
    bridge, ledger, client, _ = await setup(
        tmp_path, lambda r: (count.append(r), response())[1]
    )
    messages = [
        Message(role="system", content="extract"),
        Message(role="user", content="memory"),
    ]
    await bridge.generate_response(messages, Output, 1024, group_id="a")
    options = {"group_id": "a", "max_tokens": 1024, "response_model": Output}
    if change == "group":
        options["group_id"] = "b"
    elif change == "schema":
        options["response_model"] = None
    elif change == "cap":
        options["max_tokens"] = 2048
    else:
        options["attribute_extraction"] = True
    await bridge.generate_response(messages, **options)
    assert len(count) == 2
    await client.aclose()
    ledger.close()


@pytest.mark.asyncio
async def test_http_failure_never_retries_and_records_attempt(tmp_path):
    count = []
    bridge, ledger, client, _ = await setup(
        tmp_path, lambda r: (count.append(r), httpx.Response(500, text="PRIVATE"))[1]
    )
    with pytest.raises(PilotRuntimeError) as raised:
        await bridge.generate_response([Message(role="user", content="memory")], Output)
    assert len(count) == 1
    assert "PRIVATE" not in str(raised.value)
    assert ledger.report()["attempt_status_counts"]["failed"] == 1
    await client.aclose()
    ledger.close()


@pytest.mark.asyncio
async def test_attempt_cap_blocks_network_before_next_miss(tmp_path):
    count = []
    bridge, ledger, client, _ = await setup(
        tmp_path, lambda r: (count.append(r), response())[1], max_calls=1
    )
    await bridge.generate_response([Message(role="user", content="one")], Output)
    with pytest.raises(PilotRuntimeError):
        await bridge.generate_response([Message(role="user", content="two")], Output)
    assert len(count) == 1
    await client.aclose()
    ledger.close()
