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
 InMemory / SQLite / PostgreSQL / custom Store
          + explicit pgvector / Graphiti semantic indexes
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

PostgreSQL 是独立可选依赖，不会增加默认安装体积：

```bash
pip install "doppel-memory[postgres]"
```

使用 PostgreSQL 上的可选 pgvector 语义索引：

```bash
pip install "doppel-memory[pgvector]"
```

这个 extra 提供异步 PostgreSQL 客户端；数据库服务器仍需单独安装并启用 pgvector extension。

实验性 Graphiti 语义/图索引需要额外依赖：

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

需要服务端并发和多进程共享时可以直接使用 PostgreSQL 后端；连接池和迁移在第一次操作时
懒初始化，DSN 不会出现在 health 输出中：

```python
from doppel_memory import DoppelClient, PostgreSQLStore

store = PostgreSQLStore(
    "postgresql://doppel:secret@127.0.0.1:5432/agent_memory",
    min_pool_size=1,
    max_pool_size=10,
)
memory = DoppelClient(store)

# 等价的 facade 写法：
memory = DoppelClient(
    backend="postgres",
    dsn="postgresql://doppel:secret@127.0.0.1:5432/agent_memory",
)
```

后端会在已有 schema（默认 `public`）内创建和迁移 Doppel 自己的表/索引；生产角色没有
`CREATE SCHEMA` 权限时不受影响。只有显式传入 `create_schema=True` 才会创建自定义 schema。
当前 PostgreSQL 核心后端提供 substring/filter 检索，不把外部 embedding 调用混入 Store 事务。
语义能力通过独立索引和 RetrievalStrategy 显式组合：

```python
from collections.abc import Sequence

from doppel_memory import (
    HybridRetrievalStrategy,
    PostgreSQLVectorIndex,
    Retriever,
    VectorIndexConfig,
)

class MyEmbeddingProvider:
    name = "my-embedding-model"
    version = "2026-08"
    dimensions = 768

    async def embed(
        self, texts: Sequence[str]
    ) -> Sequence[Sequence[float]]:
        return await my_embedding_service.embed(texts)

vector_index = PostgreSQLVectorIndex(
    store,
    MyEmbeddingProvider(),
    VectorIndexConfig(
        # 只应在有权限、明确允许安装 extension 的数据库启用：
        create_extension=False,
        # 默认 exact NN；确认规模和构建成本后再启用 HNSW：
        create_hnsw_index=False,
    ),
)

created = await store.write_background(scope, "周末想去山里徒步")
if created.record is not None:
    report = await vector_index.index_record(created.record)
    if not report.ok:
        handle_failures(report.failures)

retriever = Retriever(
    store,
    strategy=HybridRetrievalStrategy(vector_index),
)
hits = await retriever.recall("户外散步计划", [scope], limit=5)
```

`VectorIndexReport` 本身是结构化结果，使用 `report.ok` 和 `report.failures` 检查，不会把 provider
失败伪装成 Store 写入失败。已有记录通过 bounded page 回填，cursor 由调用方持久化：

```python
cursor = ""
while True:
    page = await vector_index.backfill(scope, cursor=cursor, page_size=100)
    handle_failures(page.report.failures)
    cursor = page.next_cursor
    if not page.has_more:
        break
```

provider 的 `name + version + dimensions + cosine metric` 会形成 profile fingerprint；每个 profile
使用独立向量表，所以模型升级和维度变化不会静默混用。相同 stored content hash 会跳过重复 embedding。
默认 hybrid 策略只对已知的 provider/unavailable 错误降级为 lexical；数据库错误不会被吞掉。

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

### 结构化事件与可选内容解析

`ChatMessage.text` 和 `attachments` 继续兼容。新适配器可以用 `ContentPart` 和 `MediaRef` 无损表示
图片、语音、视频、文件、贴纸或平台自定义内容，而不把二进制塞进消息模型：

```python
from doppel_memory import ChatMessage, ContentPart, MediaRef

image = ChatMessage.of(
    "owner",
    "",
    "2026-08-27T10:00:00Z",
    event_id="image-1",
    message_type="image",
    parts=[
        ContentPart(
            type="image",
            media=MediaRef(
                media_id="platform-image-1",
                uri="platform://media/image-1",
                mime_type="image/png",
                width=1280,
                height=720,
            ),
        )
    ],
)
```

