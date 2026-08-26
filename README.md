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
- 可插拔 MemoryProcessor、周期 BatchTask、MemoryProposal、状态策略和有限 hooks；
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

候选召回与重排是独立扩展点：

```python
class SimilarityReranker:
    async def rerank(self, query, candidates, *, limit):
        return sorted(
            candidates,
            key=lambda item: item.similarity,
            reverse=True,
        )[:limit]

memory = DoppelClient(
    backend="sqlite",
    reranker=SimilarityReranker(),
    candidate_multiplier=4,
)
```

`RetrievalStrategy` 决定如何产生候选，默认实现转发到 `MemoryStore.search()`；`Reranker`
只接收已经通过 scope 检查的候选。有 Reranker 时，Retriever 会按
`limit * candidate_multiplier` 多取候选。自定义 strategy 与 reranker 的输出都会再次经过
exact-scope 白名单和去重，不能注入未授权记忆。

### IM 历史导入

`IMImportBatch` 是可序列化的跨平台 envelope，每条消息携带自己的 exact scope：

```python
from doppel_memory import ChatMessage, IMImportBatch, IMImportItem

batch = IMImportBatch(
    source="qq-export",
    batch_id="page-1",
    items=[
        IMImportItem(
            scope=scope,
            source_id="row-42",
            message=ChatMessage.of(
                "contact",
                "回复上一条消息",
                "2026-08-26T12:01:00+08:00",
                message_id="m2",
                sender_id="contact-1",
                reply_to_id="m1",
                quoted_message_id="m0",
                thread_id="thread-7",
                thread_root_id="m0",
            ),
        )
    ],
)

result = await memory.import_batch(batch)
result.created
result.duplicates
result.failed
```

导入仍使用普通事件的 scope 级幂等语义，因此同一批可安全重放。消息没有平台
message/event ID 时，导入器使用 `source + source_id`（或 batch ID + 序号）生成稳定 fallback
event ID；批次来源保存在 `raw.doppel_import`。`thread_id`、reply、quote 和 thread root 默认
只是消息 provenance；框架不会根据 thread 自动改变 namespace。需要 thread 级隔离时，应在
`IMImportItem.scope` 中显式使用
`scope.with_dimension("thread_id", "thread-7")`。

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

`client.process()` 不传 `processors` 时是 no-op，不会把所有输入悄悄变成长时事件记忆。
需要保存原始事件时使用 `client.ingest()`，或者显式传入确定性的 `EventProcessor()`。

### 周期聚合任务

需要“累计多次戳一戳后形成关系记忆”或 StyleMiner 这类历史统计时，使用独立的
`MemoryBatchTask`，不向在线 `MemoryProcessor` 注入 Store：

```python
from doppel_memory import (
    BatchCheckpoint,
    BatchProposalPlan,
    HistoryWindow,
    MemoryKind,
    MemoryProposal,
)

class InteractionPatternTask:
    name = "interaction-pattern"
    version = "1"

    async def propose(self, context):
        cursor = context.checkpoint.cursor
        nudges = []
        while True:
            page = await context.history.read(
                cursor=cursor,
                time_from=context.window.start,
                time_to=context.window.end,
            )
            nudges.extend(
                m for m in page.messages if m.message_type == "nudge"
            )
            cursor = page.next_cursor
            if not page.has_more:
                break
        proposals = []
        if len(nudges) >= 3:
            proposals.append(
                MemoryProposal(
                    scope=context.scope,
                    kind=MemoryKind.RELATION,
                    content="双方有频繁的轻互动",
                    processor=self.name,
                    processor_version=self.version,
                    idempotency_key=(
                        f"interaction:{context.window.start.isoformat()}"
                    ),
                )
            )
        return BatchProposalPlan(
            proposals=proposals,
            next_checkpoint=BatchCheckpoint(cursor=cursor),
        )

result = await memory.run_batch_task(
    InteractionPatternTask(),
    scope,
    HistoryWindow(start=window_start, end=window_end),
    checkpoint=last_checkpoint,
)
if result.committable_checkpoint is not None:
    await my_checkpoint_store.save(result.committable_checkpoint)
```

任务只拿到 exact-scope 的只读 `ScopedHistoryReader` 和 `ScopedMemoryReader`，返回 proposal，
最终写入仍统一经过 policy、scope 白名单、幂等、hooks 和 Store。调度频率、分布式锁、重试与
checkpoint 持久化由 Agent runtime 决定；Doppel 只运行一次任务，并且仅在本次没有错误时
返回 `committable_checkpoint`。

默认 `StoreHistoryReader` 从支持稳定分页的 Store 读取 `event`。如果表情包、戳一戳等瞬时
事件不应成为长期记忆，可以实现 `ScopedHistoryReader`，直接读取应用自己的聊天事件日志；
它们只作为统计输入存在，达到阈值后生成的关系/风格 proposal 才进入长期记忆。

`next_cursor` 是本页最后已读位置形成的持久 watermark，即使 `has_more=False` 仍然返回；
`has_more` 只控制当前运行是否继续翻页。watermark 是前向的：晚到且排序位置早于 cursor 的
事件不会自动重现，生产调度应使用处理延迟、回看窗口或源端高水位线处理迟到数据。任务切换
filters 时也不应复用旧 cursor。
checkpoint 的 host key 应包含 task name、version 以及影响历史选择的配置摘要；修改事件类型、
阈值或过滤规则时应使用新 key，而不是继续推进旧 watermark。

