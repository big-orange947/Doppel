"""三层 API 与材料装配测试。"""

from __future__ import annotations

from doppel_memory.client import DoppelClient
from doppel_memory.models import ChatMessage, MemoryScope


async def test_materials_collect_sections() -> None:
    client = DoppelClient(backend="memory")
    scope = MemoryScope(
        user_id="u1",
        agent_id="qq-bot",
        platform="qq",
        chat_type="private",
        chat_id="c1",
    )

    await client.ingest(
        scope,
        ChatMessage.of(
            "owner", "下周搬家城东", "2026-08-26T09:00:00+08:00", event_id="e1"
        ),
    )
    await client.ingest(
        scope,
        ChatMessage.of(
            "contact", "需要帮忙说一声", "2026-08-26T09:01:00+08:00", event_id="e2"
        ),
    )
    await client.write_background(
        scope, "km 是产品经理，负责项目A，搬家时也会来帮忙", tags=["工作"]
    )
    await client.write_relation(
        scope, counterpart="km", relationship="前同事", address="小刘"
    )

    bundle = await client.materials(scope, query="搬家")
    # 命中事件记忆线索（子串匹配，内存后端无语义检索）
    assert any("搬家" in item.fact for item in bundle.events)
    # 背景 / 关系分成独立小节（空 query 取全量验证分组）
    bundle_all = await client.materials(scope, query="")
    assert any("产品经理" in item.fact for item in bundle_all.background)
    assert any("前同事" in item.fact for item in bundle_all.relations)
    # 号主本人原话进入风格样本（只有 owner，不含 contact）
    assert "下周搬家城东" in bundle_all.style_samples
    assert all("帮忙说一声" not in s for s in bundle_all.style_samples)
    # provenance 带溯源字段
    assert all("memory_id" in p and "authority" in p for p in bundle_all.provenance)
    # 默认模板可拼
    block = bundle_all.render()
    assert "号主视角记忆材料" in block


async def test_materials_with_explicit_scopes_overrides_policy() -> None:
    client = DoppelClient(backend="memory")
    conversation = MemoryScope(
        user_id="u1",
        agent_id="qq-bot",
        platform="qq",
        chat_type="private",
        chat_id="c1",
    )
    user_scope = conversation.user_scope()
    await client.write_background(user_scope, "号主住在城东", tags=["生活"])

    # 显式只查用户级：不检索会话级
    bundle = await client.materials(conversation, query="", scopes=[user_scope])
    assert any("城东" in item.fact for item in bundle.background)
    # 默认策略会带上会话级 + 用户级
    bundle_default = await client.materials(conversation, query="")
    assert bundle_default.scope.group_id == conversation.group_id

    # 显式空列表不会被默认 policy 偷偷替换。
    import pytest

    from doppel_memory.models import MemoryIsolationError

    with pytest.raises(MemoryIsolationError):
        await client.materials(conversation, query="", scopes=[])


async def test_persona_preset_and_custom_renderer() -> None:
    client = DoppelClient(backend="memory")
    scope = MemoryScope(
        user_id="u1",
        agent_id="qq-bot",
        platform="qq",
        chat_type="private",
        chat_id="c1",
    )
    await client.ingest(
        scope,
        ChatMessage.of("owner", "下周搬家", "2026-08-26T09:00:00+08:00", event_id="e1"),
    )

    class JsonRenderer:
        def render(self, bundle) -> str:
            return f'{{"events": {len(bundle.events)}}}'

    bundle = await client.persona_materials(scope, query="搬家")
    assert bundle.render(JsonRenderer()) == '{"events": 1}'
    # 协议式 renderer 也可用
    assert bundle.render()  # 默认

    # 自定义 prompt renderer 不修改 bundle 本身
    assert isinstance(bundle.events, list)


async def test_capabilities_declared() -> None:
    client = DoppelClient(backend="memory")
    caps = client.capabilities
    assert caps.hard_delete is True
    assert caps.semantic_search is False  # 内存后端如实声明
    # 不支持的能力明确报错
    import pytest

    with pytest.raises(NotImplementedError):
        caps.require("semantic_search")