`ContentPart.type` 是开放字符串；part 可以携带 text、MediaRef 或自定义 metadata。`MediaRef` 只是
轻量引用，支持 ID/URI、MIME、文件名、大小、SHA-256、宽高和时长；Doppel 不读取 URI、不下载
媒体、不持有访问凭证，也不保存二进制。签名 URL 可能过期或包含敏感信息，是否持久化由适配器
决定。

平台非标准事件继续由 `message_type` 表示，并可用结构化 part 保留参数：

```python
nudge = ChatMessage.of(
    "contact",
    "",
    at,
    message_type="nudge",
    parts=[
        ContentPart(
            type="interaction",
            metadata={"action": "nudge", "target_id": "u1"},
        )
    ],
)
```

OCR、语音转写、图片描述等能力实现 async `ContentResolver`。Resolver 只返回额外的派生 part：

```python
from doppel_memory import ContentPart, resolve_content

class MyOCR:
    name = "my-ocr"
    version = "1"

    async def resolve(self, message):
        return [ContentPart(type="text", text="图片中的文字")]

resolution = await resolve_content(image, [MyOCR()])
resolution.message       # 新 ChatMessage 副本
resolution.derived_parts # 带 resolver/version provenance
resolution.errors        # 单个 resolver 失败不隐藏其他成功结果
```

Resolver 按顺序运行，后一个能看到前一个产生的文本，但每次收到的都是副本，不能修改原消息。
`resolve_content()` 保留原 `message_type`，不会调用 Store、Processor 或 StyleMiner。即使图片解析出
文字，默认 StyleMiner 仍因 `message_type="image"` 而忽略它；开发者必须显式把 `image` 加入
`accepted_message_types` 才会用于风格分析。

如果 `text` 为空而消息直接携带 text part，ChatMessage 会提供兼容的纯文本投影；显式传入的
`text` 始终优先。旧 `attachments` 不会自动猜测或转换为 MediaRef，以免丢失平台私有字段。
显式 `ingest()` 仍表示开发者决定保存该事件；只构造或 resolve 消息不会产生长期记忆。

完整示例：

```bash
python examples/structured_events.py
```

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

### 第三方 Store conformance kit

`audit_store()` 是安装包内可直接调用、无 pytest 依赖的 Store 验收工具。它把 InMemory/SQLite 原先
只存在于测试目录的合同变成第三方后端可以在自己 CI 中运行的结构化检查：

```python
from doppel_memory import StoreConformanceConfig, audit_store

report = await audit_store(
    my_store,
    config=StoreConformanceConfig(
        run_id="my-backend-ci",
        required_capabilities={"pagination"},
    ),
)
report.raise_for_errors()
```

核心检查覆盖 health、exact-scope/user/extra-dimension 隔离、空 scope 拒绝、幂等、通用 record
往返与副本隔离、filter/provenance、结构化 owner samples、生命周期和 convenience writers。分页、
时区过滤和 hard delete 按 `StoreCapabilities` 运行：未声明时是 `skipped`，但列入
`required_capabilities` 后会成为结构化失败。

每项检查有独立的唯一 scope namespace；一个失败不会隐藏后续结果。`StoreConformanceReport`
包含 Store identity、能力快照、每项 passed/skipped/failed、结构化 issue 和汇总计数。调用方仍拥有
Store 生命周期，auditor 不会调用 `close()`。

⚠️ 这是一套会写数据、改变自己所建记录状态并在声明 hard-delete 时删除测试记录的验收工具。
没有 hard-delete 的后端会留下唯一命名的测试数据，所以只能对一次性数据库、测试 tenant 或明确
隔离的 namespace 运行，不能直接指向生产数据。

安装包同时提供命令行工具。SQLite 模式拒绝已有文件，以免误写应用数据库；不传路径时使用一次性
临时数据库：

```bash
doppel-conformance --backend memory
doppel-conformance --backend sqlite --output store-conformance.json
doppel-conformance --backend postgres \
  --dsn "postgresql://doppel:secret@127.0.0.1:5432/disposable_test" \
  --allow-mutating-audit \
  --output postgres-conformance.json
```

