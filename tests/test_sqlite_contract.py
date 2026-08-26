"""SQLiteStore 契约测试（零配置默认后端必须通过全部契约断言）。"""

from __future__ import annotations

import pytest

from doppel_memory.sqlite_store import SQLiteStore


@pytest.fixture()
def store(tmp_path) -> SQLiteStore:
    return SQLiteStore(database=str(tmp_path / "doppel-test.sqlite3"))


class TestSQLiteStoreContract:
    """SQLite 后端契约（复用 MemoryStoreContract 的断言逻辑）。"""

    def _contract(self, store) -> None:
        from tests.store_contract import MemoryStoreContract

        contract = MemoryStoreContract()
        contract.store_factory = SQLiteStore
        return contract

    async def test_recall_never_crosses_users_sessions(self, store) -> None:
        from tests.store_contract import (
            MSG_A,
            MSG_B,
            MSG_Y,
            SCOPE_A,
            SCOPE_B,
            SCOPE_Y,
        )

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

    async def test_write_event_idempotent(self, store) -> None:
        from tests.store_contract import MSG_A, SCOPE_A

        first = await store.write_event(SCOPE_A, MSG_A)
        assert first.memory_id
        second = await store.write_event(SCOPE_A, MSG_A)
        assert second.memory_id == ""
        hits = await store.search("搬家", [SCOPE_A])
        assert len(hits) == 1

    async def test_filter_by_kind_and_actor(self, store) -> None:
        from doppel_memory.models import MemoryFilter, MemoryKind
        from tests.store_contract import MSG_A, MSG_B, SCOPE_A

        await store.write_event(SCOPE_A, MSG_A)
        await store.write_event(SCOPE_A, MSG_B)
        await store.write_background(SCOPE_A, "km 是产品经理", tags=["工作"])

        hits = await store.search("", [SCOPE_A], filters=MemoryFilter(actors={"contact"}))
        assert len(hits) == 1 and hits[0].actor == "contact"

        hits = await store.search(
            "", [SCOPE_A], filters=MemoryFilter(kinds={MemoryKind.BACKGROUND})
        )
        assert len(hits) == 1 and hits[0].kind == MemoryKind.BACKGROUND

    async def test_filter_exclude_agent_authority(self, store) -> None:
        from doppel_memory.models import ChatMessage, FactAuthority, MemoryFilter
        from tests.store_contract import MSG_A, SCOPE_A

        await store.write_event(SCOPE_A, MSG_A)
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

    async def test_provenance_fields(self, store) -> None:
        from tests.store_contract import MSG_A, SCOPE_A

        await store.write_event(SCOPE_A, MSG_A)
        (hit,) = await store.search("搬家", [SCOPE_A])
        assert hit.source_event_id == "e-a1"
        assert hit.actor == "owner"
        assert hit.raw_text == "我下周搬家城东"

    async def test_owner_style_samples_only_owner(self, store) -> None:
        from tests.store_contract import MSG_A, MSG_B, SCOPE_A

        await store.write_event(SCOPE_A, MSG_A)
        await store.write_event(SCOPE_A, MSG_B)
        samples = await store.list_recent_owner_messages(SCOPE_A)
        assert [s.text for s in samples] == ["我下周搬家城东"]

    async def test_temporal_filter(self, store) -> None:
        from doppel_memory.models import ChatMessage, MemoryFilter
        from tests.store_contract import SCOPE_A

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

    async def test_forget_soft_and_hard(self, store) -> None:
        from tests.store_contract import MSG_A, SCOPE_A

        record = await store.write_event(SCOPE_A, MSG_A)
        assert await store.forget(record.memory_id, hard=False)
        assert await store.forget(record.memory_id, hard=True)

    async def test_write_background_and_relation(self, store) -> None:
        from doppel_memory.models import MemoryFilter, MemoryKind
        from tests.store_contract import SCOPE_A

        await store.write_background(SCOPE_A, "km 是产品经理，负责项目A", tags=["工作", "关系"])
        await store.write_relation(SCOPE_A, counterpart="km", relationship="前同事", address="小刘")
        hits = await store.search("产品经理", [SCOPE_A])
        assert len(hits) == 1 and hits[0].kind == MemoryKind.BACKGROUND
        rel = await store.search("", [SCOPE_A], filters=MemoryFilter(kinds={MemoryKind.RELATION}))
        assert len(rel) == 1
