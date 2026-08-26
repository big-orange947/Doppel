"""SQLite-specific durability, migration and concurrency tests."""

from __future__ import annotations

import asyncio
import sqlite3

from doppel_memory import ChatMessage, MemoryScope, SQLiteStore, WriteStatus


async def test_concurrent_distinct_writes_are_lossless(tmp_path) -> None:
    store = SQLiteStore(str(tmp_path / "concurrent.sqlite3"))
    scope = MemoryScope(
        user_id="u", agent_id="bot", platform="qq", chat_type="group", chat_id="g"
    )

    async def write(index: int):
        return await store.write_event(
            scope,
            ChatMessage.of(
                "contact",
                f"message-{index}",
                "2026-08-26T10:00:00Z",
                event_id=f"event-{index}",
            ),
        )

    results = await asyncio.gather(*(write(index) for index in range(100)))
    assert all(result.status is WriteStatus.CREATED for result in results)
    assert (await store.health())["records"] == 100
    await store.close()


async def test_concurrent_duplicate_has_one_winner(tmp_path) -> None:
    store = SQLiteStore(str(tmp_path / "duplicate.sqlite3"))
    scope = MemoryScope(user_id="u", agent_id="bot")
    message = ChatMessage.of("owner", "same", "2026-08-26T10:00:00Z", event_id="same")
    results = await asyncio.gather(
        *(store.write_event(scope, message) for _ in range(25))
    )
    assert sum(result.status is WriteStatus.CREATED for result in results) == 1
    assert sum(result.status is WriteStatus.DUPLICATE for result in results) == 24
    assert len({result.memory_id for result in results}) == 1
    assert (await store.health())["records"] == 1
    await store.close()


async def test_reopen_preserves_extra_dimensions_and_state(tmp_path) -> None:
    database = str(tmp_path / "persistent.sqlite3")
    scope = MemoryScope(user_id="u", agent_id="bot").with_dimension("thread_id", "t1")
    first = SQLiteStore(database)
    result = await first.write_event(
        scope,
        ChatMessage.of("moderator", "persisted", "2026-08-26T10:00:00Z", event_id="p1"),
    )
    await first.close()

    reopened = SQLiteStore(database)
    record = await reopened.get(scope, result.memory_id)
    assert record is not None
    assert record.scope.extra_dimensions == {"thread_id": "t1"}
    assert record.actor == "moderator"
    assert (await reopened.health())["schema_version"] == 3
    await reopened.close()


async def test_v02_schema_is_migrated(tmp_path) -> None:
    database = str(tmp_path / "legacy.sqlite3")
    conn = sqlite3.connect(database)
    conn.executescript(
        """
        CREATE TABLE memories (
            id TEXT PRIMARY KEY, kind TEXT NOT NULL,
            scope_user TEXT NOT NULL, scope_agent TEXT NOT NULL DEFAULT '',
            scope_platform TEXT NOT NULL DEFAULT '', scope_chat_type TEXT NOT NULL DEFAULT '',
            scope_chat_id TEXT NOT NULL DEFAULT '', scope_group TEXT NOT NULL,
            content TEXT NOT NULL, actor TEXT NOT NULL DEFAULT '',
            authority TEXT NOT NULL DEFAULT 'derived_summary',
            state TEXT NOT NULL DEFAULT 'confirmed', tags TEXT NOT NULL DEFAULT '[]',
            importance REAL NOT NULL DEFAULT 0.5, source_event_id TEXT NOT NULL DEFAULT '',
            source_message_id TEXT NOT NULL DEFAULT '', extractor TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
            metadata_json TEXT NOT NULL DEFAULT '{}'
        );
        CREATE UNIQUE INDEX uq_memories_event_id ON memories(source_event_id)
        WHERE source_event_id != '';
        """
    )
    conn.execute(
        """INSERT INTO memories VALUES
           ('legacy-1','event','u','bot','qq','private','c','old-key','legacy','owner',
            'human_self','confirmed','[]',0.5,'legacy-event','','ingestor',
            '2026-08-26T10:00:00+08:00','2026-08-26T10:00:00+08:00','{}')"""
    )
    conn.commit()
    conn.close()

    store = SQLiteStore(database)
    scope = MemoryScope(
        user_id="u", agent_id="bot", platform="qq", chat_type="private", chat_id="c"
    )
    (hit,) = await store.search("legacy", [scope])
    assert hit.memory_id == "legacy-1"
    assert hit.valid_at.isoformat() == "2026-08-26T02:00:00+00:00"
    duplicate = await store.write_event(
        scope,
        ChatMessage.of(
            "owner", "legacy", "2026-08-26T10:00:00Z", event_id="legacy-event"
        ),
    )
    assert duplicate.status is WriteStatus.DUPLICATE
    assert (await store.health())["schema_version"] == 3
    await store.close()


async def test_fts5_indexes_existing_and_new_records(tmp_path) -> None:
    database = str(tmp_path / "fts.sqlite3")
    scope = MemoryScope(user_id="u", agent_id="bot")
    store = SQLiteStore(database)
    await store.write_event(
        scope,
        ChatMessage.of(
            "owner",
            "project alpha deadline Friday",
            "2026-08-26T10:00:00Z",
            event_id="a",
        ),
    )
    await store.write_event(
        scope,
        ChatMessage.of(
            "owner", "project beta meeting", "2026-08-26T10:01:00Z", event_id="b"
        ),
    )
    hits = await store.search("project deadline", [scope])
    assert [item.source_event_id for item in hits] == ["a"]
    assert hits[0].similarity > 0
    health = await store.health()
    assert health["schema_version"] == 3
    assert health["full_text_search"] is True
    await store.close()

    reopened = SQLiteStore(database)
    assert [
        item.source_event_id for item in await reopened.search("beta meeting", [scope])
    ] == ["b"]
    await reopened.close()


async def test_fts5_triggers_follow_hard_delete(tmp_path) -> None:
    store = SQLiteStore(str(tmp_path / "fts-delete.sqlite3"))
    scope = MemoryScope(user_id="u", agent_id="bot")
    created = await store.write_event(
        scope,
        ChatMessage.of(
            "owner", "uniquefulltexttoken", "2026-08-26T10:00:00Z", event_id="fts"
        ),
    )
    assert len(await store.search("uniquefulltexttoken", [scope])) == 1
    assert await store.forget(scope, created.memory_id, hard=True)
    assert await store.search("uniquefulltexttoken", [scope]) == []
    await store.close()


async def test_fts_disabled_retains_substring_search(tmp_path) -> None:
    store = SQLiteStore(str(tmp_path / "substring.sqlite3"), enable_fts=False)
    scope = MemoryScope(user_id="u", agent_id="bot")
    await store.write_event(
        scope,
        ChatMessage.of(
            "owner", "abcdefgh", "2026-08-26T10:00:00Z", event_id="substring"
        ),
    )
    assert len(await store.search("cde", [scope])) == 1
    assert store.capabilities.full_text_search is False
    assert (await store.health())["full_text_search"] is False
    await store.close()