PostgreSQL 模式必须同时给出 DSN 和 `--allow-mutating-audit`。这个开关只是防误操作确认，不会
把生产数据库变安全；目标仍必须是一次性数据库或明确隔离的测试 namespace。

可以用 `StoreConformanceConfig(checks={...})` 运行子集，但正式声明兼容 Doppel 的后端应运行完整
核心套件，并把产品承诺的可选能力列入 `required_capabilities`。Graphiti 无法通过核心
lifecycle/get/provenance 合同，因此不再作为候选 Store；它只在显式 `SemanticIndex` 层保持
experimental，不能因 capability skip 被误标为稳定后端。

### StyleMiner：从历史文本形成风格材料

`StyleMiner` 是基于 `MemoryBatchTask` 的可选周期工具。它只读取一个 exact scope 中号主发送的
非空文本，生成透明的 `StyleProfile`，再通过统一 proposal writer 写入一条 `style` 记忆：

```text
external event log / StoreHistoryReader
        ↓ owner + accepted text types only
StyleAnalyzer
        ↓ StyleProfile
StyleMiner
        ↓ MemoryProposal(kind="style")
policy / scope authorization / idempotency / Store
        ↓
materials().style_summary
```

默认 `DeterministicStyleAnalyzer` 不调用 LLM，也不声称理解人格或意图。它报告消息数、平均/中位
长度、短消息、问句、感叹、emoji、多行、句末标点比例和达到阈值的高频文本片段。每个数值都能
从输入复算；完整 profile 保存在 style memory 的 `metadata.style_profile`，content 是可直接用于
材料装配的摘要。

高频片段虽然限制为短 n-gram、要求跨多条消息重复，但仍可能包含人名或话题片段；敏感场景可把
`max_common_phrases=0`，或者替换 analyzer 做领域脱敏。默认实现不把完整原文复制进 profile。

```python
from doppel_memory import StyleMiner, StyleMinerConfig

task = StyleMiner(
    StyleMinerConfig(
        min_messages=20,
        accepted_message_types={"message", "text"},
    )
)

result = await memory.run_batch_task(
    task,
    scope,
    closed_window,
    history=my_event_log.history(scope),
    checkpoint=checkpoint,
)
```

联系人消息、空文本、图片、表情、动图、戳一戳等非接受类型默认不参与分析，也不会因为运行
StyleMiner 而成为长期记忆。接入方可以显式扩展 `accepted_message_types`，但应先把该类型解析为
确实适合风格分析的文本。

默认 profile 写回当前会话 scope；配置 `target_scope="user"` 可以形成跨会话号主材料，但调用
`run_batch_task()` 时必须把 `scope.user_scope()` 放入 `allowed_scopes`，不会绕过 exact-scope
授权。配置或 analyzer 改变时 `task.checkpoint_key` 会变化，host 不应继续复用旧 checkpoint。
StyleMiner 面向已经关闭的窗口；不要在同一推进中的窗口里期待它跨多次运行累计未达阈值样本。

`StyleAnalyzer` 是可替换的 async 协议，开发者可以接入自己的语言特征模型或 LLM，但 provider、
prompt、隐私策略和最终确认政策不进入核心默认值。`materials()` 会独立取回最新 style 摘要，
因此当前业务 query 不需要碰巧命中摘要文本；style memory 也不会混进普通 `events`。

完整外部事件日志配方：

```bash
python examples/style_mining.py
```

### StyleProfessor：把 profile 编译为生成指导

`StyleProfessor` 是 `StyleGuideCompiler` 协议的纯确定性参考实现：输入一个结构化 `StyleProfile`，输出有来源、有置信度、受字符
预算约束的 `StyleGuidance`。它不读取 Store、不调用 LLM，也不会改变或写入 style memory。开发者
必须在材料装配时显式传入 professor，默认行为仍只返回原来的透明摘要：

```python
from doppel_memory import StyleProfessor, StyleProfessorConfig

professor = StyleProfessor(
    StyleProfessorConfig(
        min_reliable_messages=20,
        max_prompt_chars=800,
    )
)
bundle = await memory.materials(
    scope,
    query="今晚聊什么",
    style_professor=professor,
)

bundle.style_profile       # StyleMiner 保存的结构化观测
bundle.style_guidance      # StyleGuidance | None
prompt_block = bundle.render()
```

