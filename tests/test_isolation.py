"""核心模型与隔离语义测试（框架必备：记忆绝不串台）。"""

from __future__ import annotations

import pytest

from doppel_memory.models import (
    ActorType,
    ChatMessage,
    FactAuthority,
    MemoryIsolationError,
    MemoryScope,
)
from doppel_memory.retriever import Retriever
from tests.fake_store import FakeStore


def test_scope_group_id_normalization() -> None:
    scope = MemoryScope(
        user_id="u 1", agent_id="qq-bot", platform="qq", chat_type="private", chat_id="3807050597"
    )
    # 空格等非法字符规范化为下划线，Graphiti group 安全
    assert scope.group_id == "u_1_qq-bot_qq_private_3807050597"


def test_user_scope_has_no_chat_dimension() -> None:
    scope = MemoryScope(user_id="u1", agent_id="qq-bot", platform="qq", chat_type="private", chat_id="c1")
    user_scope = scope.user_scope()
    assert user_scope.is_user_scope
    assert user_scope.group_id == "u1_qq-bot"
    # 用户级补会话
    restored = user_scope.with_chat("qq", "private", "c1")
    assert restored.group_id == scope.group_id


def test_actor_and_authority() -> None:
    assert ActorType.normalize("OWNER") is ActorType.OWNER
    assert ActorType.normalize("human_self") is ActorType.OWNER
    assert ActorType.normalize("peer") is ActorType.CONTACT
    assert ActorType.normalize("AGENT") is ActorType.AGENT
    assert FactAuthority.of(ActorType.OWNER) is FactAuthority.HUMAN_SELF
    # AGENT 代发不算风格样本/证据
    assert FactAuthority.of(ActorType.AGENT) is FactAuthority.AGENT_OUTPUT


def test_chat_message_identity_key() -> None:
    msg = ChatMessage.of("contact", "快完成了", "2026-08-26T16:51:00+08:00", message_id="m1")
    assert msg.identity_key == "m1"
    msg2 = ChatMessage.of("owner", "好的", "2026-08-26T16:52:00+08:00", event_id="e2")
    assert msg2.identity_key == "e2"
    # 无任何 ID 时 identity_key 为空 → 不做幂等去重（仍可写入）
    msg3 = ChatMessage.of("owner", "嗯", "2026-08-26T16:53:00+08:00")
    assert msg3.identity_key == ""


async def test_recall_without_scope_is_rejected() -> None:
    retriever = Retriever(FakeStore())
    with pytest.raises(MemoryIsolationError):
        await retriever.recall("搬家", [])


async def test_recall_never_crosses_users_sessions() -> None:
    """防串台：同一 query 在 A/B 会话检索结果不相交；用户 X 查不到用户 Y。"""
    store = FakeStore()
    retriever = Retriever(store)
    scope_a = MemoryScope(user_id="u1", agent_id="qq-bot", platform="qq", chat_type="private", chat_id="10001")
    scope_b = MemoryScope(user_id="u1", agent_id="qq-bot", platform="qq", chat_type="private", chat_id="20002")
    scope_y = MemoryScope(user_id="u2", agent_id="qq-bot", platform="qq", chat_type="private", chat_id="30003")

    await store.write_event(scope_a, ChatMessage.of("owner", "我下周搬家城东", "2026-08-26T10:00:00+08:00", event_id="e-a1"))
    await store.write_event(scope_b, ChatMessage.of("contact", "周二吃饭吗", "2026-08-26T10:01:00+08:00", event_id="e-b1"))
    await store.write_event(scope_y, ChatMessage.of("owner", "我下周搬家城东", "2026-08-26T10:02:00+08:00", event_id="e-y1"))

    # A 的查询在 B 里不可见
    hits_a = await retriever.recall("搬家", [scope_a])
    assert len(hits_a) == 1 and hits_a[0].source_event_id == "e-a1"
    hits_b = await retriever.recall("搬家", [scope_b])
    assert hits_b == []
    # 用户 Y 查不到用户 A 的记忆
    hits_y = await retriever.recall("搬家", [scope_y])
    assert len(hits_y) == 1 and hits_y[0].source_event_id == "e-y1"


async def test_ingest_messages_idempotent() -> None:
    """同一批消息重复导入不产生重复记忆。"""
    from doppel_memory.client import DoppelClient

    scope = MemoryScope(user_id="u1", agent_id="qq-bot", platform="qq", chat_type="private", chat_id="c")
    messages = [
        ChatMessage.of("owner", "下周搬家", "2026-08-26T09:00:00+08:00", event_id="e1"),
        ChatMessage.of("contact", "需要帮忙说一声", "2026-08-26T09:01:00+08:00", event_id="e2"),
    ]
    client = DoppelClient(FakeStore())
    first = await client.ingest_messages(scope, messages)
    second = await client.ingest_messages(scope, messages)
    assert first["accepted"] == 2
    assert second["accepted"] == 0 and second["skipped"] == 2
