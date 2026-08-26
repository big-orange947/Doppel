"""后端契约测试：任意 MemoryStore 实现跑同一套断言。

社区作者实现自己的 store 时只需：
```python
class MyStoreContract(MemoryStoreContract):
    store_factory = MyStore
```
即可验证 scope 隔离/幂等/删除/filter/provenance/时间查询。
"""

from __future__ import annotations

import pytest

from doppel_memory.models import (
    ChatMessage,
    FactAuthority,
    MemoryFilter,
    MemoryKind,
    MemoryScope,
    MemoryState,
)
from doppel_memory.store import MemoryStore

SCOPE_A = MemoryScope(user_id="u1", agent_id="qq-bot", platform="qq", chat_type="private", chat_id="10001")
SCOPE_B = MemoryScope(user_id="u1", agent_id="qq-bot", platform="qq", chat_type="private", chat_id="20002")
SCOPE_Y = MemoryScope(user_id="u2", agent_id="qq-bot", platform="qq", chat_type="private", chat_id="30003")

MSG_A = ChatMessage.of("owner", "我下周搬家城东", "2026-08-26T10:00:00+08:00", event_id="e-a1")
MSG_B = ChatMessage.of("contact", "周二吃饭吗", "2026-08-26T10:01:00+08:00", event_id="e-b1")
MSG_Y = ChatMessage.of("owner", "我下周搬家城东", "2026-08-26T10:02:00+08:00", event_id="e-y1")


class MemoryStoreContract:
    """后端契约：子类定义 store_factory，继承并重命名测试类即可。"""

    store_factory: type[MemoryStore] | None = None

    @pytest.fixture()
    def store(self) -> MemoryStore:
        assert self.store_factory is not None, "store_factory must be defined"
        return self.store_factory()

    # ------------------------------------------------------------ scope 隔离

    async def test_recall_never_crosses_users_sessions(self, store) -> None:
        await store.write_event(SCOPE_A, MSG_A)
        await store.write_event(SCOPE_B, MSG_B)
        await store.write_event(SCOPE_Y, MSG_Y)

        hits_a = await store.search("搬家", [SCOPE_A])
        assert len(hits_a) == 1 and hits_a[0].source_event_id == "e-a1"
        hits_b = await store.search("搬家", [SCOPE_B])
        assert hits_b == []
        hits_y = await store.search("搬家", [SCOPE_Y])
        assert len(hits_y) == 1 and hits_y[0].source_event_id == "e-y1"

    async def test_search_without_scope_rejected(self, store) -> None:
        from doppel_memory.models import MemoryIsolationError

        with pytest.raises(MemoryIsolationError):
            await store.search("搬家", [])

    # ------------------------------------------------------------ 幂等

    async def test_write_event_idempotent(self, store) -> None:
        first = await store.write_event(SCOPE_A, MSG_A)
        assert first.memory_id
        second = await store.write_event(SCOPE_A, MSG_A)
        assert second.memory_id == ""
        hits = await store.search("搬家", [SCOPE_A])
        assert len(hits) == 1

    # ------------------------------------------------------------ filters

    async def test_filter_by_kind_and_actor(self, store) -> None:
        await store.write_event(SCOPE_A, MSG_A)  # owner
        await store.write_event(SCOPE_A, MSG_B)  # contact
        await store.write_background(SCOPE_A, "km 是产品经理", tags=["工作"])

        hits = await store.search(
            "",
            [SCOPE_A],
            filters=MemoryFilter(actors={"contact"}),
        )
        assert len(hits) == 1 and hits[0].actor == "contact"

        hits = await store.search(
            "",
            [SCOPE_A],
            filters=MemoryFilter(kinds={MemoryKind.BACKGROUND}),
        )
        assert len(hits) == 1 and hits[0].kind == MemoryKind.BACKGROUND

    async def test_filter_exclude_agent_authority(self, store) -> None:
        await store.write_event(SCOPE_A, MSG_A)  # owner -> human_self
        await store.write_event(
            SCOPE_A,
            ChatMessage.of("agent", "收到你的消息了", "2026-08-26T10:03:00+08:00", event_id="e-a2"),
        )
        hits = await store.search(
            "",
            [SCOPE_A],
            filters=MemoryFilter(exclude_authorities={FactAuthority.AGENT_OUTPUT}),
        )
        assert all(item.authority != FactAuthority.AGENT_OUTPUT for item in hits)

    # ------------------------------------------------------------ provenance

    async def test_provenance_fields(self, store) -> None:
        await store.write_event(SCOPE_A, MSG_A)
        (hit,) = await store.search("搬家", [SCOPE_A])
        assert hit.source_event_id == "e-a1"
        assert hit.actor == "owner"
        assert hit.authority == FactAuthority.HUMAN_SELF
        assert hit.raw_text == "我下周搬家城东"

    # ------------------------------------------------------------ owner samples

    async def test_owner_style_samples_only_owner(self, store) -> None:
        await store.write_event(SCOPE_A, MSG_A)
        await store.write_event(SCOPE_A, MSG_B)
        samples = await store.list_recent_owner_messages(SCOPE_A)
        assert [s.text for s in samples] == ["我下周搬家城东"]

    # ------------------------------------------------------------ 时间过滤

    async def test_temporal_filter(self, store) -> None:
        await store.write_event(
            SCOPE_A,
            ChatMessage.of("owner", "下周搬家", "2026-08-26T09:00:00+08:00", event_id="e-t1"),
        )
        await store.write_event(
            SCOPE_A,
            ChatMessage.of("owner", "下周吃饭", "2026-08-27T09:00:00+08:00", event_id="e-t2"),
        )
        hits = await store.search(
            "",
            [SCOPE_A],
            filters=MemoryFilter(time_from="2026-08-27T00:00:00+08:00"),
        )
        assert len(hits) == 1 and hits[0].source_event_id == "e-t2"

    # ------------------------------------------------------------ 删除

    async def test_forget_soft_and_hard(self, store) -> None:
        record = await store.write_event(SCOPE_A, MSG_A)
        assert await store.forget(record.memory_id, hard=False)
        if store.capabilities.hard_delete:
            assert await store.forget(record.memory_id, hard=True)
        elif record.memory_id:
            with pytest.raises(NotImplementedError):
                await store.forget(record.memory_id, hard=True)

    # ------------------------------------------------------------ 背景/关系

    async def test_write_background_and_relation(self, store) -> None:
        await store.write_background(SCOPE_A, "km 是产品经理，负责项目A", tags=["工作", "关系"])
        await store.write_relation(SCOPE_A, counterpart="km", relationship="前同事", address="小刘")
        hits = await store.search("产品经理", [SCOPE_A])
        assert len(hits) == 1 and hits[0].kind == MemoryKind.BACKGROUND
        rel = await store.search("", [SCOPE_A], filters=MemoryFilter(kinds={MemoryKind.RELATION}))
        assert len(rel) == 1