完整可运行配方把外部 SQLite 事件日志、exact-scope reader、host-owned checkpoint 表和互动
聚合任务组合在一起，原始戳一戳不会进入 Doppel Store：

```bash
python examples/periodic_memory.py
```

Runner 会用 `GuardedHistoryReader` 包装默认或第三方 reader。默认单次运行最多读取 100 页、
50,000 条消息，单页请求最多 2,000 条；可按任务显式收紧或放宽：

```python
from doppel_memory import BatchReadLimits

result = await memory.run_batch_task(
    task,
    scope,
    window,
    read_limits=BatchReadLimits(
        max_pages=20,
        max_messages=5_000,
        max_page_size=500,
    ),
)

result.history_pages_read
result.history_messages_read
```

非空页必须返回并推进 cursor（包括最终页），reader 必须遵守请求的 limit，`has_more=True`
时必须有消息。违反协议或耗尽预算会形成 `history_read` 错误，不释放 checkpoint，也不会写入
proposal。

checkpoint 会绑定 task name/version/schema。任务改变 checkpoint metadata 结构时声明新版本：

```python
class MyTask:
    name = "my-task"
    version = "2"
    checkpoint_schema_version = 2
```

不匹配的输入 checkpoint 会要求 host 迁移或重置；任务返回错误 schema 的 checkpoint 时，
proposal 会在落库前被拦截。旧版未绑定 identity 的 schema 1 checkpoint 仍可兼容读取。

第三方 adapter 可以在测试或诊断脚本中运行无 pytest 的 conformance probe：

```python
from doppel_memory import audit_batch_task, audit_history_reader

reader_report = await audit_history_reader(reader, page_size=2)
reader_report.raise_for_errors()

task_report = await audit_batch_task(task, context)
task_report.raise_for_errors()
```

reader audit 会检查多页推进和最终 exhausted read；应针对不会并发写入的测试 fixture 执行。
task audit 只运行纯 proposal 阶段，不写 Doppel Store，并检查 checkpoint 与 proposal scope。

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

| 后端 | 状态 | substring | full text | semantic | temporal | pagination | graph | hard delete | transactions |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| `memory` | 稳定，测试/示例 | ✅ | — | — | ✅ | ✅ | — | ✅ | — |
| `sqlite` | 稳定，默认参考实现 | ✅ | ✅ FTS5 | — | ✅ | ✅ | — | ✅ | ✅ |
| `graphiti` | 实验性 | — | — | ✅ | ✅ | — | ✅ | — | — |

SQLite 使用 scope 级幂等约束、UTC 时间、WAL/串行连接操作和版本化 schema migration。
schema v3 会在 FTS5 可用时重建已有记录的 content/metadata 索引，并用 trigger 同步后续
insert/update/delete。FTS5 不可用、显式 `enable_fts=False` 或全文查询无结果时，自动回退到
escaped substring search。合法的旧 scope 会自动迁移；空 user/agent 的旧数据需要先修正。
InMemory 与 SQLite 运行同一套 Store conformance suite。

Graphiti 目前只承诺 episode 写入和语义检索；持久化幂等、完整生命周期、删除和完整
provenance 尚未实现。不支持的操作会明确抛出 `NotImplementedError`。

## 开发状态

- [x] v0.2：框架定位、SQLite/InMemory、三层 API、能力声明和 provenance
- [x] v0.2.1：稳定 scope、通用 Store、WriteResult、UTC 时间、生命周期、并发与迁移契约
- [x] v0.3：MemoryProposal/MemoryProcessor 管线、状态策略和有限生命周期 hooks
- [x] v0.4：检索器/Reranker 协议、FTS5、IM 导入格式及 reply/quote/thread 原语
- [x] v0.4.1：周期历史聚合任务、只读 reader、稳定分页和统一 proposal writer
- [x] v0.4.2：持久 watermark、外部事件日志/checkpoint 配方和恢复边界测试
- [x] v0.4.3：读取预算、checkpoint schema 绑定和第三方扩展 conformance probe
- [x] v0.4.4：公共 API 清单、稳定性分级和兼容性快照
- [ ] v0.5：稳定 Graphiti、PostgreSQL/pgvector、可选 StyleMiner/StyleProfessor、benchmark

详细设计见 [`docs/design.md`](docs/design.md)。
从 v0.2 升级时请同时阅读 [`CHANGELOG.md`](CHANGELOG.md) 的 API 迁移说明。

## API 稳定性

应用和第三方扩展应优先从包根导入，例如 `from doppel_memory import MemoryStore`。
根包的公开名称记录在版本化的 [`docs/public-api.json`](docs/public-api.json) 中，并由测试锁定；
其中 `stable` 是 v0.4 系列承诺保持兼容的核心表面，`provisional` 是仍在收敛、但不会在补丁版本中
静默破坏的批处理和 conformance 扩展表面。

未列入清单的子模块对象不是冻结 API。Graphiti 目前仍是 module-only experimental；配方目录下的
host adapter 也不是安装包合同。完整的兼容、弃用和扩展协议规则见
[`docs/api-stability.md`](docs/api-stability.md)。

## License

MIT
