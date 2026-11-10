"""Host-side source identity checks before memory processing; no core API changes."""

from __future__ import annotations

from doppel_memory import (
    ChatMessage,
    MemoryKind,
    MemoryScope,
    MemoryState,
    MemoryStore,
    WriteResult,
    WriteStatus,
)


class SourceEventConflictError(ValueError):
    """An idempotent source identity was reused for different portable content."""


def _portable(message: ChatMessage) -> dict:
    # Delivery IDs/raw payload can differ on retransmission. Stable identity,
    # content, actor, attribution and semantic message coordinates cannot.
    result = message.model_dump(mode="json", exclude={"raw", "event_id", "message_id"})
    result["identity"] = message.identity_key
    return result


async def ingest_checked(
    store: MemoryStore, scope: MemoryScope, message: ChatMessage
) -> WriteResult:
    """Write idempotently, then inspect the committed source before processing it.

    Source conflicts never overwrite the winner. This uses the existing Store
    atomic idempotency contract, not a racy lookup-then-write. Host owns auth and
    must stop the pipeline on conflict. Raw delivery metadata is not compared.
    """
    bound = ChatMessage.model_validate_json(message.model_dump_json())
    if not bound.identity_key:
        raise ValueError("incremental source events require a stable identity")
    result = await store.write_event(scope, bound.model_copy(deep=True))
    record = result.record
    if (
        result.status not in {WriteStatus.CREATED, WriteStatus.DUPLICATE}
        or record is None
    ):
        raise RuntimeError("source event was not committed")
    if (
        record.scope.scope_key != scope.scope_key
        or record.kind != MemoryKind.EVENT
        or record.state != MemoryState.CONFIRMED
        or record.authority != bound.fact_authority
    ):
        raise SourceEventConflictError(
            "source event identity or authority is inconsistent"
        )
    metadata = record.metadata
    stored = ChatMessage(
        actor=record.actor,
        text=record.content,
        at=record.created_at,
        message_id=record.source_message_id,
        event_id=record.source_event_id,
        **{
            key: metadata[key]
            for key in (
                "sender_id",
                "message_type",
                "reply_to_id",
                "quoted_message_id",
                "thread_id",
                "thread_root_id",
                "attachments",
                "parts",
            )
            if key in metadata
        },
    )
    if _portable(stored) != _portable(bound):
        # No text, account identity, tokens or raw transport payload in errors.
        raise SourceEventConflictError(
            "source event identity reused with different portable content"
        )
    return result
