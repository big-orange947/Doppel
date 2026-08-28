"""Run the reference personal-memory analyzer through a compatible endpoint.

Environment:
    DOPPEL_MODEL                 required model identifier
    DOPPEL_API_KEY               optional for unauthenticated local endpoints
    DOPPEL_OPENAI_BASE_URL       defaults to https://api.openai.com/v1
"""

from __future__ import annotations

import asyncio
import os
from datetime import UTC, datetime

from doppel_memory import (
    Actor,
    ChatMessage,
    MemoryScope,
    OpenAICompatibleStructuredOutputConfig,
    OpenAICompatibleStructuredOutputModel,
    PersonalMemoryAnalysisRequest,
    ReferencePersonalMemoryAnalyzer,
)


async def main() -> None:
    model = os.environ.get("DOPPEL_MODEL", "").strip()
    if not model:
        raise RuntimeError("set DOPPEL_MODEL before running this example")
    config = OpenAICompatibleStructuredOutputConfig(
        model=model,
        base_url=os.environ.get("DOPPEL_OPENAI_BASE_URL", "https://api.openai.com/v1"),
    )
    async with OpenAICompatibleStructuredOutputModel(
        config,
        api_key=os.environ.get("DOPPEL_API_KEY", ""),
    ) as provider:
        analyzer = ReferencePersonalMemoryAnalyzer(provider)
        result = await analyzer.analyze(
            PersonalMemoryAnalysisRequest(
                scope=MemoryScope(user_id="owner", agent_id="personal-agent"),
                messages=[
                    ChatMessage(
                        actor=Actor.OWNER,
                        text="更正一下，我现在长期住在杭州。",
                        at=datetime.now(UTC),
                        message_id="example-message-1",
                        sender_id="owner",
                    )
                ],
            )
        )
    print(result.model_dump_json(indent=2))


if __name__ == "__main__":
    asyncio.run(main())
