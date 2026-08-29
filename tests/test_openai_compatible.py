"""OpenAI-compatible structured-output transport and failure boundaries."""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

import httpx
import pytest

from doppel_memory.consolidation import ReferenceMemoryConsolidator
from doppel_memory.intelligence import (
    PersonalMemoryAnalysisRequest,
    ReferencePersonalMemoryAnalyzer,
    StructuredGenerationRequest,
)
from doppel_memory.models import Actor, ChatMessage, MemoryScope
from doppel_memory.openai_compatible import (
    OpenAICompatibleStructuredOutputConfig,
    OpenAICompatibleStructuredOutputModel,
    StructuredOutputProviderError,
)
from doppel_memory.query import ReferencePersonalMemoryQueryPlanner


def _request() -> StructuredGenerationRequest:
    return StructuredGenerationRequest(
        instructions="Extract one object.",
        input={"消息": "我住在上海"},
        output_schema={
            "title": "Memory Result",
            "type": "object",
            "properties": {"city": {"type": "string"}},
            "required": ["city"],
            "additionalProperties": False,
        },
    )


async def test_json_schema_request_is_bounded_authenticated_and_parsed() -> None:
    observed: dict[str, Any] = {}
    observed_usage: list[Mapping[str, int]] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        observed["url"] = str(request.url)
        observed["authorization"] = request.headers.get("authorization")
        observed["organization"] = request.headers.get("openai-organization")
        observed["payload"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "usage": {
                    "prompt_tokens": 120,
                    "completion_tokens": 30,
                    "total_tokens": 150,
                    "prompt_cache_hit_tokens": 80,
                    "prompt_cache_miss_tokens": 40,
                },
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {"content": '{"city":"上海"}'},
                    }
                ]
            },
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = OpenAICompatibleStructuredOutputModel(
        OpenAICompatibleStructuredOutputConfig(
            model="compatible-model",
            base_url="https://models.example/v1/",
            max_completion_tokens=512,
            temperature=0.2,
            thinking="disabled",
        ),
        api_key="secret-key",
        headers={"OpenAI-Organization": "org-test"},
        client=client,
        usage_observer=observed_usage.append,
    )

    result = await provider.generate(_request())

    assert result == {"city": "上海"}
    assert observed["url"] == "https://models.example/v1/chat/completions"
    assert observed["authorization"] == "Bearer secret-key"
    assert observed["organization"] == "org-test"
    payload = observed["payload"]
    assert payload["model"] == "compatible-model"
    assert payload["messages"][1]["content"] == '{"消息":"我住在上海"}'
    assert payload["response_format"] == {
        "type": "json_schema",
        "json_schema": {
            "name": "Memory_Result",
            "strict": False,
            "schema": _request().output_schema,
        },
    }
    assert payload["max_completion_tokens"] == 512
    assert payload["temperature"] == 0.2
    assert payload["thinking"] == {"type": "disabled"}
    assert observed_usage == [
        {
            "input_tokens": 120,
            "output_tokens": 30,
            "total_tokens": 150,
            "cached_input_tokens": 80,
            "cache_miss_input_tokens": 40,
            "reasoning_tokens": 0,
        }
    ]
    assert provider.version.startswith("1.")
    await provider.aclose()
    assert not client.is_closed
    await client.aclose()


async def test_json_object_fallback_places_schema_in_instructions() -> None:
    observed: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        observed.update(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {
                            "content": [
                                {"type": "text", "text": '{"city":'},
                                {"type": "output_text", "text": '"杭州"}'},
                            ]
                        },
                    }
                ]
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = OpenAICompatibleStructuredOutputModel(
            OpenAICompatibleStructuredOutputConfig(
                model="local-model",
                base_url="http://127.0.0.1:8000/v1",
                schema_mode="json_object",
                max_completion_tokens=256,
                max_tokens_parameter="max_tokens",
            ),
            client=client,
        )
        result = await provider.generate(_request())

    assert result == {"city": "杭州"}
    assert observed["response_format"] == {"type": "json_object"}
    assert observed["max_tokens"] == 256
    assert (
        "Return only one JSON object matching this schema"
        in observed["messages"][0]["content"]
    )
    assert '"additionalProperties":false' in observed["messages"][0]["content"]


