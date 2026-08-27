"""Represent and optionally resolve non-text IM events without implicit memory writes.

Run from the repository root:

    python examples/structured_events.py
"""

from __future__ import annotations

import asyncio

from doppel_memory import (
    Actor,
    ChatMessage,
    ContentPart,
    DoppelClient,
    MediaRef,
    MemoryScope,
    resolve_content,
)


class ExampleImageCaptionResolver:
    """A local fixture; real applications choose their own OCR/caption provider."""

    name = "example.image-caption"
    version = "1"

    async def resolve(self, message: ChatMessage) -> list[ContentPart]:
        images = [
            part
            for part in message.parts
            if part.media is not None and part.media.mime_type.startswith("image/")
        ]
        if not images:
            return []
        return [
            ContentPart(
                type="text",
                text="截图中是一张项目排期表",
                metadata={"confidence": 0.92},
            )
        ]


async def main() -> None:
    scope = MemoryScope(user_id="u1", agent_id="qq-bot")
    memory = DoppelClient(backend="memory")
    image = ChatMessage.of(
        Actor.OWNER,
        "",
        "2026-08-27T10:00:00Z",
        event_id="qq-image-1",
        message_type="image",
        # Existing adapters can keep writing this legacy field during migration.
        attachments=[{"file_id": "legacy-image-1"}],
        parts=[
            ContentPart(
                type="image",
                media=MediaRef(
                    media_id="qq-image-1",
                    uri="qq://media/qq-image-1",
                    mime_type="image/png",
                    filename="schedule.png",
                    width=1280,
                    height=720,
                ),
            )
        ],
        raw={"qq_sequence": 42},
    )
    nudge = ChatMessage.of(
        Actor.CONTACT,
        "",
        "2026-08-27T10:01:00Z",
        event_id="qq-nudge-1",
        message_type="nudge",
        parts=[
            ContentPart(
                type="interaction",
                metadata={"action": "nudge", "target_id": "u1"},
            )
        ],
    )

    try:
        resolution = await resolve_content(image, [ExampleImageCaptionResolver()])
        print("original text:", repr(image.text))
        print("resolved text:", resolution.message.text)
        print("resolver provenance:", resolution.derived_parts[0].metadata)
        print("non-standard event:", nudge.model_dump_json(indent=2))

        # Resolution returns data only. Even process() remains a no-op without an
        # explicitly supplied processor, so no event or derived text is persisted.
        processing = await memory.process(scope, resolution.message)
        assert processing.proposals == []
        assert await memory.recall("排期表", [scope]) == []
    finally:
        await memory.close()


if __name__ == "__main__":
    asyncio.run(main())
