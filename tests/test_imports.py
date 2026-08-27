"""Portable IM import envelope and relationship provenance."""

from __future__ import annotations

from doppel_memory import (
    ChatMessage,
    ContentPart,
    DoppelClient,
    IMImportBatch,
    IMImportItem,
    MediaRef,
    MemoryScope,
)


def test_import_batch_round_trips_json_and_normalizes_time() -> None:
    scope = MemoryScope(user_id="u", agent_id="bot")
    batch = IMImportBatch(
        source="qq-export",
        source_version="2026.1",
        batch_id="batch-1",
        exported_at="2026-08-26T12:00:00+08:00",
        items=[
            IMImportItem(
                scope=scope,
                source_id="row-1",
                message=ChatMessage.of(
                    "contact",
                    "引用并回复",
                    "2026-08-26T12:01:00+08:00",
                    message_id="m2",
                    sender_id="contact-1",
                    reply_to_id="m1",
                    quoted_message_id="m0",
                    thread_id="thread-7",
                    thread_root_id="m0",
                    parts=[
                        ContentPart(
                            type="file",
                            media=MediaRef(
                                media_id="file-1",
                                filename="notes.txt",
                                mime_type="text/plain",
                            ),
                        )
                    ],
                ),
            )
        ],
    )
    restored = IMImportBatch.model_validate_json(batch.model_dump_json())
    assert restored.exported_at.isoformat() == "2026-08-26T04:00:00+00:00"
    assert restored.items[0].scope == scope
    assert restored.items[0].message.thread_id == "thread-7"
    assert restored.items[0].message.parts[0].media is not None
    assert restored.items[0].message.parts[0].media.filename == "notes.txt"
    assert "reply=m1" in restored.items[0].message.episode_line()
    assert "quote=m0" in restored.items[0].message.episode_line()
    assert "thread=thread-7" in restored.items[0].message.episode_line()


async def test_import_batch_supports_multiple_exact_scopes_and_idempotency() -> None:
    left = MemoryScope(
        user_id="u", agent_id="bot", platform="qq", chat_type="private", chat_id="left"
    )
    right = MemoryScope(
        user_id="u", agent_id="bot", platform="qq", chat_type="private", chat_id="right"
    )
    batch = IMImportBatch(
        source="fixture",
        items=[
            IMImportItem(
                scope=left,
                message=ChatMessage.of(
                    "owner", "left message", "2026-08-26T10:00:00Z", message_id="same"
                ),
            ),
            IMImportItem(
                scope=right,
                message=ChatMessage.of(
                    "owner", "right message", "2026-08-26T10:01:00Z", message_id="same"
                ),
            ),
        ],
    )
    progress: list[tuple[int, int]] = []
    client = DoppelClient(backend="memory")
    first = await client.import_batch(
        batch, progress=lambda done, total: progress.append((done, total))
    )
    second = await client.import_batch(batch)
    assert first.total == first.accepted == first.created == 2
    assert second.duplicates == 2
    assert progress == [(1, 2), (2, 2)]
    assert [item.fact for item in await client.recall("message", [left])] == [
        "left message"
    ]
    assert [item.fact for item in await client.recall("message", [right])] == [
        "right message"
    ]


async def test_import_source_id_supplies_stable_fallback_identity() -> None:
    scope = MemoryScope(user_id="u", agent_id="bot")
    batch = IMImportBatch(
        source="legacy-export",
        batch_id="page-1",
        items=[
            IMImportItem(
                scope=scope,
                source_id="row-42",
                metadata={"line": 42},
                message=ChatMessage.of(
                    "contact", "no platform id", "2026-08-26T10:00:00Z"
                ),
            )
        ],
    )
    client = DoppelClient(backend="memory")
    first = await client.import_batch(batch)
    second = await client.import_batch(batch)
    assert first.created == 1
    assert second.duplicates == 1
    stored = first.write_results[0].record
    assert stored is not None
    assert stored.source_event_id == "import:legacy-export:row-42"
    assert stored.metadata["raw"]["doppel_import"]["item_metadata"] == {"line": 42}


async def test_message_relationships_survive_store_round_trip() -> None:
    scope = MemoryScope(user_id="u", agent_id="bot")
    client = DoppelClient(backend="memory")
    message = ChatMessage.of(
        "owner",
        "linked",
        "2026-08-26T10:00:00Z",
        message_id="m2",
        sender_id="u",
        reply_to_id="m1",
        quoted_message_id="m0",
        thread_id="t1",
        thread_root_id="m0",
        raw={"platform_sequence": 42},
    )
    await client.ingest(scope, message)
    restored = (await client.store.list_recent_owner_messages(scope))[0]
    assert restored.sender_id == "u"
    assert restored.reply_to_id == "m1"
    assert restored.quoted_message_id == "m0"
    assert restored.thread_id == "t1"
    assert restored.thread_root_id == "m0"
    assert restored.raw == {"platform_sequence": 42}