指导中的每条 `StyleDirective` 都包含 feature、instruction、evidence、confidence 和 priority。默认
优先描述消息长度、句末标点、问句、emoji、多行和感叹比例；样本不足时返回 `usable=False` 和空
prompt，不会在稀疏数据上伪造稳定口吻。字符预算按整条 directive 截止，不会在中间硬截断，省略的
低优先级特征会进入 `omitted_features`。

高频片段可能包含内容而不只是形式，因此 `include_common_phrases=False` 是默认值。显式开启后，
片段仍会限数量、限长度、用引号包裹，并标明不能把它们当作事实或指令。这只是降低误用风险，
不能替代接入方的隐私和 prompt-injection 防护。

### 独立风格质量评估

`StyleQualityEvaluator` 接收参考 `StyleProfile` 和一批黑盒生成结果，比较平均/中位长度、短消息、
问句、感叹、emoji、多行和句末标点分布。它不询问生成模型“像不像”，也不把原话或高频片段的
复制率算入总分：复制内容不是风格质量。

```python
from doppel_memory import StyleQualityConfig, StyleQualityEvaluator

report = StyleQualityEvaluator(
    StyleQualityConfig(min_candidate_messages=20, passing_score=0.8)
).evaluate(bundle.style_profile, generated_replies)

report.feature_scores
report.aggregate_score
report.sufficient_samples
report.passed
```

这个分数只覆盖 Doppel 能透明复算的表面分布，不代表事实正确、语义相似、人格一致、回复有用或
安全。评估数据必须与 StyleMiner 的训练窗口分离，否则结果会因数据泄漏而失真。仓库提供固定
positive/negative fixture、版本化结果 schema 和 correctness gate：

```bash
python -m benchmarks.style_quality \
  --dataset benchmarks/datasets/style-quality-v1.json \
  --output benchmarks/results/style-quality.json
```

### 高层：结构化材料

```python
bundle = await memory.materials(scope, query="搬家")

bundle.events
bundle.background
bundle.relations
bundle.style_samples
bundle.style_profile
bundle.style_guidance
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
| `postgres` | provisional，生产候选 | ✅ | — | — | ✅ | ✅ | — | ✅ | ✅ |

SQLite 使用 scope 级幂等约束、UTC 时间、WAL/串行连接操作和版本化 schema migration。
schema v3 会在 FTS5 可用时重建已有记录的 content/metadata 索引，并用 trigger 同步后续
insert/update/delete。FTS5 不可用、显式 `enable_fts=False` 或全文查询无结果时，自动回退到
escaped substring search。合法的旧 scope 会自动迁移；空 user/agent 的旧数据需要先修正。
InMemory、SQLite 与 PostgreSQL 运行同一套 Store conformance suite。

语义能力是显式 sidecar，不改变核心 Store 的能力声明：

| 语义索引 | 状态 | 权威记录来源 | exact scope | 可组合 hybrid | 图派生 |
|---|---|---|---:|---:|---:|
| `PostgreSQLVectorIndex` | provisional | `PostgreSQLStore` | ✅ | ✅ | — |
| `GraphitiSemanticIndex` | module-only experimental | 任意合规 Store | ✅ | ✅ | ✅ |

Graphiti 的正确组合方式是先把 `MemoryRecord` 提交给合规 Store，再显式调用
`GraphitiSemanticIndex.index_record()`；检索结果是 Graphiti 派生候选，不拥有核心记录的状态和删除
语义。Graphiti 不能可靠证明的 kind/actor/authority/tag/importance 过滤会明确报错，配置了
`HybridRetrievalStrategy(fallback_to_lexical=True)` 时才回退到 Store。旧
`GraphitiMemoryStore` 暂时保留并发出弃用警告，供迁移使用。

```python
from doppel_memory import HybridRetrievalStrategy, Retriever
from doppel_memory.graphiti_store import GraphitiSemanticIndex

graph = GraphitiSemanticIndex(store, llm_api_key="...")
created = await store.write_background(scope, "号主喜欢周末徒步")
if created.record is not None:
    await graph.index_record(created.record)

