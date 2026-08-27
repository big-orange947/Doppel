"""Reusable conformance suite for every stable MemoryStore backend."""

from __future__ import annotations

import pytest

from doppel_memory.models import (
    Actor,
    ChatMessage,
    ContentPart,
    FactAuthority,
    MediaRef,
    MemoryFilter,
    MemoryIsolationError,
    MemoryKind,
    MemoryRecord,
    MemoryScope,
    MemoryState,
    MemoryStateConflictError,
    WriteStatus,
)

SCOPE_A = MemoryScope(
    user_id="u1", agent_id="qq-bot", platform="qq", chat_type="private", chat_id="10001"
)
SCOPE_B = MemoryScope(
    user_id="u1", agent_id="qq-bot", platform="qq", chat_type="private", chat_id="20002"
)
SCOPE_Y = MemoryScope(
    user_id="u2", agent_id="qq-bot", platform="qq", chat_type="private", chat_id="30003"
)
MSG_A = ChatMessage.of(
    "owner", "我下周搬家城东", "2026-08-26T10:00:00+08:00", event_id="e-a1"
)
MSG_B = ChatMessage.of(
    "contact", "周二吃饭吗", "2026-08-26T10:01:00+08:00", event_id="e-b1"
)
MSG_Y = ChatMessage.of(
    "owner", "我下周搬家城东", "2026-08-26T10:02:00+08:00", event_id="e-y1"
)