@pytest.mark.parametrize(
    ("finish_reason", "message", "code", "retryable"),
    [
        ("length", {"content": "{}"}, "truncated", True),
        ("content_filter", {"content": "{}"}, "content_filtered", False),
        ("stop", {"refusal": "sensitive details"}, "refusal", False),
        ("tool_calls", {"content": "{}"}, "invalid_finish_reason", False),
        ("stop", {"content": "not json"}, "invalid_content_json", False),
        ("stop", {"content": "[]"}, "invalid_content_shape", False),
    ],
)
async def test_completion_failures_are_classified_without_content_leakage(
    finish_reason: str,
    message: dict[str, Any],
    code: str,
    retryable: bool,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"choices": [{"finish_reason": finish_reason, "message": message}]},
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = OpenAICompatibleStructuredOutputModel(
            OpenAICompatibleStructuredOutputConfig(model="test-model"),
            client=client,
        )
        with pytest.raises(StructuredOutputProviderError) as captured:
            await provider.generate(_request())

    assert captured.value.code == code
    assert captured.value.retryable is retryable
    assert captured.value.__cause__ is None
    assert "sensitive details" not in str(captured.value)
    assert "not json" not in str(captured.value)


@pytest.mark.parametrize(
    ("status", "body", "code", "retryable"),
    [
        (
            401,
            {"error": {"message": "key secret", "type": "auth_error"}},
            "authentication_error",
            False,
        ),
        (
            429,
            {"error": {"message": "prompt secret", "code": "rate_limit"}},
            "rate_limited",
            True,
        ),
        (503, {"error": {"message": "upstream secret"}}, "http_error", True),
        (400, {"error": {"message": "input secret"}}, "http_error", False),
    ],
)
async def test_http_failures_expose_safe_machine_readable_context(
    status: int,
    body: dict[str, Any],
    code: str,
    retryable: bool,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json=body, headers={"Retry-After": "2.5"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = OpenAICompatibleStructuredOutputModel(
            OpenAICompatibleStructuredOutputConfig(model="test-model"),
            api_key="never-print-this-key",
            client=client,
        )
        with pytest.raises(StructuredOutputProviderError) as captured:
            await provider.generate(_request())

    error = captured.value
    assert error.code == code
    assert error.status_code == status
    assert error.retryable is retryable
    assert error.retry_after_seconds == 2.5
    assert "secret" not in str(error)
    assert "never-print-this-key" not in str(error)
    assert error.__cause__ is None


async def test_transport_timeout_is_retryable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("contains transport details", request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = OpenAICompatibleStructuredOutputModel(
            OpenAICompatibleStructuredOutputConfig(model="test-model"),
            client=client,
        )
        with pytest.raises(StructuredOutputProviderError) as captured:
            await provider.generate(_request())

    assert captured.value.code == "timeout"
    assert captured.value.retryable is True
    assert "transport details" not in str(captured.value)
    assert captured.value.__cause__ is None


async def test_request_and_response_size_limits_fail_closed() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(
            200,
            content=b"x" * 1_025,
            headers={"Content-Type": "application/json"},
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        request_limited = OpenAICompatibleStructuredOutputModel(
            OpenAICompatibleStructuredOutputConfig(
                model="test-model", max_request_bytes=1_024
            ),
            client=client,
        )
        with pytest.raises(
            StructuredOutputProviderError, match="max_request_bytes"
        ) as request_error:
            await request_limited.generate(
                _request().model_copy(update={"input": {"text": "x" * 2_000}})
            )
        assert request_error.value.code == "request_too_large"
        assert calls == 0

        response_limited = OpenAICompatibleStructuredOutputModel(
            OpenAICompatibleStructuredOutputConfig(
                model="test-model", max_response_bytes=1_024
            ),
            client=client,
        )
        with pytest.raises(
            StructuredOutputProviderError, match="max_response_bytes"
        ) as response_error:
            await response_limited.generate(_request())
        assert response_error.value.code == "response_too_large"
        assert calls == 1


def test_config_rejects_secret_urls_reserved_headers_and_invalid_strict_mode() -> None:
    with pytest.raises(ValueError, match="credentials"):
        OpenAICompatibleStructuredOutputConfig(
            model="test", base_url="https://secret@example.com/v1"
        )
    with pytest.raises(ValueError, match="query or fragment"):
        OpenAICompatibleStructuredOutputConfig(
            model="test", base_url="https://example.com/v1?token=secret"
        )
    with pytest.raises(ValueError, match="chat/completions"):
        OpenAICompatibleStructuredOutputConfig(
            model="test", base_url="https://example.com/v1/chat/completions"
        )
    with pytest.raises(ValueError, match="strict_schema"):
        OpenAICompatibleStructuredOutputConfig(
            model="test", schema_mode="json_object", strict_schema=True
        )
    with pytest.raises(ValueError, match="reserved"):
        OpenAICompatibleStructuredOutputModel(
            OpenAICompatibleStructuredOutputConfig(model="test"),
            headers={"Authorization": "Bearer leaked"},
        )


def test_generation_identity_excludes_operational_limits() -> None:
    first = OpenAICompatibleStructuredOutputConfig(
        model="same-model",
        timeout_seconds=10,
        max_request_bytes=2_000,
        max_response_bytes=3_000,
    )
    second = OpenAICompatibleStructuredOutputConfig(
        model="same-model",
        timeout_seconds=90,
        max_request_bytes=4_000,
        max_response_bytes=5_000,
    )
    changed_model = second.model_copy(update={"model": "different-model"})

    assert first.fingerprint != second.fingerprint
    assert first.generation_fingerprint == second.generation_fingerprint
    assert changed_model.generation_fingerprint != second.generation_fingerprint


async def test_reference_analyzer_runs_through_real_provider_boundary() -> None:
    captured_schema: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        captured_schema.update(body["response_format"]["json_schema"]["schema"])
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {
                            "content": json.dumps(
                                {
                                    "memories": [
                                        {
                                            "content": "用户现在住在上海。",
                                            "memory_type": "state",
                                            "topic_key": "residence.primary",
                                            "temporal_status": "current",
                                            "evidence_ids": ["message-1"],
                                        }
                                    ]
                                },
                                ensure_ascii=False,
                            )
                        },
                    }
                ]
            },
        )

    scope = MemoryScope(user_id="owner", agent_id="agent")
    request = PersonalMemoryAnalysisRequest(
        scope=scope,
        messages=[
            ChatMessage(
                actor=Actor.OWNER,
                text="我现在住在上海。",
                at=datetime(2026, 8, 28, tzinfo=UTC),
                message_id="message-1",
                sender_id="owner",
            )
        ],
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = OpenAICompatibleStructuredOutputModel(
            OpenAICompatibleStructuredOutputConfig(model="test-model"),
            client=client,
        )
        analyzer = ReferencePersonalMemoryAnalyzer(provider)
        result = await analyzer.analyze(request)
        planner = ReferencePersonalMemoryQueryPlanner(provider)
        consolidator = ReferenceMemoryConsolidator(provider)

    assert result.memories[0].content == "用户现在住在上海。"
    assert result.memories[0].revision_kind == "assertion"
    assert captured_schema["title"] == "PersonalMemoryAnalysis"
    assert analyzer.version.startswith("8.")
    assert planner.version.startswith("2.")
    assert consolidator.version.startswith("4.")
