# Doppel（分身）

> A persona memory framework for AI chat agents — 让聊天机器人像号主本人一样说话的长期记忆框架。

Doppel 是一个**专门适配机器人代理聊天**的开源记忆框架。接入后，你的聊天机器人在多用户、
多会话并发场景下：

- 📌 **记得每个会话发生过什么**（事件记忆，可溯源）
- 🎭 **学会号主本人的说话风格**（风格记忆：口吻、口头禅、长度、标点、称呼）
- 🧩 **主动注入聊天以外的背景**（职业、关系、项目、偏好）
- 🚧 **记忆绝不串台**（scope 五元组强隔离 + 防串台测试）

对标 Mem0 / MemoBase 的易用 API，但它们是"通用记忆层"，Doppel 专做"**代理聊天的人格复刻**"。

## 为什么是 Doppel

| 能力 | Mem0 | MemoBase | Zep | **Doppel** |
| --- | --- | --- | --- | --- |
| 自动提取对话记忆 | ✅ | ✅ | ✅ | ✅ |
| 用户/会话隔离 | user_id | user 级 | 图隔离 | **user_id + agent_id + 会话（五元组）** |
| 时间感知图谱 | 部分 | — | ✅（Graphiti） | ✅（Graphiti 同源） |
| **区分说话人（OWNER/CONTACT/AGENT）** | ❌ | ❌ | ❌ | ✅ |
| **学习号主本人的说话风格** | ❌ | ❌ | ❌ | ✅（StyleMiner + StyleProfessor） |
| **人格注入（像本人发的）** | ❌ | 静态 persona | ❌ | ✅（PersonaInjector） |
| **确认闭环（防学歪）** | ❌ | ❌ | ❌ | ✅（候选→确认→生效） |

一句话：**Mem0 的易用性 + Zep 的时间图谱 + Memobase 的用户画像 + 独有的代理人格复刻。**

## 快速开始

```bash
pip install -e .
```

```python
from doppel_memory import DoppelClient, MemoryScope

memory = DoppelClient(backend="graphiti", neo4j_uri="bolt://127.0.0.1:7687", ...)

# ① 每来一条消息都喂进去（自动记忆，幂等）
await memory.ingest_event(
    scope=MemoryScope(user_id="u1", agent_id="qq-bot", platform="qq",
                      chat_type="private", chat_id="3807050597"),
    actor="contact",
    text="快完成了，下午发给你",
    at="2026-08-26T16:51:00+08:00",
    event_id="evt-123",
)

# ② 生成回复前拿"号主视角"记忆材料
materials = await memory.inject_persona(scope=scope, query="昨天布置的任务")

# ③ 拼进你自己的 prompt（怎么拼你说了算）
prompt = f"{my_system_prompt}\n{materials.to_prompt_block()}"
```

## 接入三步

任何 agent 框架（LangGraph、裸 asyncio、其他都行）接入 Doppel 只需要：

1. `await memory.ingest_event(scope, msg)` —— 喂消息（每条都喂）
2. `await memory.inject_persona(scope, query)` —— 拿记忆材料
3. `memory.write_background(...)` —— 主动塞背景（可选）

**框架职责边界**（详见 docs）：

- ✅ Doppel 负责：记忆存储/提取/检索、scope 隔离、溯源、生命周期、人格材料
- ❌ 不碰：对话路由、回复生成、工具执行、短期上下文窗口、平台协议、最终 prompt 组装

## 核心能力

- **事件记忆**：会话内每条消息（带 actorType/factAuthority）→ 时间感知图谱
- **批量导入**：`ingest_messages(messages, scope)` 一次性记忆历史聊天记录（幂等）
- **风格记忆**：只学习 `actor=owner`（号主本人）的消息，AGENT 代发不算风格样本
- **人格注入**：风格画像 + 号主原话 few-shot + 关系 + 背景 → 组装成"号主视角"
- **多用户隔离**：scope 五元组（user_id + agent_id + platform + chat_type + chat_id），检索必须带 scope

## 开发状态

- [x] v0.1 框架骨架（存储抽象 / 事件摄入 / 检索 / 隔离测试）
- [ ] StyleMiner（词频风格统计）
- [ ] StyleProfessor（LLM 风格反思 + 确认闭环）
- [ ] Mem0 风格 `add()` / MemoBase 风格记忆分区
- [ ] 多后端（SQLite + 向量 / PostgreSQL）

## License

MIT