class MemoryStoreContract:
    """Subclasses only provide a ``store`` fixture; all assertions are shared."""

    async def test_recall_never_crosses_exact_scopes(self, store) -> None:
        await store.write_event(SCOPE_A, MSG_A)
        await store.write_event(SCOPE_B, MSG_B)
        await store.write_event(SCOPE_Y, MSG_Y)
        assert [
            hit.source_event_id for hit in await store.search("搬家", [SCOPE_A])
        ] == ["e-a1"]
        assert await store.search("搬家", [SCOPE_B]) == []
        assert [
            hit.source_event_id for hit in await store.search("搬家", [SCOPE_Y])
        ] == ["e-y1"]

    async def test_search_without_scope_rejected(self, store) -> None:
        with pytest.raises(MemoryIsolationError):
            await store.search("搬家", [])

    async def test_scan_is_exact_stable_and_paginated(self, store) -> None:
        at = "2026-08-26T10:00:00Z"
        for memory_id in ("page-a", "page-b", "page-c"):
            await store.put(
                MemoryRecord(
                    memory_id=memory_id,
                    scope=SCOPE_A,
                    kind=MemoryKind.EVENT,
                    content=memory_id,
                    actor=Actor.OWNER,
                    created_at=at,
                    updated_at=at,
                )
            )
        await store.put(
            MemoryRecord(
                memory_id="other-scope",
                scope=SCOPE_B,
                kind=MemoryKind.EVENT,
                content="other-scope",
                actor=Actor.OWNER,
                created_at=at,
                updated_at=at,
            )
        )

        first = await store.scan(SCOPE_A, limit=2)
        assert [record.memory_id for record in first.records] == ["page-a", "page-b"]
        assert first.has_more and first.next_cursor
        second = await store.scan(SCOPE_A, cursor=first.next_cursor, limit=2)
        assert [record.memory_id for record in second.records] == ["page-c"]
        assert not second.has_more and second.next_cursor
        exhausted = await store.scan(SCOPE_A, cursor=second.next_cursor, limit=2)
        assert exhausted.records == []
        assert not exhausted.has_more
        assert exhausted.next_cursor == second.next_cursor
        assert store.capabilities.pagination

        with pytest.raises(ValueError, match="invalid memory page cursor"):
            await store.scan(SCOPE_A, cursor="not-a-cursor")

    async def test_scan_cursor_is_a_forward_only_watermark(self, store) -> None:
        for memory_id, at in (
            ("watermark-a", "2026-08-26T01:00:00Z"),
            ("watermark-b", "2026-08-26T02:00:00Z"),
        ):
            await store.put(
                MemoryRecord(
                    memory_id=memory_id,
                    scope=SCOPE_A,
                    content=memory_id,
                    created_at=at,
                    updated_at=at,
                )
            )
        initial = await store.scan(SCOPE_A)

        for memory_id, at in (
            ("watermark-late", "2026-08-26T01:30:00Z"),
            ("watermark-next", "2026-08-26T03:00:00Z"),
        ):
            await store.put(
                MemoryRecord(
                    memory_id=memory_id,
                    scope=SCOPE_A,
                    content=memory_id,
                    created_at=at,
                    updated_at=at,
                )
            )
        delta = await store.scan(SCOPE_A, cursor=initial.next_cursor)
        assert [record.memory_id for record in delta.records] == ["watermark-next"]

    async def test_scope_hierarchy_is_explicit(self, store) -> None:
        user_scope = SCOPE_A.user_scope()
        await store.write_background(user_scope, "全局背景")
        assert await store.search("全局背景", [SCOPE_A]) == []
        assert len(await store.search("全局背景", [user_scope])) == 1
        assert len(await store.search("全局背景", [SCOPE_A, user_scope])) == 1

    async def test_extra_dimensions_are_isolated(self, store) -> None:
        thread_a = SCOPE_A.with_dimension("thread_id", "a")
        thread_b = SCOPE_A.with_dimension("thread_id", "b")
        await store.write_event(
            thread_a,
            ChatMessage.of(
                "owner", "thread-a", "2026-08-26T10:00:00Z", event_id="thread-a"
            ),
        )
        assert len(await store.search("thread-a", [thread_a])) == 1
        assert await store.search("thread-a", [thread_b]) == []

    async def test_write_event_idempotent_per_scope(self, store) -> None:
        first = await store.write_event(SCOPE_A, MSG_A)
        second = await store.write_event(SCOPE_A, MSG_A)
        same_id_other_scope = await store.write_event(SCOPE_B, MSG_A)
        assert first.status is WriteStatus.CREATED
        assert second.status is WriteStatus.DUPLICATE
        assert second.memory_id == first.memory_id
        assert same_id_other_scope.status is WriteStatus.CREATED
        assert len(await store.search("搬家", [SCOPE_A])) == 1
        assert len(await store.search("搬家", [SCOPE_B])) == 1

    async def test_generic_put_supports_custom_kind(self, store) -> None:
        result = await store.put(
            MemoryRecord(
                scope=SCOPE_A,
                kind="example.preference",
                content="喜欢短回复",
                actor="moderator",
                state=MemoryState.CANDIDATE,
            ),
            idempotency_key="preference:short",
        )
        assert result.status is WriteStatus.CREATED
        (hit,) = await store.search(
            "短回复", [SCOPE_A], filters=MemoryFilter(kinds={"example.preference"})
        )
        assert hit.actor == "moderator"
        assert hit.state is MemoryState.CANDIDATE

    async def test_returned_record_does_not_alias_backend_state(self, store) -> None:
        result = await store.write_event(SCOPE_A, MSG_A)
        assert result.record is not None
        result.record.content = "caller mutation"
        stored = await store.get(SCOPE_A, result.memory_id)
        assert stored is not None and stored.content == MSG_A.text

    async def test_filters_and_provenance(self, store) -> None:
        await store.write_event(SCOPE_A, MSG_A)
        await store.write_event(SCOPE_A, MSG_B)
        await store.write_background(SCOPE_A, "km 是产品经理", tags=["工作"])
        contacts = await store.search(
            "", [SCOPE_A], filters=MemoryFilter(actors={Actor.CONTACT})
        )
        assert len(contacts) == 1 and contacts[0].actor == Actor.CONTACT
        backgrounds = await store.search(
            "", [SCOPE_A], filters=MemoryFilter(kinds={MemoryKind.BACKGROUND})
        )
        assert len(backgrounds) == 1
        (event,) = await store.search("搬家", [SCOPE_A])
        assert event.source_event_id == "e-a1"
        assert event.actor == Actor.OWNER
        assert event.authority is FactAuthority.HUMAN_SELF
        assert event.raw_text == MSG_A.text
        assert event.scope == SCOPE_A

    async def test_filter_exclude_agent_authority(self, store) -> None:
        await store.write_event(SCOPE_A, MSG_A)
        await store.write_event(
            SCOPE_A,
            ChatMessage.of(
                "agent", "收到你的消息了", "2026-08-26T10:03:00+08:00", event_id="e-a2"
            ),
        )
        hits = await store.search(
            "",
            [SCOPE_A],
            filters=MemoryFilter(exclude_authorities={FactAuthority.AGENT_OUTPUT}),
        )
        assert all(hit.authority is not FactAuthority.AGENT_OUTPUT for hit in hits)

    async def test_owner_style_samples_only_active_owner(self, store) -> None:
        owner = await store.write_event(SCOPE_A, MSG_A)
        await store.write_event(SCOPE_A, MSG_B)
        assert [
            message.text for message in await store.list_recent_owner_messages(SCOPE_A)
        ] == [MSG_A.text]
        await store.forget(SCOPE_A, owner.memory_id)
        assert await store.list_recent_owner_messages(SCOPE_A) == []

    async def test_owner_message_relationship_provenance_round_trip(
        self, store
    ) -> None:
        message = ChatMessage.of(
            "owner",
            "linked message",
            "2026-08-26T10:00:00Z",
            message_id="linked",
            sender_id="owner-id",
            reply_to_id="reply-target",
            quoted_message_id="quote-target",
            thread_id="thread-1",
            thread_root_id="root-1",
            raw={"sequence": 7},
            parts=[
                ContentPart(type="text", text="linked message"),
                ContentPart(
                    type="image",
                    media=MediaRef(media_id="image-7", mime_type="image/png"),
                ),
            ],
        )
        await store.write_event(SCOPE_A, message)
        restored = (await store.list_recent_owner_messages(SCOPE_A))[0]
        assert restored.sender_id == "owner-id"
        assert restored.reply_to_id == "reply-target"
        assert restored.quoted_message_id == "quote-target"
        assert restored.thread_id == "thread-1"
        assert restored.thread_root_id == "root-1"
        assert restored.raw == {"sequence": 7}
        assert restored.parts == message.parts

    async def test_temporal_filter_normalizes_timezones(self, store) -> None:
        await store.write_event(
            SCOPE_A,
            ChatMessage.of(
                "owner", "较早", "2026-08-26T23:30:00+08:00", event_id="e-t1"
            ),
        )
        await store.write_event(
            SCOPE_A,
            ChatMessage.of("owner", "较晚", "2026-08-26T16:00:00Z", event_id="e-t2"),
        )
        hits = await store.search(
            "", [SCOPE_A], filters=MemoryFilter(time_from="2026-08-26T15:45:00Z")
        )
        assert [hit.source_event_id for hit in hits] == ["e-t2"]

    async def test_soft_forget_hides_and_hard_delete_removes(self, store) -> None:
        result = await store.write_event(SCOPE_A, MSG_A)
        assert await store.forget(SCOPE_A, result.memory_id, hard=False)
        assert await store.search("搬家", [SCOPE_A]) == []
        inactive = await store.search(
            "搬家", [SCOPE_A], filters=MemoryFilter(include_inactive=True)
        )
        assert len(inactive) == 1 and inactive[0].state is MemoryState.EXPIRED
        if store.capabilities.hard_delete:
            assert await store.forget(SCOPE_A, result.memory_id, hard=True)
            assert await store.get(SCOPE_A, result.memory_id) is None

    async def test_get_and_delete_are_scope_guarded(self, store) -> None:
        result = await store.write_event(SCOPE_A, MSG_A)
        assert await store.get(SCOPE_B, result.memory_id) is None
        assert not await store.forget(SCOPE_B, result.memory_id, hard=True)
        assert await store.get(SCOPE_A, result.memory_id) is not None

    async def test_state_transition_uses_optimistic_guard(self, store) -> None:
        result = await store.put(
            MemoryRecord(
                scope=SCOPE_A,
                kind=MemoryKind.FACT,
                content="候选事实",
                state=MemoryState.CANDIDATE,
            )
        )
        confirmed = await store.transition(
            SCOPE_A,
            result.memory_id,
            MemoryState.CONFIRMED,
            expected_state=MemoryState.CANDIDATE,
        )
        assert confirmed.state is MemoryState.CONFIRMED
        assert confirmed.version == 2
        with pytest.raises(MemoryStateConflictError):
            await store.transition(
                SCOPE_A,
                result.memory_id,
                MemoryState.REJECTED,
                expected_state=MemoryState.CANDIDATE,
            )

    async def test_write_background_and_relation(self, store) -> None:
        await store.write_background(
            SCOPE_A, "km 是产品经理，负责项目A", tags=["工作", "关系"]
        )
        await store.write_relation(
            SCOPE_A, counterpart="km", relationship="前同事", address="小刘"
        )
        assert len(await store.search("产品经理", [SCOPE_A])) == 1
        relations = await store.search(
            "", [SCOPE_A], filters=MemoryFilter(kinds={MemoryKind.RELATION})
        )
        assert len(relations) == 1
