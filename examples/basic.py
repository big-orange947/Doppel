"""零配置示例：不需要 Neo4j、不需要 API key（默认 SQLite 后端）。

运行：python examples/basic.py
"""

import asyncio

from doppel_memory import ChatMessage, DoppelClient, MemoryScope


async def main() -> None:
    # 零配置：默认 SQLite。示例使用内存数据库，重复运行结果保持一致。
    memory = DoppelClient(backend="sqlite", database=":memory:")

    scope = MemoryScope(
        user_id="u1",
        agent_id="qq-bot",
        platform="qq",
        chat_type="private",
        chat_id="3807050597",
    )

    # 1) 导入历史聊天记录（自动记忆，幂等）
    result = await memory.ingest_messages(
        scope,
        [
            ChatMessage.of(
                "owner", "下周搬家城东", "2026-08-26T09:00:00+08:00", event_id="e1"
            ),
            ChatMessage.of(
                "contact", "需要帮忙说一声", "2026-08-26T09:01:00+08:00", event_id="e2"
            ),
            ChatMessage.of(
                "owner",
                "好啊，到时候联系你",
                "2026-08-26T09:02:00+08:00",
                event_id="e3",
            ),
        ],
    )
    print("ingest:", result)

    # 2) 主动注入聊天以外的背景
    await memory.write_background(
        scope, "km 是产品经理，负责项目A", tags=["工作", "关系"]
    )
    await memory.write_relation(
        scope, counterpart="km", relationship="前同事", address="小刘"
    )

    # 3) 召回当前会话记忆
    hits = await memory.recall("搬家", [scope])
    print("recall 搬家:", [h.fact for h in hits])

    # 4) 获取号主本人原话（风格 few-shot）
    samples = await memory.owner_style_samples(scope)
    print("owner 原话:", samples)

    # 5) 生成结构化人格材料并渲染
    bundle = await memory.persona_materials(scope, query="搬家")
    print("--- 材料结构 ---")
    print(
        "events:",
        len(bundle.events),
        "| background:",
        len(bundle.background),
        "| relations:",
        len(bundle.relations),
        "| style_samples:",
        len(bundle.style_samples),
    )
    print("--- 默认 prompt block ---")
    print(bundle.render())

    await memory.close()


if __name__ == "__main__":
    asyncio.run(main())
