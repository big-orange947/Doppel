"""Stable source identities are not permission to silently change source content."""

import asyncio
from datetime import UTC, datetime

import pytest

from doppel_memory import (
    ChatMessage,
    InMemoryStore,
    MemoryScope,
    MemoryState,
    SQLiteStore,
)
from examples.checked_ingest import SourceEventConflictError, ingest_checked

SCOPE = MemoryScope(user_id="owner", agent_id="test")


@pytest.fixture(params=["memory", "sqlite"])
async def store(request, tmp_path):
    value = (
        InMemoryStore()
        if request.param == "memory"
        else SQLiteStore(database=str(tmp_path / "source.sqlite3"))
    )
    yield value
    await value.close()


def message(**updates):
    return ChatMessage(
        actor="owner",
        text="synthetic-private-body",
        at=datetime(2026, 1, 1, tzinfo=UTC),
        message_id="stable",
        **updates,
    )


@pytest.mark.parametrize(
    "field,value",
    [
        ("text", "different"),
        ("actor", "agent"),
        ("sender_id", "another"),
        ("reply_to_id", "other-parent"),
        ("at", datetime(2026, 1, 2, tzinfo=UTC)),
    ],
)
async def test_payload_conflict_keeps_original(store, field, value):
    original = message()
    first = await ingest_checked(store, SCOPE, original)
    with pytest.raises(SourceEventConflictError) as error:
        await ingest_checked(store, SCOPE, original.model_copy(update={field: value}))
    assert "synthetic-private-body" not in str(error.value)
    assert (await store.get(SCOPE, first.memory_id)).content == original.text


async def test_retransmission_can_have_different_raw_delivery_metadata(store):
    first = await ingest_checked(
        store, SCOPE, message(event_id="delivery-1", raw={"trace": "one"})
    )
    retry = await ingest_checked(
        store, SCOPE, message(event_id="delivery-2", raw={"trace": "two"})
    )
    assert first.memory_id == retry.memory_id
    assert retry.status.value == "duplicate"


async def test_same_id_in_different_scope_is_independent(store):
    first = await ingest_checked(store, SCOPE, message())
    other = SCOPE.model_copy(update={"user_id": "another-owner"})
    second = await ingest_checked(store, other, message())
    assert first.memory_id != second.memory_id


async def test_concurrent_different_payloads_have_one_winner(store):
    results = await asyncio.gather(
        ingest_checked(store, SCOPE, message()),
        ingest_checked(
            store, SCOPE, message().model_copy(update={"text": "competing"})
        ),
        return_exceptions=True,
    )
    assert sum(isinstance(value, SourceEventConflictError) for value in results) == 1
    assert sum(not isinstance(value, Exception) for value in results) == 1


async def test_missing_identity_fails_before_write(store):
    with pytest.raises(ValueError, match="stable identity"):
        await ingest_checked(
            store, SCOPE, message().model_copy(update={"message_id": ""})
        )


async def test_inactive_source_is_not_reactivated_by_retransmission(store):
    original = await ingest_checked(store, SCOPE, message())
    await store.transition(SCOPE, original.memory_id, MemoryState.EXPIRED)
    with pytest.raises(SourceEventConflictError):
        await ingest_checked(store, SCOPE, message())
    assert (await store.get(SCOPE, original.memory_id)).state == MemoryState.EXPIRED
