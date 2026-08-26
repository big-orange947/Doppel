"""Persona 注入材料与默认模板测试。"""

from __future__ import annotations

from doppel_memory.client import DoppelClient
from doppel_memory.models import ChatMessage, MemoryScope
from tests.fake_store import FakeStore


async def test_inject_persona_collects_materials() -> None:
    store = FakeStore()
    client = DoppelClient(store)
    scope = MemoryScope(user_id="u1", agent_id="qq-bot", platform="qq", chat_type="private", chat_id="c1")

    await client.ingest_event(
        scope, ChatMessage.of("owner", "下周搬家城东", "2026-08-26T09:00:00+08:00", event_id="e1")
    )
    await client.ingest_event(
        scope, ChatMessage.of("contact", "需要帮忙说一声", "2026-08-26T09:01:00+08:00", event_id="e2")
    )
    await client.write_background(scope, "km 是产品经理，负责项目A", tags=["工作"])
    await client.write_relation(scope, counterpart="km", relationship="前同事", address="小刘")

    materials = await client.inject_persona(scope, query="搬家")
    # 命中的记忆线索
    assert any("搬家" in m.fact for m in materials.memories)
    # 号主本人原话进入 few-shot（只有 owner）
    assert "下周搬家城东" in materials.style_samples
    assert all("帮忙说一声" not in s for s in materials.style_samples)
    # 默认模板可拼
    block = materials.to_prompt_block()
    assert "号主视角记忆材料" in block


async def test_persona_block_empty_without_materials() -> None:
    client = DoppelClient(FakeStore())
    scope = MemoryScope(user_id="u1", agent_id="qq-bot", platform="qq", chat_type="private", chat_id="c2")
    materials = await client.inject_persona(scope)
    assert materials.to_prompt_block() == ""
