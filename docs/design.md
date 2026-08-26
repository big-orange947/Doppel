# Doppel 设计说明

> v0.4.3：面向 IM Agent 的 role-aware、exact-scope、backend-neutral 记忆与检索协议。

## 定位与边界

Doppel 是记忆基础库，不是 Agent runtime。它标准化 IM 事件，持久化带 actor、authority、
scope 和 provenance 的记忆，并向上层提供结构化检索材料。

核心负责：

1. `ChatMessage` IM 事件模型；
2. `MemoryScope` 精确 namespace；
3. `MemoryRecord` 通用持久化协议；
4. `WriteResult` 明确写入结果；
5. 生命周期、过滤检索和 provenance；
6. 可组合 ScopePolicy、MaterialBundle 和 renderer；
7. Store 能力声明与跨后端一致性测试；
8. 只产生提议、不绑定 LLM 的在线 MemoryProcessor 和周期 MemoryBatchTask 管线。

核心不负责回复生成、路由、发送、工具调用、平台协议、确认 UI 或统一 LLM provider。

## 不变量

### Exact scope

Store 只对调用方传入的 `scope_key` 做精确匹配。Store 不自动从会话 scope 扩展到用户、
联系人或平台 scope；层级扩展属于 `ScopePolicy`。

`scope_key` 由所有强类型字段和排序后的 `extra_dimensions` 进行 canonical JSON 编码后计算
SHA-256。`describe()` 只用于日志，不参与隔离。

所有读、状态转换和删除操作都要求显式 scope。仅凭 memory ID 不能跨 namespace 操作。

### UTC 时间

公共模型使用 timezone-aware `datetime`，进入模型时统一转换成 UTC。后端序列化格式属于实现
细节，但返回公共模型时必须恢复 UTC-aware datetime。

### 幂等

幂等键的唯一范围是：

```text
(exact scope_key, idempotency_key)
```

`write_event()` 默认将 message ID（优先）或 event ID 转换为 `event:<identity>`。自定义
Processor 应提供稳定且带领域前缀的 idempotency key。

重复写入返回 `WriteStatus.DUPLICATE` 和已有记录；失败必须返回 `FAILED` 或抛出后端定义的
异常，不能伪装为 duplicate。

### 生命周期

普通检索默认只返回 active states：`candidate` 与 `confirmed`。`rejected`、`superseded` 和
`expired` 仅在显式查询时返回。

状态转换可以携带 `expected_state`，后端必须以原子方式实现乐观并发保护。软删除等价于转换
到 `expired`；硬删除能力由 StoreCapabilities 声明。

### Provenance

每个派生记录至少保留：

- exact scope；
- memory ID；
- actor 与 authority；
- source event/message ID；
- extractor/processor 标识；
- 创建与更新时间；
- 派生 metadata。

## 三层 API

| 层 | 入口 | 职责 |
|---|---|---|
| 低层 | `store.put/get/search/transition/forget` | 完整控制和后端协议 |
| 中层 | `client.ingest/import_batch/process/run_batch_task/recall` | 标准 IM 流程、提议管线和结构化结果 |
| 高层 | `client.materials/persona_materials` | ScopePolicy、分组材料和可替换 renderer |

专用 `write_event/background/relation` 是对通用 `put(MemoryRecord)` 的便利封装，不定义封闭
的 memory kind 集合。

## StoreCapabilities

能力声明必须对应可验证行为。目前字段包括：

- `semantic_search`
- `substring_search`
- `full_text_search`
- `temporal_search`
- `graph_relations`
- `metadata_filter`
- `hard_delete`
- `transactions`
- `reranking`
- `pagination`

不支持的管理操作应抛出 `NotImplementedError`。调用方可以使用 `capabilities.require()` 做
前置检查。`scan()` 的基类实现会抛出 `NotImplementedError`，因此已有自定义 Store 不会仅因
新增该可选能力而无法实例化；只有实现稳定游标语义的后端才能声明 `pagination=True`。

## SQLite 参考语义

SQLite 是稳定参考后端：

- 单连接操作由 async lock 串行化，避免跨线程并发使用同一连接；
- 文件数据库开启 WAL 和 busy timeout；
- 幂等唯一索引包含 `scope_key`；
- 所有 extra dimensions 持久化；
- schema 使用 `doppel_meta.schema_version` 迁移；
- 旧 schema 在打开时迁移到 schema v3；
- FTS5 可用时索引 content/metadata，以 external-content trigger 同步增删改；
- FTS5 不可用、显式关闭或无命中时保留 escaped LIKE fallback；
- 普通 search 排除 inactive states；
- `transition` 原子检查 expected state 并递增 version。

