"""Async OpenAI-compatible structured generation without a vendor SDK."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from types import TracebackType
from typing import Any, Literal, Self
from urllib.parse import urlsplit, urlunsplit

import httpx
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from doppel_memory.intelligence import StructuredGenerationRequest


class StructuredOutputProviderError(RuntimeError):
    """A structured-output endpoint failed without exposing response or key data."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        status_code: int | None = None,
        retryable: bool = False,
        retry_after_seconds: float | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.status_code = status_code
        self.retryable = retryable
        self.retry_after_seconds = retry_after_seconds


class OpenAICompatibleStructuredOutputConfig(BaseModel):
    """Endpoint and bounded request policy; secrets intentionally live elsewhere."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    model: str
    base_url: str = "https://api.openai.com/v1"
    schema_mode: Literal["json_schema", "json_object"] = "json_schema"
    strict_schema: bool = False
    timeout_seconds: float = Field(default=60.0, gt=0.0, le=600.0)
    max_request_bytes: int = Field(default=1_000_000, ge=1_024, le=20_000_000)
    max_response_bytes: int = Field(default=2_000_000, ge=1_024, le=20_000_000)
    max_completion_tokens: int | None = Field(default=None, ge=1, le=1_000_000)
    max_tokens_parameter: Literal["max_completion_tokens", "max_tokens"] = (
        "max_completion_tokens"
    )
    temperature: float | None = Field(default=None, ge=0.0, le=2.0)

    @field_validator("model", mode="before")
    @classmethod
    def _require_model(cls, value: Any) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("OpenAI-compatible model is required")
        return normalized

    @field_validator("base_url", mode="before")
    @classmethod
    def _normalize_base_url(cls, value: Any) -> str:
        raw = str(value or "").strip().rstrip("/")
        parsed = urlsplit(raw)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("base_url must be an absolute HTTP(S) URL")
        if parsed.username or parsed.password:
            raise ValueError("base_url must not contain credentials")
        if parsed.query or parsed.fragment:
            raise ValueError("base_url must not contain a query or fragment")
        path = parsed.path.rstrip("/")
        if path.endswith("/chat/completions"):
            raise ValueError("base_url must not include the chat/completions endpoint")
        return urlunsplit((parsed.scheme, parsed.netloc, path, "", ""))

    @model_validator(mode="after")
    def _strict_requires_schema_mode(self) -> OpenAICompatibleStructuredOutputConfig:
        if self.strict_schema and self.schema_mode != "json_schema":
            raise ValueError("strict_schema requires schema_mode='json_schema'")
        return self

    @property
    def endpoint(self) -> str:
        return f"{self.base_url}/chat/completions"

    @property
    def fingerprint(self) -> str:
        payload = json.dumps(
            self.model_dump(mode="json"),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()

    @property
    def generation_fingerprint(self) -> str:
        payload = {
            "base_url": self.base_url,
            "max_completion_tokens": self.max_completion_tokens,
            "max_tokens_parameter": (
                self.max_tokens_parameter
                if self.max_completion_tokens is not None
                else None
            ),
            "model": self.model,
            "schema_mode": self.schema_mode,
            "strict_schema": self.strict_schema,
            "temperature": self.temperature,
        }
        encoded = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()


class OpenAICompatibleStructuredOutputModel:
    """OpenAI-compatible chat-completions adapter for ``StructuredOutputModel``."""

    name = "doppel.openai-compatible-structured-output"

    def __init__(
        self,
        config: OpenAICompatibleStructuredOutputConfig,
        *,
        api_key: str = "",
        headers: Mapping[str, str] | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.config = OpenAICompatibleStructuredOutputConfig.model_validate(config)
        self._api_key = str(api_key or "").strip()
        self._headers = _normalize_headers(headers)
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(
            timeout=self.config.timeout_seconds,
            follow_redirects=False,
        )

    @property
    def version(self) -> str:
        return f"1.{self.config.generation_fingerprint[:16]}"

    async def generate(self, request: StructuredGenerationRequest) -> Mapping[str, Any]:
        bound = StructuredGenerationRequest.model_validate(request)
        payload = self._payload(bound)
        encoded = json.dumps(
            payload,
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        if len(encoded) > self.config.max_request_bytes:
            raise StructuredOutputProviderError(
                "request_too_large",
                "structured-output request exceeds max_request_bytes",
            )
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            **self._headers,
        }
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        try:
            response = await self._client.post(
                self.config.endpoint,
                content=encoded,
                headers=headers,
                timeout=self.config.timeout_seconds,
            )
        except httpx.TimeoutException:
            raise StructuredOutputProviderError(
                "timeout",
                "structured-output provider timed out",
                retryable=True,
            ) from None
        except httpx.TransportError:
            raise StructuredOutputProviderError(
                "transport_error",
                "structured-output provider transport failed",
                retryable=True,
            ) from None

        if len(response.content) > self.config.max_response_bytes:
            raise StructuredOutputProviderError(
                "response_too_large",
                "structured-output response exceeds max_response_bytes",
                status_code=response.status_code,
            )
        if not 200 <= response.status_code < 300:
            raise _http_error(response)
        try:
            envelope = response.json()
        except (json.JSONDecodeError, UnicodeDecodeError, ValueError):
            raise StructuredOutputProviderError(
                "invalid_response_json",
                "structured-output provider returned invalid response JSON",
                status_code=response.status_code,
            ) from None
        return _structured_content(envelope, status_code=response.status_code)

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        await self.aclose()

    def _payload(self, request: StructuredGenerationRequest) -> dict[str, Any]:
        schema = request.output_schema
        if schema.get("type") != "object":
            raise StructuredOutputProviderError(
                "invalid_request",
                "structured-output schema root must have type='object'",
            )
        try:
            schema_json = json.dumps(
                schema,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
        except (TypeError, ValueError):
            raise StructuredOutputProviderError(
                "invalid_request",
                "structured-output schema is not JSON serializable",
            ) from None
        instructions = request.instructions.strip()
        if not instructions:
            raise StructuredOutputProviderError(
                "invalid_request",
                "structured-output instructions must not be empty",
            )
        if self.config.schema_mode == "json_object":
            instructions = (
                f"{instructions}\nReturn only one JSON object matching this schema:\n"
                f"{schema_json}"
            )
            response_format: dict[str, Any] = {"type": "json_object"}
        else:
            response_format = {
                "type": "json_schema",
                "json_schema": {
                    "name": _schema_name(schema),
                    "strict": self.config.strict_schema,
                    "schema": schema,
                },
            }
        try:
            input_json = json.dumps(
                request.input,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
        except (TypeError, ValueError):
            raise StructuredOutputProviderError(
                "invalid_request",
                "structured-output input is not JSON serializable",
            ) from None
        payload: dict[str, Any] = {
            "model": self.config.model,
            "messages": [
                {"role": "system", "content": instructions},
                {"role": "user", "content": input_json},
            ],
            "response_format": response_format,
        }
        if self.config.max_completion_tokens is not None:
            payload[self.config.max_tokens_parameter] = (
                self.config.max_completion_tokens
            )
        if self.config.temperature is not None:
            payload["temperature"] = self.config.temperature
        return payload


def _normalize_headers(headers: Mapping[str, str] | None) -> dict[str, str]:
    normalized: dict[str, str] = {}
    for raw_name, raw_value in dict(headers or {}).items():
        name = str(raw_name or "").strip()
        value = str(raw_value or "").strip()
        if not name or "\r" in name or "\n" in name:
            raise ValueError("custom header names must be non-empty single lines")
        if "\r" in value or "\n" in value:
            raise ValueError("custom header values must be single lines")
        if name.lower() in {"authorization", "content-length", "host"}:
            raise ValueError("custom header is reserved")
        normalized[name] = value
    return normalized


def _schema_name(schema: Mapping[str, Any]) -> str:
    title = str(schema.get("title", "") or "doppel_output")
    normalized = re.sub(r"[^A-Za-z0-9_-]+", "_", title).strip("_-")
    return (normalized or "doppel_output")[:64]


def _http_error(response: httpx.Response) -> StructuredOutputProviderError:
    status = response.status_code
    if status in {401, 403}:
        code = "authentication_error"
    elif status == 429:
        code = "rate_limited"
    else:
        code = "http_error"
    retryable = status in {408, 409, 425, 429} or 500 <= status <= 599
    return StructuredOutputProviderError(
        code,
        f"structured-output provider returned HTTP {status}",
        status_code=status,
        retryable=retryable,
        retry_after_seconds=_retry_after(response.headers.get("retry-after")),
    )


def _structured_content(envelope: Any, *, status_code: int) -> Mapping[str, Any]:
    if not isinstance(envelope, Mapping):
        raise StructuredOutputProviderError(
            "invalid_response_shape",
            "structured-output response envelope must be an object",
            status_code=status_code,
        )
    choices = envelope.get("choices")
    if not isinstance(choices, list) or not choices:
        raise StructuredOutputProviderError(
            "invalid_response_shape",
            "structured-output response has no choices",
            status_code=status_code,
        )
    choice = choices[0]
    if not isinstance(choice, Mapping):
        raise StructuredOutputProviderError(
            "invalid_response_shape",
            "structured-output choice must be an object",
            status_code=status_code,
        )
    finish_reason = str(choice.get("finish_reason", "") or "").strip().lower()
    if finish_reason == "length":
        raise StructuredOutputProviderError(
            "truncated",
            "structured-output response was truncated",
            status_code=status_code,
            retryable=True,
        )
    if finish_reason == "content_filter":
        raise StructuredOutputProviderError(
            "content_filtered",
            "structured-output response was content-filtered",
            status_code=status_code,
        )
    if finish_reason not in {"", "stop"}:
        raise StructuredOutputProviderError(
            "invalid_finish_reason",
            "structured-output response ended with an unexpected finish reason",
            status_code=status_code,
        )
    message = choice.get("message")
    if not isinstance(message, Mapping):
        raise StructuredOutputProviderError(
            "invalid_response_shape",
            "structured-output response has no assistant message",
            status_code=status_code,
        )
    refusal = message.get("refusal")
    if refusal:
        raise StructuredOutputProviderError(
            "refusal",
            "structured-output model refused the request",
            status_code=status_code,
        )
    content = message.get("content")
    if isinstance(content, Mapping):
        return dict(content)
    if isinstance(content, list):
        text_parts = [
            str(item.get("text", ""))
            for item in content
            if isinstance(item, Mapping) and item.get("type") in {"text", "output_text"}
        ]
        content = "".join(text_parts)
    if not isinstance(content, str) or not content.strip():
        raise StructuredOutputProviderError(
            "missing_content",
            "structured-output response has no content",
            status_code=status_code,
        )
    try:
        decoded = json.loads(content)
    except (json.JSONDecodeError, UnicodeDecodeError, ValueError):
        raise StructuredOutputProviderError(
            "invalid_content_json",
            "structured-output message content is not valid JSON",
            status_code=status_code,
        ) from None
    if not isinstance(decoded, Mapping):
        raise StructuredOutputProviderError(
            "invalid_content_shape",
            "structured-output message content must be a JSON object",
            status_code=status_code,
        )
    return dict(decoded)


def _retry_after(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        parsed = float(value)
    except ValueError:
        return None
    return parsed if parsed >= 0 else None
