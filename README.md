# Doppel（分身）

> An open-source, role-aware memory framework for IM agents.
> 面向即时通讯代理的模块化记忆框架：说话人感知 · 会话隔离 · 可插拔后端。

Doppel 把即时通讯事件标准化为**带说话人、事实权威、作用域和来源**的记忆，通过可替换的
存储、提取与检索组件，为上层 Agent 提供**结构化记忆材料**。Doppel 不负责生成回复，
也不规定 Agent 如何使用这些材料。

让机器人"像号主本人一样说话"（owner 风格样本 + 人格材料注入）是 Doppel 的**典型用途之一**，
但不是框架的全部——你可以只用事件记忆、只用关系记忆，或完全不做人格模仿。

## 框架边界

```
IM Platform / Agent Runtime
          │
          │  normalized events / memory query
          ▼
        Doppel
  ingest · store · retrieve
  scope · provenance · materials
          │
          ▼
Memory Backend / Extractor / Embedder
```

**Doppel 负责**：IM 消息标准化、scope 隔离、记忆摄入与生命周期、检索与过滤、
结构化材料生成、后端抽象与能力声明。

**Doppel 不负责**：对话路由、回复生成、工具调用、消息发送、短期上下文管理、
平台协议、确认 UI、强制 prompt 模板、"怎样才算像本人"的唯一判断。

## 为什么是 Doppel

| 能力 | Mem0 | MemoBase | Zep | **Doppel** |
| --- | --- | --- | --- | --- |
| 自动提取对话记忆 | ✅ | ✅ | ✅ | ✅ |
| scope（用户/Agent/会话/联系人） | user_id | user 级 | 图隔离 | **五元组 + extra 维度** |
| 时间感知图谱 | 部分 | — | ✅（Graphiti） | ✅（Graphiti 同源，extra） |
| **区分说话人（OWNER/CONTACT/AGENT）** | ❌ | ❌ | ❌ | ✅ |
| **事实权威（agent 输出不算证据/风格样本）** | ❌ | ❌ | ❌ | ✅ |
| **确认闭环（候选→生效，防学歪）** | ❌ | ❌ | ❌ | ✅ |
| 后端能力声明（semantic/temporal/hard_delete） | 隐含 | 隐含 | 隐含 | ✅ 显式 |
| 存储后端可替换 | ✅ | ✅ | 仅自家 | ✅ 契约测试保证 |

## 快速开始（零配置）

```bash
pip install doppel-memory
python examples/basic.py
```

不需要 Neo4j、不需要 API key——默认 SQLite 后端：

```python
from doppel_memory import ChatMessage, DoppelClient, MemoryScope

memory = DoppelClient(backend="sqlite", database="doppel.sqlite3")  # 零配置默认

scope = MemoryScope(user_id="u1", agent_id="qq-bot", platform="qq",
                    chat_type="private", chat_id="3807050597")

# ① 导入历史聊天（自动记忆，幂等）
await memory.ingest_messages(scope, [
    ChatMessage.of("owner", "下周搬家城东", "2026-08-26T09:00:00+08:00", event_id="e1"),
    ChatMessage.of("contact", "需要帮忙说一声", "2026-08-26T09:01:00+08:00", event_id="e2"),
])

# ② 主动注入聊天以外的背景 / 关系
await memory.write_background(scope, "km 是产品经理，负责项目A", tags=["工作"])
await memory.write_relation(scope, counterpart="km", relationship="前同事", address="小刘")

# ③ 生成回复前拿结构化记忆材料
bundle = await memory.persona_materials(scope, query="搬家")
bundle.events        # 事件线索
bundle.background    # 背景
bundle.relations     # 关系
bundle.style_samples # 号主原话（只含 owner）
bundle.provenance    # 溯源

# ④ 渲染成 prompt 块（模板可替换，框架不替你写最终 prompt）
prompt_block = bundle.render()
```

## 三层 API

```python
# 低层：直连后端，完全控制
await memory.store.search("搬家", [scope], filters=MemoryFilter(actors={"owner"}))

# 中层：标准流程 + filters 组合
hits = await memory.recall("搬家", [scope, scope.user_scope()],
                           filters=MemoryFilter(kinds={"event", "background"}))

# 高层：结构化材料 + persona preset（可替换 renderer / scope policy）
bundle = await memory.materials(scope, query="搬家")          # 默认 OwnerPersonaPolicy
bundle = await memory.persona_materials(scope, "搬家")         # preset 快捷方式
bundle.render(MyRenderer())                                    # 自定义渲染
```

## 多用户隔离（绝不串台）

- scope 五元组：`user_id + agent_id + platform + chat_type + chat_id`（+ extra 维度）
- **无 scope 的检索 API 不存在**（接口层面拒绝，防误用）
- 检索 scope 由开发者显式传入（或注册 ScopePolicy），框架不硬编码"自动加用户级"
- 契约测试保证：同一 query 在不同 scope 结果不相交，用户 X 查不到用户 Y

## 后端

| 后端 | 安装 | semantic | temporal | graph | hard_delete |
| --- | --- | --- | --- | --- | --- |
| `sqlite`（默认） | `doppel-memory` | — | ✅ | — | ✅ |
| `memory`（测试/示例） | `doppel-memory` | — | ✅ | — | ✅ |
| `graphiti`（高级图谱） | `doppel-memory[graphiti]` | ✅ | ✅ | ✅ | 软删 |

新后端实现 `MemoryStore` 接口后，跑 `tests/store_contract.py` 契约测试即可保证行为一致。

## 开发状态

- [x] v0.2 核心协议 + SQLite/InMemory 后端 + 契约测试 + 三层 API + provenance + 能力声明
- [ ] v0.3 MemoryProcessor 管线（EventProcessor/FactExtractor/RelationExtractor）+ 确认闭环状态
- [ ] v0.4 IM 专用能力（reply/quote/thread 关系、平台导入格式、owner 风格样本 preset）
- [ ] v0.5 StyleMiner/StyleProfessor + 时间关系/冲突事实 + PostgreSQL/pgvector

## License

MIT