InMemory 与 SQLite 必须通过同一份 conformance suite。Graphiti 在通过完整 suite 前保持
experimental 状态。

## v0.3 Processor 协议

v0.3 在稳定 Store 协议之上增加纯提议管线：

```text
ChatMessage
    ↓
MemoryProcessor[]
    ↓
MemoryProposal[]
    ↓
validation / policy / deduplication
    ↓
MemoryRecord
    ↓
Store.put()
```

Processor 不直接写 Store，也不决定最终确认策略。`MemoryProposal` 包含：

- kind/content/scope；
- actor/authority/confidence；
- source event/message；
- processor name/version；
- proposed state 与 confidence；
- idempotency key；
- derived chain 和 metadata。

核心内置的 `EventProcessor` 只做确定性原始事件映射，但必须显式启用；不传 processors 的
`client.process()` 是 no-op。事实抽取、关系抽取、LLM 调用和领域
规则均实现同一个 `MemoryProcessor` protocol，属于开发者或 optional adapter，不进入核心
默认决策。

`ProposalPolicy.evaluate()` 返回原 proposal、修改后的 proposal 或 `None`。默认
`PassThroughProposalPolicy` 不应用置信度阈值，也不更改 proposed state。

Pipeline 默认只允许 proposal 写入调用时的 exact scope。将会话事实提升到 user scope 等操作，
必须通过 `allowed_scopes` 提供精确授权。单次运行内相同 `(scope_key, idempotency_key)` 的
proposal 在写 Store 前去重；跨运行幂等仍由 Store 保证。

第一版 hooks 固定为 `before_process`、`after_proposal`、`before_write`、`after_write` 和
`on_error`，不建立通用中间件系统。扩展错误进入 `ProcessingError`；已经成功的 Store 写入
不会因为后置 hook 失败而被改写为失败。

## v0.4.1 周期历史聚合

在线 Processor 保持无状态协议：

```text
process(scope, message) -> proposals
```

需要跨消息统计的 InteractionPattern、StyleMiner 等能力属于 `MemoryBatchTask`：

```text
host scheduler / checkpoint
          ↓
BatchTaskContext
  ├─ ScopedHistoryReader (read-only, exact scope, paginated)
  └─ ScopedMemoryReader  (read-only, authorized scopes)
          ↓
MemoryBatchTask.propose()
          ↓
BatchProposalPlan(proposals, tentative checkpoint)
          ↓
ProposalWriter (policy / scope / dedup / hooks / Store.put)
          ↓
BatchRunResult(committable checkpoint only on a clean run)
```

`MemoryProcessor` 和 `MemoryBatchTask` 都不能直接写 Store。共同的 `ProposalWriter` 是唯一提案
落库路径，执行重新校验、exact-scope 授权、单批去重、policy、hooks 和 Store 幂等写入。

`MemoryStore.scan()` 只扫描一个 exact scope，按 `(created_at, memory_id)` 升序并返回 opaque
cursor；稳定后端必须通过相同分页契约。StoreHistoryReader 用它恢复 event 为 ChatMessage。
应用也可以提供自定义 ScopedHistoryReader，从独立事件日志读取无需长期保存的表情、动图、
戳一戳等瞬时事件。

cursor 是“本页最后已读记录”的持久 watermark，最终非空页也必须返回 cursor；`has_more`
只表示当前是否需要继续翻页。读取到空增量时返回输入 cursor，从而避免 host 把已有 checkpoint
清空。watermark 只向前移动，不提供 snapshot 或迟到事件检测：排序位置早于 cursor 的晚到事件
不会被后续扫描看到。生产 host 必须按源数据特征选择处理延迟、回看窗口或源端 high watermark，
并保持同一 checkpoint 前后的过滤条件一致。
Host checkpoint key 应绑定 task name、version 和影响历史选择的配置摘要；task 语义或 filters
变化时必须换 key，不能把旧 watermark 解释成新任务的处理进度。

Doppel 不内置 scheduler、分布式锁或 checkpoint 数据库。Host 为每次运行指定时间窗口与旧
checkpoint，并且只能在 `BatchRunResult.committable_checkpoint` 非空时推进进度。任务异常、
proposal 越权、写入失败或 hook 错误都不会释放新 checkpoint；Store 的 idempotency key 保证
安全重试。

## v0.4.2 Host 配方

`examples/batch_runtime.py` 提供两个不进入核心 API 的参考 adapter：

- `SQLiteEventLog`/`SQLiteEventHistoryReader`：以 exact scope 隔离瞬时 IM 事件，cursor 额外
  绑定 scope，task 只获得只读 reader；
- `SQLiteCheckpointStore`：按 `(task_key, scope_key)` 原子 upsert host-owned checkpoint。

