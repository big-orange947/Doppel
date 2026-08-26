"""Periodic batch-task protocol and safety contracts."""

from __future__ import annotations

from doppel_memory import (
    Actor,
    BatchCheckpoint,
    BatchProposalPlan,
    BatchTaskRunner,
    ChatMessage,
    DoppelClient,
    HistoryWindow,
    InMemoryStore,
    MemoryIsolationError,
    MemoryKind,
    MemoryProposal,
    MemoryScope,
    StoreHistoryReader,
    StoreMemoryReader,
    WriteStatus,
)

SCOPE = MemoryScope(
    user_id="u1",
    agent_id="agent",
    platform="qq",
    chat_type="private",
    chat_id="c1",
)
OTHER_SCOPE = SCOPE.with_chat("qq", "private", "c2")
WINDOW = HistoryWindow(start="2026-08-26T00:00:00Z", end="2026-08-27T00:00:00Z")


async def _seed_history(store: InMemoryStore) -> None:
    await store.write_event(
        SCOPE,
        ChatMessage.of(
            Actor.OWNER,
            "戳一戳",
            "2026-08-26T01:00:00Z",
            event_id="poke-1",
            message_type="nudge",
        ),
    )
    await store.write_event(
        SCOPE,
        ChatMessage.of(
            Actor.CONTACT,
            "戳一戳",
            "2026-08-26T02:00:00Z",
            event_id="poke-2",
            message_type="nudge",
        ),
    )
    await store.write_event(
        OTHER_SCOPE,
        ChatMessage.of(
            Actor.CONTACT,
            "不应读到",
            "2026-08-26T03:00:00Z",
            event_id="other",
        ),
    )


class InteractionPatternTask:
    name = "interaction-pattern"
    version = "1"

    async def propose(self, context):
        page = await context.history.read(
            cursor=context.checkpoint.cursor,
            time_from=context.window.start,
            time_to=context.window.end,
        )
        nudges = [
            message for message in page.messages if message.message_type == "nudge"
        ]
        return BatchProposalPlan(
            proposals=[
                MemoryProposal(
                    scope=context.scope,
                    kind=MemoryKind.RELATION,
                    content=f"本窗口发生 {len(nudges)} 次戳一戳互动",
                    processor=self.name,
                    processor_version=self.version,
                    idempotency_key=f"{self.name}:{context.window.start.isoformat()}",
                )
            ],
            next_checkpoint=BatchCheckpoint(
                cursor=page.next_cursor,
                metadata={"window_end": context.window.end.isoformat()},
            ),
        )


async def test_store_history_reader_is_exact_paginated_and_lossless() -> None:
    store = InMemoryStore()
    await _seed_history(store)
    reader = StoreHistoryReader(store, SCOPE)

    first = await reader.read(limit=1)
    second = await reader.read(cursor=first.next_cursor, limit=1)
    assert [first.messages[0].event_id, second.messages[0].event_id] == [
        "poke-1",
        "poke-2",
    ]
    assert first.messages[0].message_type == "nudge"
    assert first.has_more and not second.has_more


async def test_batch_task_writes_via_common_writer_and_returns_checkpoint() -> None:
    store = InMemoryStore()
    await _seed_history(store)
    result = await DoppelClient(store).run_batch_task(
        InteractionPatternTask(), SCOPE, WINDOW, run_id="run-1"
    )

    assert result.run_id == "run-1"
    assert result.accepted_count == 1
    assert result.write_results[0].status is WriteStatus.CREATED
    assert result.committable_checkpoint is not None
    assert result.committable_checkpoint.metadata["window_end"].endswith("+00:00")
    (stored,) = await store.search("2 次", [SCOPE])
    assert stored.extractor == "interaction-pattern"

    retry = await BatchTaskRunner(store).run_once(
        InteractionPatternTask(), SCOPE, WINDOW, run_id="run-2"
    )
    assert retry.write_results[0].status is WriteStatus.DUPLICATE
    assert retry.committable_checkpoint is not None


class EscapingTask(InteractionPatternTask):
    async def propose(self, context):
        return BatchProposalPlan(
            proposals=[
                MemoryProposal(
                    scope=OTHER_SCOPE,
                    content="scope escape",
                    processor=self.name,
                )
            ],
            next_checkpoint=BatchCheckpoint(cursor="unsafe-progress"),
        )


async def test_failed_batch_does_not_release_checkpoint_or_escape_scope() -> None:
    store = InMemoryStore()
    result = await BatchTaskRunner(store).run_once(EscapingTask(), SCOPE, WINDOW)

    assert result.failed_count == 1
    assert result.write_results[0].error_code == "scope_not_allowed"
    assert result.committable_checkpoint is None
    assert await store.search("scope escape", [OTHER_SCOPE]) == []


async def test_memory_reader_rejects_unauthorized_exact_scope() -> None:
    reader = StoreMemoryReader(InMemoryStore(), [SCOPE])
    try:
        await reader.get(OTHER_SCOPE, "missing")
    except MemoryIsolationError as exc:
        assert "not authorized" in str(exc)
    else:
        raise AssertionError("unauthorized scope should fail")


class BrokenTask:
    name = "broken"
    version = "1"

    async def propose(self, context):
        raise RuntimeError("aggregation unavailable")


async def test_task_failure_is_structured_and_has_no_checkpoint() -> None:
    result = await BatchTaskRunner(InMemoryStore()).run_once(
        BrokenTask(), SCOPE, WINDOW
    )
    assert result.errors[0].stage == "batch_propose"
    assert result.errors[0].processor == "broken"
    assert result.committable_checkpoint is None
