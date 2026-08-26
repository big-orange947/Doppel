# Doppel（分身）

> An open-source, role-aware memory framework for IM agents.
>
> 面向即时通讯代理的模块化记忆框架：说话人感知、精确作用域、完整溯源、可插拔后端。

Doppel 把即时通讯事件标准化为带说话人、事实权威、作用域和来源的记忆，为上层
Agent 提供摄入、生命周期、过滤检索和结构化材料能力。Doppel 不生成回复，不负责
消息路由或发送，也不规定开发者如何消费记忆。

“让机器人更接近号主的表达方式”是一个可选 preset；你也可以只使用事件记忆、关系
记忆、自定义记忆类型，或者完全替换材料构建逻辑。

## 框架边界

```text
IM Platform / Agent Runtime
          │ normalized events / explicit scopes
          ▼
        Doppel
 put · ingest · process · search · lifecycle · materials
 role · authority · scope · provenance
          │
          ▼
 InMemory / SQLite / experimental Graphiti / custom store
```

Doppel 负责：

- 标准化 IM 消息和开放式 actor；
- 无碰撞、可扩展的 exact scope namespace；
- 通用记忆写入、幂等、状态转换和删除；
- 可插拔 MemoryProcessor、MemoryProposal、状态策略和有限 hooks；
- 按 kind、actor、authority、state、tag、重要性和时间过滤；
- 可追溯的检索结果和结构化材料；
- 可替换后端及明确的能力声明。

Doppel 不负责：

- 对话路由、回复生成、工具调用和消息发送；
- 完整短期上下文管理和具体平台协议；
- 确认 UI、统一 LLM provider 或强制 prompt 模板；
- 替开发者决定哪些记忆应该参与当前回复。

## 安装

核心包只依赖 Pydantic，默认包含 InMemory 和 SQLite 后端：

```bash
pip install doppel-memory
```

实验性 Graphiti 后端需要额外依赖：

```bash
pip install "doppel-memory[graphiti]"
```

## 快速开始

```python
from doppel_memory import ChatMessage, DoppelClient, MemoryScope, WriteStatus

memory = DoppelClient(backend="sqlite", database="doppel.sqlite3")

scope = MemoryScope(
    user_id="u1",
    agent_id="qq-bot",
    platform="qq",
    chat_type="private",
    chat_id="3807050597",
)

result = await memory.ingest(
    scope,
    ChatMessage.of(
        "contact",
        "快完成了，下午发给你",
        "2026-08-26T16:51:00+08:00",
        event_id="evt-123",
    ),
)
assert result.status is WriteStatus.CREATED

hits = await memory.recall("下午发", [scope])
bundle = await memory.materials(scope, query="项目进度")
prompt_block = bundle.render()  # 默认 renderer 只是便利工具，可以替换

await memory.close()
```

完整零配置示例：

```bash
python examples/basic.py
```

## 三层 API

### 低层：Store 协议

自定义 kind 和底层工具可以直接通过通用 `MemoryRecord` 写入：

```python
from doppel_memory import MemoryRecord, MemoryState

result = await memory.put(
    MemoryRecord(
        scope=scope,
        kind="my_agent.preference",
        content="偏好短回复",
        actor="moderator",
        state=MemoryState.CANDIDATE,
    ),
    idempotency_key="preference:short-replies",
)
```

`WriteResult.status` 会明确区分 `created`、`updated`、`duplicate`、`skipped` 和
`failed`，不会用一个空字符串同时表示多种结果。

### 中层：摄入与检索

```python
from doppel_memory import FactAuthority, MemoryFilter

await memory.ingest_messages(scope, messages)

hits = await memory.recall(
    "搬家",
    [scope, scope.user_scope()],
    filters=MemoryFilter(
        kinds={"event", "background"},
        exclude_authorities={FactAuthority.AGENT_OUTPUT},
    ),
)
```

Store 只做 exact scope 匹配。需要会话级、联系人级和用户级多层召回时，由开发者显式
传入多个 scope，或者在高层 API 注册 `ScopePolicy`。

### Processor 管线

Processor 只分析标准化消息并返回 proposal，不直接接触 Store。下面的规则处理器只是示例；
你可以换成自己的规则、模型或远程服务：

