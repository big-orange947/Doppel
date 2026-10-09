"""Graphiti bridge to Doppel's durable, cached structured generation runtime.

Uses chat/completions, not Graphiti's default Responses API. The host controls
attempts/bytes in the existing cross-process ledger. No retries or secret files.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

import httpx
from graphiti_core.llm_client.client import (
    LLMClient,
    get_extraction_language_instruction,
)
from graphiti_core.llm_client.config import DEFAULT_MAX_TOKENS, LLMConfig, ModelSize
from graphiti_core.prompts.models import Message
from pydantic import BaseModel

from doppel_memory.intelligence import (
    StructuredGenerationRequest,
    StructuredOutputModel,
)
from doppel_memory.openai_compatible import (
    OpenAICompatibleStructuredOutputConfig,
    OpenAICompatibleStructuredOutputModel,
)


class GraphitiChatTransport:
    """Fixed transport identity, with a bounded output limit on each request."""

    name = "doppel.graphiti-chat-transport"

    def __init__(
        self,
        config: OpenAICompatibleStructuredOutputConfig,
        *,
        api_key: str,
        usage_observer: Callable[[Mapping[str, int]], None],
        client: httpx.AsyncClient | None = None,
    ) -> None:
        if config.max_completion_tokens is None:
            raise ValueError("graph transport requires an explicit output cap")
        self.config, self.api_key = config, api_key
        self.output_cap = config.max_completion_tokens
        self.usage_observer, self.client = usage_observer, client
        self.version = "1." + config.generation_fingerprint

    async def generate(self, request: StructuredGenerationRequest) -> Mapping[str, Any]:
        cap = request.input.get("effective_max_tokens")
        if type(cap) is not int or not 1 <= cap <= self.output_cap:
            raise ValueError("invalid graph output limit")
        provider = OpenAICompatibleStructuredOutputModel(
            self.config.model_copy(update={"max_completion_tokens": cap}),
            api_key=self.api_key,
            usage_observer=self.usage_observer,
            client=self.client,
        )
        try:
            return await provider.generate(request)
        finally:
            if self.client is None:
                await provider.aclose()


class DurableGraphitiLLMClient(LLMClient):
    """Graphiti protocol adapter; all misses flow through a host-cached model.

    The adapter deliberately overrides generate_response to avoid the base
    tenacity retry path. Clone messages before Graphiti's attribute preamble.
    Prompt name, group, schema, language, instructions and effective cap are all
    part of the exact structured request/cache identity.
    """

    def __init__(self, model: StructuredOutputModel, *, output_cap: int) -> None:
        if not 1 <= output_cap <= 16_384:
            raise ValueError("invalid Graphiti output cap")
        super().__init__(
            LLMConfig(model=model.name, temperature=0, max_tokens=output_cap)
        )
        self.structured_model, self.output_cap = model, output_cap

    async def generate_response(
        self,
        messages: list[Message],
        response_model: type[BaseModel] | None = None,
        max_tokens: int | None = None,
        model_size: ModelSize = ModelSize.medium,
        group_id: str | None = None,
        prompt_name: str | None = None,
        *,
        attribute_extraction: bool = False,
    ) -> dict[str, Any]:
        if not messages:
            raise ValueError("Graphiti requires at least one message")
        requested = self.output_cap if max_tokens is None else max_tokens
        if type(requested) is not int or requested < 1:
            raise ValueError("invalid Graphiti requested output limit")
        copies = [message.model_copy(deep=True) for message in messages]
        self._apply_attribute_extraction_preamble(copies, attribute_extraction)
        system = "\n\n".join(m.content for m in copies if m.role == "system")
        instructions = (
            system
            + get_extraction_language_instruction(group_id)
            + "\nProcess graphiti_messages in order as the extraction dialogue. "
            "Return exactly the requested JSON object, without markdown fences."
        )
        raw = await self.structured_model.generate(
            StructuredGenerationRequest(
                instructions=instructions,
                input={
                    "graphiti_messages": [
                        {"role": m.role, "content": self._clean_input(m.content)}
                        for m in copies
                        if m.role != "system"
                    ],
                    "group_id": group_id,
                    "prompt_name": prompt_name,
                    "model_size": model_size.value,
                    "effective_max_tokens": min(requested, self.output_cap),
                },
                output_schema=response_model.model_json_schema()
                if response_model
                else {
                    "type": "object",
                    "additionalProperties": True,
                },
            )
        )
        value = raw.model_dump(mode="json") if isinstance(raw, BaseModel) else dict(raw)
        if response_model:
            return response_model.model_validate(value).model_dump(mode="json")
        return value

    async def _generate_response(
        self,
        messages: list[Message],
        response_model: type[BaseModel] | None = None,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        model_size: ModelSize = ModelSize.medium,
    ) -> dict[str, Any]:
        return await self.generate_response(
            messages, response_model, max_tokens, model_size
        )