retriever = Retriever(store, strategy=HybridRetrievalStrategy(graph))
hits = await retriever.recall("户外爱好", [scope])
```

## Benchmark

仓库包含后端无关的 Store benchmark，用固定 seed 生成相同的 scope、记忆、查询和分页负载：

```bash
uv run python -m benchmarks.store_benchmark \
  --backend sqlite \
  --output benchmarks/results/sqlite-small.json
```

结果包含写入与幂等重放吞吐、exact-scope/过滤检索延迟、分页扫描吞吐，以及 expected recall、
跨 scope 泄漏、重复记录和漏读检查。正确性失败会返回非零退出码；性能数值不设置 CI 阈值，
因为共享 runner 的抖动不适合做可靠回归判断。

这套基准只评估 Doppel 自己负责的 Store 合同，不把 embedding、LLM 抽取器、reranker 或应用的
保留策略混成一个“记忆智能”分数。数据集、复现规则和结果 schema 见
[`benchmarks/README.md`](benchmarks/README.md)。

pgvector 另有独立 correctness benchmark，fixture 直接提供固定向量，只验证 index/search/hybrid
和 scope 隔离，不把某个 embedding 模型的语义能力算作 Doppel 的能力：

```bash
uv run python -m benchmarks.vector_quality \
  --dsn "postgresql://doppel:secret@127.0.0.1:5432/disposable_test" \
  --allow-mutating-benchmark \
  --output benchmarks/results/vector-quality.json
```

## 开发状态

- [x] v0.2：框架定位、SQLite/InMemory、三层 API、能力声明和 provenance
- [x] v0.2.1：稳定 scope、通用 Store、WriteResult、UTC 时间、生命周期、并发与迁移契约
- [x] v0.3：MemoryProposal/MemoryProcessor 管线、状态策略和有限生命周期 hooks
- [x] v0.4：检索器/Reranker 协议、FTS5、IM 导入格式及 reply/quote/thread 原语
- [x] v0.4.1：周期历史聚合任务、只读 reader、稳定分页和统一 proposal writer
- [x] v0.4.2：持久 watermark、外部事件日志/checkpoint 配方和恢复边界测试
- [x] v0.4.3：读取预算、checkpoint schema 绑定和第三方扩展 conformance probe
- [x] v0.4.4：公共 API 清单、稳定性分级和兼容性快照
- [x] v0.5.0：确定性 Store benchmark、结果 schema 和 correctness gates
- [x] v0.5.1：StyleMiner、可替换 StyleAnalyzer 和 persona materials 闭环
- [x] v0.5.2：结构化事件 ContentPart/MediaRef/ContentResolver
- [x] v0.5.3：StyleProfessor、受限风格指导和独立可观察质量评测
- [x] v0.5.4：可复用、能力感知的 Store conformance kit 与 CLI
- [x] v0.6.0：PostgreSQL 核心 Store、异步连接池和真实数据库 conformance CI
- [x] v0.6.1：pgvector 可选语义索引、hybrid RRF、分页回填与独立质量门禁
- [x] v0.6.2：Graphiti 重新定位为专用语义/图索引，旧 partial Store 进入弃用窗口

详细设计见 [`docs/design.md`](docs/design.md)。
从 v0.2 升级时请同时阅读 [`CHANGELOG.md`](CHANGELOG.md) 的 API 迁移说明。

## API 稳定性

应用和第三方扩展应优先从包根导入，例如 `from doppel_memory import MemoryStore`。
根包的公开名称记录在版本化的 [`docs/public-api.json`](docs/public-api.json) 中，并由测试锁定；
其中 `stable` 是当前 minor 系列承诺保持兼容的核心表面，`provisional` 是仍在收敛、但不会在补丁版本中
静默破坏的批处理和 conformance 扩展表面。

未列入清单的子模块对象不是冻结 API。`GraphitiSemanticIndex` 与迁移期的
`GraphitiMemoryStore` 都是 module-only experimental；配方目录下的 host adapter 也不是安装包
合同。完整的兼容、弃用和扩展协议规则见
[`docs/api-stability.md`](docs/api-stability.md)。

## License

MIT