```python
from doppel_memory import (
    MemoryKind,
    MemoryProposal,
    MemoryState,
)

class PreferenceProcessor:
    name = "my.preference"
    version = "1"

    async def process(self, scope, message):
        if "短回复" not in message.text:
            return []
        return [
            MemoryProposal(
                scope=scope.user_scope(),
                kind=MemoryKind.FACT,
                content="用户偏好短回复",
                actor=message.actor,
                confidence=0.9,
                proposed_state=MemoryState.CANDIDATE,
                idempotency_key="preference:short-replies",
                source_message_id=message.message_id,
                processor=self.name,
                processor_version=self.version,
            )
        ]

result = await memory.process(
    scope,
    message,
    processors=[PreferenceProcessor()],
    # 跨到 user scope 必须由调用方显式授权。
    allowed_scopes=[scope.user_scope()],
)
```

`ProposalPolicy.evaluate()` 可以保留、修改或拒绝 proposal。默认 policy 原样保留
`proposed_state`，不会内置置信度阈值或确认规则。`before_process`、`after_proposal`、
`before_write`、`after_write`、`on_error` 是全部生命周期 hooks；框架不建立无限扩张的
中间件体系。

不传 `processors` 时，`client.process()` 使用确定性的 `EventProcessor`；显式传入空列表则
是 no-op。已有 `client.ingest()` 保持兼容，仍然是写入单条原始事件的最短路径。

### 高层：结构化材料

```python
bundle = await memory.materials(scope, query="搬家")

bundle.events
bundle.background
bundle.relations
bundle.style_samples
bundle.provenance

text = bundle.render()              # 默认文本 renderer
text = bundle.render(MyRenderer())  # JSON/XML/ChatML/自定义格式
```

`persona_materials()` 是默认 OwnerPersonaPolicy 的快捷 preset，不是唯一的材料策略。

## Scope 语义

`MemoryScope` 支持常用 IM 维度和自定义维度：

```python
thread_scope = scope.with_dimension("thread_id", "456")
```

所有维度都会进入 canonical `scope_key`。`group_id` 是兼容别名；`describe()` 提供可读
日志文本。不同 thread、topic 或自定义 dimension 不会被映射到同一 namespace。

后端不会隐式扩大检索范围：

```python
await memory.recall(query, [scope])               # 只查当前 exact scope
await memory.recall(query, [scope, user_scope])   # 显式加入用户全局记忆
```

读取、状态转换和删除都必须携带 scope，避免仅凭一个 memory ID 跨 namespace 操作。

## 生命周期

内置状态为：

```text
candidate · confirmed · rejected · superseded · expired
```

普通检索默认只返回 candidate 和 confirmed；可通过
`MemoryFilter(include_inactive=True)` 显式查询其他状态。

```python
confirmed = await memory.transition(
    scope,
    memory_id,
    MemoryState.CONFIRMED,
    expected_state=MemoryState.CANDIDATE,
)

await memory.forget(scope, memory_id)            # 软删除：转为 expired
await memory.forget(scope, memory_id, hard=True) # 后端支持时硬删除
```

`expected_state` 提供乐观并发保护。

## 后端

| 后端 | 状态 | substring | semantic | temporal | graph | hard delete | transactions |
|---|---|---:|---:|---:|---:|---:|---:|
| `memory` | 稳定，测试/示例 | ✅ | — | ✅ | — | ✅ | — |
| `sqlite` | 稳定，默认参考实现 | ✅ | — | ✅ | — | ✅ | ✅ |
| `graphiti` | 实验性 | — | ✅ | ✅ | ✅ | — | — |

SQLite 使用 scope 级幂等约束、UTC 时间、WAL/串行连接操作和版本化 schema migration。
合法的 v0.2 scope 会在首次打开数据库时自动迁移；空 user/agent 的旧数据需要先修正。
InMemory 与 SQLite 运行同一套 Store conformance suite。

Graphiti 目前只承诺 episode 写入和语义检索；持久化幂等、完整生命周期、删除和完整
provenance 尚未实现。不支持的操作会明确抛出 `NotImplementedError`。

## 开发状态

- [x] v0.2：框架定位、SQLite/InMemory、三层 API、能力声明和 provenance
- [x] v0.2.1：稳定 scope、通用 Store、WriteResult、UTC 时间、生命周期、并发与迁移契约
- [x] v0.3：MemoryProposal/MemoryProcessor 管线、状态策略和有限生命周期 hooks
- [ ] v0.4：检索器/Reranker 协议、FTS5、IM 导入格式及 reply/quote/thread 原语
- [ ] v0.5：稳定 Graphiti、PostgreSQL/pgvector、可选 StyleMiner/StyleProfessor、benchmark

详细设计见 [`docs/design.md`](docs/design.md)。
从 v0.2 升级时请同时阅读 [`CHANGELOG.md`](CHANGELOG.md) 的 API 迁移说明。

## License

MIT