`examples/periodic_memory.py` 展示多页读取、互动阈值、聚合 proposal、checkpoint 提交和空增量
重试。它们是可复制配方，不是 Doppel 对“哪些事件值得记忆”的默认判断，也不会随 wheel 作为
核心包 API 安装。

## v0.4.3 扩展安全与 conformance

`BatchTaskRunner` 在 task 与任意 `ScopedHistoryReader` 之间放置 `GuardedHistoryReader`。默认
`BatchReadLimits` 为 100 页、50,000 条消息、单页 2,000 条，调用方可以逐任务覆盖。Guard
重新验证第三方 `HistoryPage`，并强制以下不变量：

- reader 返回条数不得超过请求 limit；
- 非空页必须提供 durable cursor；
- 任意非空页（包括最终页）都必须推进 cursor，`has_more=True` 还必须同时有消息；
- 超过页数、实际消息数或单页请求预算立即终止 proposal 阶段。

`BatchRunResult.history_pages_read/history_messages_read` 暴露实际消耗。预算或 reader 协议错误
记录为 `history_read`，不提交 checkpoint；task 尚未返回 plan，因此没有 proposal 可以落库。

`BatchCheckpoint` 携带 `task_name`、`task_version` 与 `schema_version`。Runner 对旧 schema 1、
identity 为空的 checkpoint 自动绑定；已绑定 identity、task version 或 schema 不匹配时要求 host
迁移或重置。任务通过可选 `checkpoint_schema_version` 声明状态结构版本，默认 1。任务输出的
checkpoint 在 proposal 写入前验证并绑定，错误输出不会产生部分写入。

`audit_history_reader()` 与 `audit_batch_task()` 是不依赖 pytest 的 conformance probes。前者在
静止 fixture 上遍历分页，检查 oldest-first 顺序、跨页非空 identity 去重并验证最终 exhausted
read；后者只运行 task 的 proposal 阶段，验证读取预算、checkpoint 和 proposal scope，不调用
ProposalWriter。Report 提供结构化 issues、`ok` 和 `raise_for_errors()`，方便第三方后端在自己的
CI 中使用。

## v0.4 检索组合

Store 的 `search()` 仍是后端合同，不承担所有召回算法。`RetrievalStrategy.search()` 负责产生
候选，默认 `StoreRetrievalStrategy` 转发到 Store；`Reranker.rerank()` 只重排或过滤候选。

当启用 Reranker 时，Retriever 按 `limit * candidate_multiplier` 获取候选。strategy 输出后和
reranker 输出后都执行相同的 exact-scope guard，并按 memory ID（无 ID 时按来源与内容）稳定
去重。scope 为空或不在调用白名单的结果不能进入最终召回，即使它由自定义扩展点注入。

SQLite FTS5 使用安全生成的 quoted token `AND` 查询和 BM25 排序。FTS rank 映射为单调的
`RecallResult.similarity`，方便后续 Reranker 组合。FTS 是 Store 候选实现细节，不改变
RetrievalStrategy/Reranker 的公共协议。

## v0.4 IM 导入格式

`IMImportBatch` 表示一个导出页或批次，`IMImportItem` 将标准化 `ChatMessage` 与 exact
`MemoryScope` 绑定。批次可以包含多个会话，`client.import_batch()` 逐条复用普通事件幂等
语义，并返回保留所有底层 `WriteResult` 的 `ImportResult`。

如果源消息没有 message/event ID，导入器使用 export source 和 item `source_id` 生成稳定 event
ID；在 source ID 也缺失但 batch ID 存在时，以 batch ID 和条目序号作为回退。批次与条目
provenance 保存在 `raw.doppel_import`。

消息 provenance 包含 sender、reply target、quoted target、thread ID、thread root、附件和
原始平台字段。thread 信息不会隐式参与 scope；需要 thread namespace 时，导入适配器必须
显式构造带 `extra_dimensions.thread_id` 的 scope。

## 路线图

- v0.2.1：协议、SQLite 和 conformance 稳定化；
- v0.3：MemoryProposal/Processor、状态策略、有限 hooks（已完成）；
- v0.4：检索器/Reranker、FTS5、IM 导入格式和消息关系原语（已完成）；
- v0.4.1：周期历史聚合、稳定分页和统一 proposal writer（已完成）；
- v0.4.2：持久 watermark、host-side event/checkpoint 配方和恢复测试（已完成）；
- v0.4.3：读取预算、checkpoint schema 绑定和扩展 conformance probe（已完成）；
- v0.5：稳定 Graphiti、PostgreSQL/pgvector、可选风格工具和 benchmark。
