"""PostgreSQL-specific pool, migration, concurrency, and facade integration tests."""

from __future__ import annotations

import asyncio
import os
from uuid import uuid4

import pytest

from doppel_memory import (
    ChatMessage,
    DoppelClient,
    MemoryScope,
    PostgreSQLStore,
    WriteStatus,
)

POSTGRES_DSN = os.environ.get("DOPPEL_TEST_POSTGRES_DSN", "")

pytestmark = pytest.mark.skipif(
    not POSTGRES_DSN,
    reason="DOPPEL_TEST_POSTGRES_DSN is not configured",
)


def _scope(name: str) -> MemoryScope:
    return MemoryScope(
        user_id=f"postgres-runtime-{name}-{uuid4().hex}",
        agent_id="bot",
        platform="test",
        chat_type="private",
        chat_id=name,
    )


async def test_concurrent_distinct_writes_are_lossless() -> None:
    store = PostgreSQLStore(POSTGRES_DSN, min_pool_size=0, max_pool_size=8)
    scope = _scope("distinct")

    async def write(index: int):
        return await store.write_event(
            scope,
            ChatMessage.of(
                "contact",
                f"message-{index}",
                "2026-08-27T10:00:00Z",
                event_id=f"{scope.user_id}-event-{index}",
            ),
        )

    results = await asyncio.gather(*(write(index) for index in range(50)))
    assert all(result.status is WriteStatus.CREATED for result in results)
    assert len(await store.search("message-", [scope], limit=100)) == 50
    await store.close()


async def test_concurrent_duplicate_has_one_database_winner() -> None:
    store = PostgreSQLStore(POSTGRES_DSN, min_pool_size=0, max_pool_size=8)
    scope = _scope("duplicate")
    message = ChatMessage.of(
        "owner",
        "same",
        "2026-08-27T10:00:00Z",
        event_id=f"{scope.user_id}-same",
    )

    results = await asyncio.gather(
        *(store.write_event(scope, message) for _ in range(25))
    )
    assert sum(result.status is WriteStatus.CREATED for result in results) == 1
    assert sum(result.status is WriteStatus.DUPLICATE for result in results) == 24
    assert len({result.memory_id for result in results}) == 1
    await store.close()


async def test_reopen_preserves_jsonb_arrays_and_schema_version() -> None:
    scope = _scope("reopen").with_dimension("thread_id", "topic-1")
    first = PostgreSQLStore(POSTGRES_DSN, min_pool_size=0, max_pool_size=2)
    created = await first.write_event(
        scope,
        ChatMessage.of(
            "owner",
            "persisted",
            "2026-08-27T10:00:00Z",
            event_id=f"{scope.user_id}-persisted",
            raw={"nested": {"unicode": "长期记忆"}},
        ),
    )
    await first.close()

    reopened = PostgreSQLStore(POSTGRES_DSN, min_pool_size=0, max_pool_size=2)
    record = await reopened.get(scope, created.memory_id)
    assert record is not None
    assert record.scope.extra_dimensions == {"thread_id": "topic-1"}
    assert record.metadata["raw"] == {"nested": {"unicode": "长期记忆"}}
    health = await reopened.health()
    assert health["schema_version"] == 1
    assert health["backend"] == "postgresql"
    assert "server_version" in health
    await reopened.close()


async def test_doppel_client_accepts_postgres_alias() -> None:
    client = DoppelClient(
        backend="postgres",
        dsn=POSTGRES_DSN,
        min_pool_size=0,
        max_pool_size=2,
    )
    assert isinstance(client.store, PostgreSQLStore)
    assert (await client.store.health())["ok"] is True
    await client.close()
