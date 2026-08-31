# Doppel 设计说明

> v0.8.3：面向长期个人 Agent 的 provenance-aware、exact-scope、backend-neutral 记忆与上下文内核。

## 定位与边界

Doppel 是个人信息代理的记忆基础库，不是 Agent runtime。当前以 IM 事件作为第一类输入，持久化
带 actor、authority、scope、时间解释和 provenance 的个人记忆，并向上层提供结构化检索材料。
核心协议保持开放，但官方参考智能和质量门禁优先解决个人事实、状态、经历、偏好、关系、计划与
承诺，不把项目退化为通用向量数据库包装层。

核心负责：

1. `ChatMessage` IM 事件模型；
2. `MemoryScope` 精确 namespace；
3. `MemoryRecord` 通用持久化协议；
4. `WriteResult` 明确写入结果；
5. 生命周期、过滤检索和 provenance；
6. 可组合 ScopePolicy、MaterialBundle 和 renderer；
7. Store 能力声明与跨后端一致性测试；
8. 只产生提议、不绑定 LLM 的在线 MemoryProcessor 和周期 MemoryBatchTask 管线。

核心不负责回复生成、路由、发送、工具调用、平台协议、确认 UI、模型/账号选择或 API key 托管。

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

InMemory、SQLite 与 PostgreSQL 必须通过同一份 conformance suite。Graphiti 缺少核心
get/lifecycle/delete/provenance 语义，不作为 Store 接受；它位于独立的 experimental
`SemanticIndex` 层。

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

## v0.4.4 公共 API 冻结

根包 `doppel_memory.__all__` 是推荐的导入入口，并由版本化的 `docs/public-api.json` 明确分为
stable 和 provisional 两层。兼容性快照同时覆盖根导出、序列化模型字段顺序、扩展协议签名、
关键默认值、枚举值和 `MemoryStore` 抽象方法集合，避免重构时无意改变第三方实现合同。

stable 层是已收敛的核心数据模型、Store、在线 Processor、检索和材料构建协议；provisional 层
主要是新加入的批处理、只读 reader、proposal writer 和 conformance API。provisional 不是私有
API：补丁版本同样不能静默破坏它，但在下一个 minor 版本仍可随迁移说明调整。Graphiti semantic
index 与迁移期 Store adapter 继续保持 module-only experimental，不通过根包导出。

协议演进优先增加有默认实现的可选方法、可选 keyword 参数和 capability gate。给
`MemoryStore` 新增抽象方法、删除或重命名模型字段、收窄字段类型、增加必填参数、删除枚举值，
都视为破坏性变更。详细政策及 manifest 更新流程见 `docs/api-stability.md`。

## v0.5.0 可复现 Store benchmark

`benchmarks/` 是 repository-only 工具，不随 wheel 安装，也不扩大核心运行时 API。第一版用
版本化配置和固定 seed 生成相同的 MemoryScope、MemoryRecord、查询样本与分页负载，并把生成器
版本和配置哈希写入结果，避免不同数据集的数字被误作横向比较。

Runner 只评估框架能够负责的 Store 合同：初次写入、幂等重复写入、exact-scope 查询、过滤查询
和稳定分页。每类操作记录总耗时、吞吐及 nearest-rank P50/P95/P99；结果同时记录 Python、平台、
后端能力和 Doppel 版本。机器可读 envelope 由 `benchmarks/result.schema.json` 独立版本化。

性能指标只用于同环境、同数据 fingerprint 下的观察和回归分析。CI 不设置延迟或吞吐阈值，只把
缺失 expected memory、命中 forbidden memory、跨 scope 泄漏、幂等失败、分页重复或漏读视为
correctness failure。embedding、LLM Processor、Reranker 和应用保留策略属于独立质量评测，不能
混入核心 Store benchmark 后宣称为框架整体“记忆能力”。

## v0.5.1 StyleMiner

StyleMiner 复用 v0.4.1 的周期任务边界，不给在线 Processor 注入历史或 Store：

```text
ScopedHistoryReader(owner text)
        ↓
StyleAnalyzer.analyze(messages, config)
        ↓
StyleProfile | None
        ↓
StyleMiner → MemoryProposal(kind=style)
        ↓
ProposalWriter → Store → PersonaMaterialsBuilder
```

默认 DeterministicStyleAnalyzer 只产生可复算的描述统计，不绑定 LLM，也不把统计描述包装为人格、
身份或心理推断。StyleProfile schema 1 包含样本/字符数、平均和中位长度、短消息、问句、感叹、
emoji、多行、句末标点比例以及跨消息达到阈值的字符 n-gram。摘要进入 MemoryProposal.content，
完整结构进入 `metadata.style_profile`。

高频 n-gram 是可选的 observed fragment，不等于纯风格特征，可能携带重复出现的人名或话题。
隐私敏感的接入方应设置 `max_common_phrases=0` 或提供脱敏 analyzer；默认 profile 不保存完整原文。

StyleMiner 同时在 reader filter 和任务内部检查 `actor=owner`，以防第三方 reader 忽略 filter。
只有非空且 message_type 位于显式 allowlist 的消息进入 analyzer；默认 allowlist 是 `message/text`。
非文本事件可以留在外部 event log 中，但不会被分析或持久化。derived chain 只引用实际参与分析的
消息，并有可配置上限，避免大窗口生成无界 metadata。

Profile 默认写回来源会话 exact scope。可配置写入 user scope，但必须通过 BatchTaskRunner 的
`allowed_scopes` 显式授权。任务 idempotency key 绑定 source/target scope、窗口、配置 fingerprint
和 analyzer identity；host checkpoint key 同样随配置/analyzer 改变。任务以 closed window 为
语义单位，不承诺跨多次增量运行累计尚未达到 `min_messages` 的样本。

PersonaMaterialsBuilder 对 style 使用独立的空查询 + kind filter，避免当前业务 query 导致 profile
不可见；style 摘要填入 `MaterialBundle.style_summary`，style memory 不混入普通 events，来源仍
进入 provenance。第三方模型分析器实现 async `StyleAnalyzer` 即可，模型 provider、prompt、数据
出境和确认策略继续由接入方决定。

## v0.5.4 可复用 Store conformance kit

`audit_store()` 把 stable MemoryStore 的行为合同从 repository pytest mixin 提升为安装包内的
dependency-free auditor。它接收 caller-owned Store，不构造、不清空也不关闭后端；每个 check 使用
由 run ID 和 check name 组成的唯一 user/chat/memory/event namespace，避免同一次运行中相互污染。

```text
caller-owned writable Store
           ↓
 StoreConformanceConfig
           ↓
 core checks + capability-gated checks
           ↓ continue after individual failure
 StoreConformanceReport
   ├─ Store identity + capability snapshot
   ├─ passed / skipped / failed per check
   ├─ structured ConformanceIssue[]
   └─ aggregate counts + raise_for_errors()
```

核心合同检查 health、exact scope、显式 user hierarchy、extra dimensions、无 scope 拒绝、scope-local
idempotency、generic record/metadata round-trip、返回值副本隔离、组合 filters、provenance、结构化
owner samples、active-state 筛选、乐观生命周期和 convenience writers。pagination、temporal filter、
hard delete 只在对应 capability 为 true 时执行；未声明能力正常 skip，调用方通过
`required_capabilities` 声明产品承诺后，缺失能力转为失败。尚未映射到具体 check 的 required
capability 仍产生独立 capability failure，不能静默忽略。

Auditor 会写数据并改变自己创建记录的状态。hard-delete check 只删除自己创建的 record，但不支持
hard delete 的 backend 无法由通用合同安全清理剩余 fixture。因此 API 明确要求 disposable database、
test tenant 或隔离 namespace，不能对生产数据运行。CLI 的 SQLite recipe 拒绝已存在数据库；无
database 参数时创建并清理临时目录。`audit_store()` 不替调用方关闭连接，避免库函数越权管理资源。

InMemory 与 SQLite 的 pytest adapter 现在只负责提供 fixture，真正语义来自安装包里的同一 auditor。
Graphiti 即使跳过 pagination/hard-delete，也会因 stable core 的 get/lifecycle/provenance 缺口失败，
所以不能作为 Store；它只保留 module-only experimental semantic index。这份 kit 是后端进入
benchmark 之前的准入门槛；性能不能补偿 conformance failure。

## v0.5.3 StyleProfessor 与独立质量评测

StyleProfessor 是 StyleMiner 后面的显式消费层，不是第二个 miner，也不是在线 Processor：

```text
stored style MemoryRecord.metadata.style_profile
                ↓ explicit materials(style_professor=...)
          StyleProfessor.compile(profile)
                ↓ pure deterministic compilation
 StyleGuidance(directives + bounded prompt + provenance)
                ↓ host/model adapter decides how to consume
```

PersonaMaterialsBuilder 在有 Store 能力时用 recall 返回的 exact scope + memory ID 读取对应记录，验证
`metadata.style_profile` 后暴露 `MaterialBundle.style_profile`。只有调用方显式传入 StyleProfessor
才生成 `style_guidance`；否则 renderer 继续使用原 `style_summary`，保持 v0.5.1 默认行为。
Professor 不读取其他记忆、不写 Store、不调用模型，也不把指导保存成新的长期记忆。

StyleGuidance 绑定 professor/profile/config fingerprint、源 analyzer identity 和样本数。每条
StyleDirective 保留特征、指令、数值证据、样本置信度和优先级。少于
`min_reliable_messages` 时安全降级为空 prompt；prompt 预算只接受完整 directive，未容纳的低优先级
特征进入 omitted list。默认不使用 common phrases，因为它们可能承载内容、隐私或指令文本；
显式 opt-in 仍只提供有限缓解，不能构成 prompt-injection 安全边界。

StyleQualityEvaluator 与 Professor 分离，直接把黑盒生成样本的可观察统计与参考 StyleProfile
比较。v1 对平均/中位长度、短消息、问句、感叹、emoji、多行和句末标点分别给分并加权；候选数
不足时即使表面分数较高也不能 pass。common phrase overlap 刻意不计分，避免奖励复述训练内容。
这个 evaluator 不测事实、语义、身份、帮助性或安全，也不能替代人工盲测。

repository-only `benchmarks/style_quality.py` 使用独立、版本化的 positive/negative fixture 和结果
schema。CI gate 检查相似分布达到下限、对比分布低于上限、pass 判定正确，以及 Professor 输出
确实可用且不越字符预算。fixture fingerprint 防止更换数据后继续比较旧数字；真实产品评测仍应
使用严格隔离的留出对话和实际模型输出。

## v0.5.2 结构化事件

结构化事件把“平台消息能否表达”“媒体是否解析”“解析结果是否进入长期记忆”拆成三个独立决定：

```text
platform adapter
    ↓ lossless representation
ChatMessage(message_type, text, parts, raw)
    ├─ ContentPart(type, text, media, metadata)
    └─ MediaRef(identity/pointer/descriptive metadata)
              ↓ optional explicit call
        ContentResolver[]
              ↓
 ContentResolution(new message + derived parts + errors)
              ↓ host decision only
 event log / Processor / ingest / discard
```

`ContentPart.type` 与 memory kind 一样是开放 namespace。MediaRef 至少需要 `media_id` 或 `uri`，
可以保存 MIME、文件名、大小、SHA-256、宽高、时长和平台 metadata，但不包含媒体 bytes。Doppel
不会解析 URI、下载媒体或管理平台 token。`raw` 继续保存平台 envelope；legacy `attachments` 原样
兼容且不自动转换，因为框架无法可靠猜测任意字典的标识、权限和过期语义。

ChatMessage 在原有字段末尾增加 optional `parts`。旧代码构造的消息保持相同语义。仅当显式 text
为空时，非空 text parts 会去重并形成兼容 text projection；显式 text 始终优先。Store event
metadata、IMImportBatch、外部事件日志和 StoreHistoryReader 均保留 parts，因此结构化内容能跨
InMemory/SQLite 的写入、重启和 batch history round-trip。

ContentResolver 是 async whole-message 协议，返回 additional derived parts。`resolve_content()`
按顺序运行多个 resolver，给每个 resolver 一个深副本，把 resolver identity/version 写入保留的
`metadata.doppel_resolution`，并把失败转换为 ContentResolutionError。后续 resolver 能看到前面
成功产生的投影；某个 resolver 失败不回滚或隐藏其他 resolver 的成功结果。

Resolution 不调用 Store，不改变原消息，不改变 `message_type`，也不自动进入 Processor 或
StyleMiner。这保证图片 OCR 后仍是 image；要将派生文本用于风格分析，host 必须显式允许 image
类型。只构造、导入 envelope 或 resolve 都不是长期记忆决策；`ingest()` 仍是明确的事件持久化
动作，`process()` 不传 processors 仍是 no-op。

## v0.4 检索组合

Store 的 `search()` 仍是后端合同，不承担所有召回算法。`RetrievalStrategy.search()` 负责产生
候选，默认 `StoreRetrievalStrategy` 转发到 Store；`Reranker.rerank()` 只重排或过滤候选。

当启用 Reranker 时，Retriever 按 `limit * candidate_multiplier` 获取候选。strategy 输出后和
reranker 输出后都执行相同的 exact-scope guard，并按 memory ID（无 ID 时按来源与内容）稳定
去重。scope 为空或不在调用白名单的结果不能进入最终召回，即使它由自定义扩展点注入。

SQLite FTS5 使用安全生成的 quoted token `AND` 查询和 BM25 排序。FTS rank 映射为单调的
`RecallResult.similarity`，方便后续 Reranker 组合。FTS 是 Store 候选实现细节，不改变
RetrievalStrategy/Reranker 的公共协议。

## v0.6.0 PostgreSQL 核心 Store

`PostgreSQLStore` 是第一个面向共享服务部署的核心后端。它没有改变 `MemoryStore` 协议，而是用
PostgreSQL 原生机制兑现相同语义：

- asyncpg 连接池在第一次操作时创建，初始化锁保证一个 Store 实例只迁移一次；数据库 advisory
  transaction lock 让多个进程同时启动时串行执行幂等 DDL；
- `scope_key` 是所有 scoped read/write/lifecycle 操作的必备条件，拆分的 scope 字段和 JSONB extra
  dimensions 只用于无损往返，不参与模糊层级匹配；
- `(scope_key, idempotency_key)` partial unique index 在数据库层仲裁并发 replay；`memory_id`
  冲突与同 scope 幂等重复返回不同的结构化结果；
- metadata 与 extra dimensions 用 JSONB，tags 用 `text[]`，时间用 `TIMESTAMPTZ`，避免把
  PostgreSQL 降格为字符串化 SQLite；
- scan 按 `(created_at ASC, id ASC)` 读取，cursor 仍复用后端无关编码，是 forward-only durable
  watermark；
- lifecycle transition 通过带 scope 和可选 expected state 的单条 `UPDATE ... RETURNING` 完成，
  state/version/updated_at 在同一事务内推进；
- schema 名只接受普通 identifier 并始终引用；默认只在已有 schema 内建表，`create_schema=True`
  才请求 schema DDL 权限。

驱动是 `postgres` extra，模块顶层不会导入 asyncpg。因此默认安装和根包导入仍不依赖数据库驱动。
当前 capability 明确限于 substring、temporal、transactions、pagination、hard delete。PostgreSQL
全文检索和 pgvector 都不是核心 Store 自动获得的能力；v0.6.1 因此把 pgvector 放在显式
SemanticIndex/RetrievalStrategy 层，`PostgreSQLStore.capabilities.semantic_search` 继续保持 false。

CI 使用一次性 PostgreSQL service 运行公共 11 项 Store audit、并发/重开测试和安装后的 CLI。
远程 CLI 额外要求 `--allow-mutating-audit`，但它只是显式确认：安全边界仍是 disposable database
或测试 namespace，不能用参数开关替代数据隔离。

## v0.6.1 pgvector 语义索引与 hybrid retrieval

向量能力是 `PostgreSQLStore` 之上的显式索引，不是 Store `put()` 的隐藏副作用。边界是：

```text
MemoryStore.put() ──成功──> authoritative MemoryRecord
                              │ 显式 index_record / bounded backfill
EmbeddingProvider ────────────┤
                              ▼
                  PostgreSQLVectorIndex
                     │ semantic candidates
Store.search() ──────┤ lexical candidates
                     ▼
            HybridRetrievalStrategy (weighted RRF)
                     ▼
              Retriever exact-scope guard
```

embedding 服务是数据库事务之外的外部系统。如果 `put()` 自动调用它，那么“数据库已提交、provider
超时”的结果无法用现有 `WriteResult` 准确表达。显式索引让核心写入结果保持真实，失败通过
`VectorIndexReport.failures` 单独重试。`backfill()` 每次只消费一个 Store scan page，并返回 durable
cursor，不在库内部创建无边界后台任务。

`EmbeddingProvider` 必须声明非空 name/version 和固定 dimensions。Doppel 将这些字段与 cosine metric
哈希成 profile；每个 profile 使用独立表，并以 core memory ID 为 FK、hard delete cascade。索引前会按
调用者给出的 exact scope 重新读取 authoritative record，content hash 未变化时不再次调用 provider。
模型升级或维度变化得到新表，可在旧 profile 仍在线时逐页回填，切换 strategy 后再由部署方清理旧表。

pgvector extension 安装和 HNSW 都默认关闭。extension 通常是数据库级运维动作；框架只有在
`create_extension=True` 时尝试 `CREATE EXTENSION`。无 HNSW 时使用 exact nearest neighbor，保证基线
recall；显式启用 HNSW 时验证 pgvector vector index 的 2,000 维上限。向量输入验证数量、维度、有限值
和非零 cosine norm，不能把 provider contract violation 写进数据库。

Hybrid 使用 weighted reciprocal-rank fusion，不混合 lexical BM25、substring 0 分和 cosine similarity
这些不同量纲的原始分数。已知 `EmbeddingProviderError`/`SemanticIndexUnavailableError` 可以按配置降级到
lexical；连接、SQL 和程序错误继续抛出。semantic SQL 自身必须带 exact scope 和全部 MemoryFilter，
融合后仍经过 Retriever 的 scope guard 和去重。

质量 fixture 使用预计算向量，在两个 scope 放置语义相同的 adversarial records，检查 semantic/hybrid
top-1、forbidden ID、scope leakage、完整索引和 content-hash replay。它只验证 Doppel 管线，不代表
真实 embedding 模型的语义质量；生产仍需用固定模型版本、领域数据和人工标注单独评估。

## v0.6.2 Graphiti 重新定位

Graphiti 的 graph episode、实体和派生 fact 适合提供语义候选，但不等价于 Doppel 的权威
`MemoryRecord`。尤其是 `get()`、scope-local 持久幂等、原样 provenance round-trip、乐观状态迁移
和删除不能通过 capability skip 变成可选。因此 v0.6.2 明确采用 sidecar 组合：

```text
conforming Store.put() ──成功──> authoritative MemoryRecord
                                  │ explicit index_record
                                  ▼
                         GraphitiSemanticIndex
                                  │ graph-derived facts
Store search candidates ──────────┤
                                  ▼
                         HybridRetrievalStrategy
                                  ▼
                         Retriever scope guard
```

Graphiti episode 使用 exact `scope_key` 作为 group ID，并由 scope + core memory ID 生成稳定 episode
UUID；episode name 保存可逆的 core memory ID 编码。查询同时把允许的 group IDs 交给 Graphiti，批量
解析 fact 的 source episodes，并用 exact scope 重新读取权威 Store。未知 group、无法恢复来源、已硬删
或默认 inactive 的核心记录都会让候选被丢弃，避免上游过滤错误或图中陈旧 fact 变成跨会话/生命周期
泄漏。返回候选使用 source core memory ID，而不是 edge UUID；edge fact 保存在 raw_text/derived chain，
使 PersonalMemoryQueryEngine 能按 `(scope, memory_id)` 回源。Graphiti edge 没有 Doppel kind、actor、
authority、tag 或 importance 的可靠一对一来源，因此这些条件全部在恢复出的 authoritative source
record 上验证，不使用模型默认值伪造匹配。

v3 temporal projection 把 evidence 中最新 observation time 作为 Graphiti reference_time，并在 episode
中显式编码 temporal status、valid_from 与 valid_to；固定 extraction instruction 要求分别映射为
valid_at/invalid_at。`TemporalSemanticIndex.search_at()` 对 current/as_of 使用 Graphiti valid_at <= T、
invalid_at > T or null、expired_at > T or null 的图过滤。Graphiti 仍只是候选层：最终时点有效性由
Store record 的区间再次判断，图中陈旧或错误的时间边不能提升事实权威。

旧 `GraphitiMemoryStore` 在迁移窗口内保留并发出 `DeprecationWarning`；移除仍需未来 minor 版本和
迁移说明。新 Graphiti 对象继续是 optional-extra、module-only experimental，不扩大默认依赖或稳定
根 API。

## v0.7.0 派生索引生命周期

`SemanticIndex` 只负责返回语义候选，不能表达写入、删除、目录枚举或恢复进度。v0.7.0 用独立的
`IndexWriter` 组合协议补齐运维面，同时保持 Store 是唯一权威来源：

```text
                         ┌──────────────── SemanticIndex.search ──> candidates
                         │
authoritative Store ─────┤
                         │
                         └── IndexMaintainer ──> IndexWriter
                               records phase       inspect/upsert/delete
                               entries phase       exact-scope catalog scan
```

一个 index entry 保存 `memory_id`、exact `scope_key`、source version 和完整记录 fingerprint。
fingerprint 是 canonical JSON `MemoryRecord` 的 SHA-256，包括 content、state、kind、actor、authority、
importance、tags、timestamps、provenance、metadata 和 record version。只做 content hash 不足以发现
Graphiti episode header、过滤材料或生命周期语义的变化。

reconciliation 是两阶段、有界且可重放的：

1. `records` 阶段用 `MemoryFilter(include_inactive=True)` oldest-first 扫描一个 Store page。active
   记录执行幂等 upsert，inactive 记录执行 exact-scope delete；
2. records 扫描结束后进入 `entries` 阶段，按 index 自身稳定 cursor 枚举同一 exact scope。每个 entry
   重新读取 Store：不存在或 inactive 时删除，fingerprint 不同时 upsert，相同时跳过；
3. entries 扫描结束后完成一个 cycle，checkpoint 回到空 cursor 的 records 阶段并递增 cycle。

checkpoint 绑定 schema、index identity 和 exact scope，不能跨 embedding profile、Graphiti adapter 或
会话复用。任一页有失败都不返回 `committable_checkpoint`；本页已经成功的操作依靠 IndexWriter 幂等
合同安全重放。Doppel 不拥有 scheduler、lease 或 checkpoint persistence，host 与 batch task 一样只在
拿到 committable checkpoint 后推进。

两阶段不是跨 Store 与 sidecar 的分布式快照。并发新增但尚未进入本轮 records page 的索引缺口会在下
一个 cycle 修复；两阶段之间的更新由 entries 阶段再次读取权威 Store 捕获。硬删除后的孤儿不依赖 core
tombstone，由 index catalog 反向发现并清除。检索路径仍执行 Store revalidation，因此清理暂时失败不会
放宽 scope 或 lifecycle 可见性。

`PostgreSQLVectorIndex` profile table schema v2 增加 scope、完整 fingerprint 和 source version。向量
外键继续 `ON DELETE CASCADE`；fingerprint 变化但 content hash 不变时只更新 manifest，避免状态变化
触发无意义 embedding。`GraphitiSemanticIndex` 使用 v3 episode name 编码 fingerprint/version，稳定
episode UUID 仍由 scope + core memory ID 生成；v1/v2 episode 会被视为旧 temporal projection，
下一次 reconciliation 会判定 stale、删除旧 episode 并重建。

## v0.7.1 中文 IM 记忆质量基线

v0.7.1 不增加默认 extractor，也不以 Store throughput、Style 指标或固定向量 correctness 代替长期
记忆质量。仓库先冻结 `doppel.memory-quality.zh.v1` 数据集和分层 runner，为后续 Reference
Intelligence 提供同一把尺子：

```text
hand-labeled Chinese IM cases
  ├─ scopes / actors / timestamps / raw messages
  ├─ future gold memories + source evidence
  └─ queries
       ├─ authorized exact scopes
       ├─ required evidence groups
       └─ forbidden message IDs
                    │
                    ▼
  no memory · recent window · raw lexical · current Doppel events
                    │
                    ▼
  evidence recall · precision · MRR · abstention · forbidden evidence
  redundancy · context characters · latency · scope leakage
```

一个 required evidence group 表示支持同一所需事实的替代来源；返回其中任一条即可覆盖该 group。这样
同一偏好被重复说三次时，系统不会为了满分被迫返回三份重复上下文。forbidden evidence 同时覆盖旧
事实、错误说话人、Agent 建议和跨用户对抗记录。候选离开 query 授权的 exact scope 时属于 runner
合同失败；同 scope 内召回旧事实或错误权威属于被记录的质量缺陷，不阻止弱基线生成报告。

四个 v1 baseline 都声明 `extracts_memories=False`、`consolidates_memories=False` 和
`generates_answers=False`。结果 envelope 同时列出 `not_yet_measured`：memory extraction、memory
consolidation、conflict resolution、answer correctness 和 LLM token cost。未来实现不能仅靠修改文字
宣传获得这些能力，必须提供相应候选/证据并在相同 fixture 或版本化后继 fixture 上度量。

数据集 fingerprint 绑定全部消息、gold、query 和参数。提交的 reference result 记录 release revision
第一次运行；其中 evidence 指标可跨环境比较，延迟只是在报告所列 Python/OS 上的观察值。CI 运行完整
四基线并把 scope leakage 作为硬门禁，但不把当前弱检索的低 recall 变成一个无法迭代的 CI 失败。

## v0.7.2 个人记忆参考智能

v0.7.2 增加第一条官方个人记忆抽取路径，但不把模型变成隐式写权限：

```text
ChatMessage[] (exact source scope)
        │
        ▼
PersonalMemoryAnalysisRequest
        │
        ▼
PersonalMemoryAnalyzer
  └─ ReferencePersonalMemoryAnalyzer
       └─ StructuredOutputModel (official compatible or custom provider)
        │
        ▼
PersonalMemoryDraft[]
  content · type · subject · temporal status · evidence IDs
        │
        ▼ trusted revalidation
known evidence · single source actor · subject binding · confidence gate
derived authority · derived target scope · stable idempotency
        │
        ▼
MemoryProposal(candidate)
        │
        ▼ existing ProposalWriter
policy · exact-scope authorization · hooks · Store
```

`PersonalMemoryDraft` 能表达开放的 personal memory type，内置建议值包括 fact、state、episode、
preference、relationship、plan 和 commitment；`MemoryTemporalStatus` 同样是开放 namespace，提供
timeless/current/historical/planned/unknown 建议值。`valid_from/valid_to` 为下一阶段时间整理保留明确
区间，但 v0.7.2 不根据它自动过期、覆盖或合并记录。

模型只能选择草稿内容、类型、subject、时间解释、置信度和 evidence IDs。它不能选择 scope、
authority、memory ID、Store 或 lifecycle action。转换层以输入消息重新解析 evidence：未知 ID、混合
说话人证据、subject 与来源 actor 不一致、伪造 owner/agent subject ID 或超量输出都会使本次处理
失败。默认只分析 owner/contact，owner 记忆提议到 user scope，contact 记忆固定留在来源会话；跨到
user scope 仍必须由 `allowed_scopes` 明确授权。所有提议默认为 candidate。

单条自包含事实使用 `PersonalMemoryExtractor`，保持 `MemoryProcessor.process(scope, message)` 无状态。
跨消息纠正、重复证据和上下文判断使用 `PersonalMemoryMiner`；它复用 `MemoryBatchTask` 的 exact-scope
只读历史、读取预算、checkpoint 和统一 ProposalWriter，不给在线 Processor 增加 Store 能力。
Miner 每次读取有 `page_size/max_messages` 双重界限，checkpoint metadata 记录 eligible message 数、
截断标志、配置 fingerprint 与 analyzer 身份。

质量实验室增加独立的 `run_memory_extraction_quality_benchmark()`。它可以把真实 analyzer 注入完整
Miner/Proposal 路径，并度量 gold evidence coverage、supported candidate precision、subject
attribution、target scope、ignored/agent evidence writes、latency 和跨用户泄漏。这里的 supported 只
表示候选引用了人工标注证据；报告明确把 semantic content correctness、整理、冲突、最终回答与模型
成本保留为未测维度，避免用证据重合冒充语义正确。

这一组根导出在 v0.7 系列标记为 provisional。`MemoryStore`、`MemoryProcessor`、`MemoryProposal`、
`MemoryBatchTask` 与现有 writer 合同没有修改。v0.7.2 当时只定义 host provider 边界；v0.8.3 增加
OpenAI-compatible HTTP 参考实现，但 API key、账号、模型选择和重试策略仍由 host 管理，核心不绑定
统一供应商 SDK。

## v0.7.3 可审计个人记忆整理

抽取和整理是两个不同的信任边界。Extractor 只从消息证据产生 candidate；Consolidator 只读取一个
exact scope 内 active、带 `personal-memory` tag 的现有记录，并返回现有 source memory ID、操作类型与
现有 canonical source ID。参考模型不拥有 Store，也不能生成 replacement content、scope、authority、
state、ID、expiry 或 deletion。

```text
full exact-scope active snapshot
        │
        ▼
MemoryConsolidator
  ├─ DeterministicMemoryConsolidator
  └─ ReferenceMemoryConsolidator(StructuredOutputModel)
        │
        ▼ trusted binding
known IDs · no overlap · actor/authority/type/subject/topic agreement
correction temporal-class gate · source version/fingerprint snapshots
        │
        ▼ serializable integrity-bound ConsolidationPlan
idempotent canonical proposal write
        │
        ▼ optimistic source transitions
candidate/confirmed → superseded
        │
        ▼
checkpoint released only when the complete plan is clean
```

Runner 必须读取完整 scope 才能做否定性判断；`max_records` 达到上限时直接失败，不用截断快照做危险
整理。plan 绑定 runner config、consolidator identity、输入 fingerprint、全部 action/proposal/source
snapshot 和 next checkpoint。执行前重新验证 plan ID；执行中重新读取每个来源的 state、version 和完整
record fingerprint，变化即停止 canonical 写入。

host 必须以 exact scope 为键提供 single-writer lease；同一 scope 上不能并发执行两个不同 plan。
replay-safe 表示同一持久化 plan 可在部分失败后恢复，不表示通用 Store 自动提供分布式串行化。

由于 Store 协议不提供跨记录事务，执行采用可恢复顺序：先写 idempotency key 绑定 decision ID 的
canonical，再把来源逐条转为 `superseded`。部分 transition 失败时不释放 checkpoint；同一 plan 重放会
识别 canonical duplicate 和已经完成的 `version + 1 / superseded` 来源，再继续剩余 transition。新记录
保留 canonical 原文、合并后的 evidence、所有 source fingerprint 与 derived chain，审计时无需相信模型
解释。

确定性策略优先避免 false merge：无 topic 的 episode 即使文本一致也不合并；不同非空 topic 永不因
文本一致而合并；纠错要求相同 subject/subject ID/type/topic 与相同 temporal status，并且只接受
`current` 或 `planned`。当前事实和未来计划不会彼此覆盖，historical/unknown 也不参与 newest-wins。
严格时间并列时保持两条记录等待更强证据。语义模型版仍受这些 runner 门禁约束。

版本化 consolidation benchmark 使用真实 InMemory Store、runner 和 deterministic consolidator，分别
报告 false/missing action、wrong canonical、scope leakage 与 latency；前四类正确性指标是 CI 硬门禁。
v0.7.3 不做 temporary expiry、计划兑现推断、episode 身份判定/旅行次数聚合或答案生成。

## v0.8.0 结构化个人记忆查询

通用 Retriever 只承诺 scope-guarded candidates，RecallResult 也不携带个人记忆的 topic、subject、
temporal status、validity interval 或 event identity。v0.8.0 因此以组合方式增加独立 query layer，
不向稳定 Store/Retriever 协议塞入个人信息代理特有语义：

    natural-language question + trusted now
            │
            ▼
    PersonalMemoryQueryPlanner
      ├─ domain-neutral temporal/count baseline
      └─ reference planner over StructuredOutputModel
            │ scope-free draft
            ▼ trusted binding
    explicit exact scopes · one user_id · authorized subject · config fingerprint
            │
            ▼
    lookup: bounded index-first candidates + authoritative exact-scope reload
    count: complete bounded active personal-memory snapshot
            │
    subject/type/topic/temporal/validity hard gates
            │
            ├─ deterministic Chinese lexical score
            └─ optional SemanticIndex scores for known authorized IDs only
            ▼
    evidence hits · ambiguity · warnings · conservative count

planner intent 是 lookup/current/history/planned/list/count/as_of。模型不能选择 scope、Store、memory
ID、生命周期或答案；plan 绑定提问时刻、全部 exact scopes、subject、过滤条件、planner identity 和 config，
执行前验证 pmq_ fingerprint。current/history/planned intent 在 planner 未提供 temporal statuses 时会
分别绑定到 current+timeless/historical/planned 硬门，避免 intent 只是标签而检索集合仍然宽泛。
多个 scope 可以属于同一个人，但一个 query 不允许跨 user ID。
contact/custom subject ID 必须由 host 显式授权。

默认 deterministic planner 只识别 current/history/planned/as_of/list/count 等封闭结构，不维护
饮食、工作、居住、宠物、颜色等领域关键词到 topic_key 的映射。领域概念留在 search_text，由
lexical/semantic retrieval 处理；固定 benchmark 文本不得反向进入查询代码。

普通查询在 SemanticIndex 可用时先并行获取有界 lexical/semantic candidates，再按 candidate 提供的
exact scope 和 memory ID 从 authoritative Store 重载；未知、孤儿、越权以及不满足当前 plan 证据资格
的 candidate 直接丢弃，因此不需要先扫描 2,000 条才能使用向量索引。owner/contact 查询在粗过滤和
最终结构门两层拒绝 agent_output；这不等于拒绝有真实人类或派生证据的 candidate。结果
complete=false，明确表示
top-k 不是完整 snapshot。semantic provider 失败时可配置回退完整 lexical scan，warning 会进入结果。

关系检索不再伪装成第二个 SemanticIndex。`RelationIndex` 只在可信 plan 提供显式
`entity_mentions` 或 `relation_hints` 时运行，接收 exact scopes、subject、可选 relation hints 与 valid_at，返回带
Edge/Episode provenance 的 memory candidates。`GraphitiRelationIndex` 绕过 Graphiti 的通用
embedding/BM25/RRF 搜索，只读取非 `DOPPEL_MEMORY_FALLBACK` 的 Entity→RELATES_TO→Entity rich
edges。显式实体优先作为锚点；仅有关系提示时，adapter 使用 host 已授权 subject 与 exact scope
派生的 scope-salted `DoppelSubject`，不会把跨 scope 的原始平台 ID 暴露或混用。自然语言 relation hints
提供软排序与分数门，不作为直接删除候选的硬 ontology 过滤。每个候选仍回
authoritative Store，并经过与 lexical/pgvector 相同的 scope、subject、authority、lifecycle、时间门。
relation score 独立进入解释与排序，不因它同时出现在向量源中而自动获得双倍语义奖励。

实体相邻不等于关系相关。若 plan 提供 relation hints，Graphiti adapter 会在 edge name 与 edge fact
中做领域无关的大小写归一化包含匹配；未命中的边仍可被观察和自定义阈值消费，但默认降为 0.2，
低于 Doppel 的 0.35 relation gate。该规则没有“书/相机/工作”等领域表，且 pgvector/lexical
仍可独立让同一记忆入选。semantic 与 relation 候选源并发执行，避免最高配置把两段 I/O 延迟相加。

count 始终使用稳定分页完整读取每个 scope；达到 max_records_per_scope 时失败，不用截断集合回答
“一共几次”。SemanticIndex 是 top-k 协议，因此不参与 exact count 的集合定义；计数只使用完整
结构/词法扫描。普通查询中，结构化条件仍是硬门禁，lexical/semantic 只能筛选或排序候选。

history/as_of 可以读取 confirmed 以及带明确有效区间的 superseded/expired 历史记录；rejected 在任何
个人事实查询中都不可见，current/lookup 不会把 inactive lifecycle 当成当前事实。as_of 使用
valid_from/valid_to，无区间的 inactive/historical/planned 不被猜测为当时有效。planned 默认
不会因为查询日期落在计划区间就被当成实际状态；只有明确 planned intent/过滤才返回计划。current 或
as-of 同 topic 出现多个不同 active 内容时全部返回并标记 ambiguous，不以 recency 掩盖未整理冲突。
范围查询用查询窗口与 `valid_from`/`valid_to` 的区间重叠判断状态是否可见，而不是要求状态的起始
时间恰好落入窗口；因此“2026 年 6 月”可以命中 1 月开始、6 月底结束的状态。

episode 计数基于 event_key 去重。同一 event 的多次提及可以保留多条 evidence record，但只计一个
key；任一匹配 episode 没有 key 时 count 为 indeterminate。这里的 exact 表示完整授权 snapshot 上
key 的精确 distinct count，event key 本身的真实语义仍依赖 evidence-bound analyzer 与质量评测。

repository-only query benchmark 固定 10 条记忆和 9 个中文问题，报告 missing/forbidden hits、intent、
count、ambiguity、scope leakage 和 latency。它明确标记为 `lexical-domain-neutral`：planner 不包含
场景词典，当前 3 个 missing evidence hit 和 1 个 over-broad hit 原样进入报告，`correctness.passed`
保持 false。CI 用显式上限冻结“不能变差”，不会把这个词法基线包装成语义质量；embedding/模型
provider 必须在独立 hybrid E2E 上验证。

## v0.8.1 个人记忆治理

治理不扩展稳定 Store，也不把可变分数原地覆盖。policy 读取一个 bounded exact-scope active
personal-memory snapshot，只能返回 source memory ID、reinforce/decay/archive 动作、目标 importance、
置信度和原因。runner 重新绑定 scope、状态、版本、完整 record fingerprint、policy/config identity 和
输入 fingerprint，生成可序列化且带 gpl_ 完整性校验的 plan：

    active personal-memory snapshot + trusted now
            │
            ▼
    MemoryGovernancePolicy (read-only decisions)
            │ trusted binding / optimistic source snapshots
            ▼
    immutable MemoryGovernancePlan
            │
            ├─ ProposalWriter: idempotent replacement snapshot
            └─ Store.transition: active source -> superseded
            ▼
    checkpoint only after every action completes

reinforce 只认可 human_self/peer_statement 的不同 evidence identity，不把 Agent 自己生成的内容当成人类
事实强化。治理快照记录 observed_evidence_count；同一批 evidence 不会在每个周期反复加分。默认上限为
0.9，importance 仍只是召回信号，不取代 authority、subject、scope 或 temporal 门禁。

archive 仅对 state/plan/commitment 且 explicit valid_to 已结束的记录生效，不推断计划已经兑现，也不对
长期 fact/preference/relationship/episode 做“长期未访问即过期”。归档写成 `expired` replacement，再把
active source 转为 `superseded`；这复用旧 Store 的既有状态和索引维护语义。archive 保留原 content、
evidence、validity interval 和 claim created_at，治理执行时间只进入 provenance，避免污染历史查询。

decay 默认关闭。启用后也只处理 host 显式标记 retention_class=ephemeral 的记录，并按 evidence/上次
decay 时间设置最小间隔和下限。低 importance 不触发自动 archive。restore 是 host-authorized 独立路径，
只接受 Doppel archive snapshot，生成新的 candidate/confirmed 记录，archive 本身保持 inactive；原
valid_to 默认保留，时间含义需要由后续新证据纠正，而不是恢复操作暗改。

和 consolidation 一样，通用 Store 没有跨记录事务，host 必须保证一个 exact scope 同时只有一个治理或
整理 plan。相同 plan 的写入和 transition 可幂等重放；checkpoint 只在所有动作成功后释放。治理质量
fixture 把 false action 作为硬错误，覆盖已结束临时状态、未来状态、老旧长期事实/偏好、默认关闭的
ephemeral decay、可信多证据强化和 Agent 输出拒绝。

## v0.8.2 显式纠正与开放冲突

`topic_key` 只说明两条 claim 属于同一可变槽位，不证明较新的 claim 一定正确。抽取草稿新增
`revision_kind=assertion|correction|retraction`；默认是 assertion。Reference analyzer 只有在绑定的
消息证据明确表达“改为”“不再”“前述有误”等修订关系时，才应输出 correction/retraction。

ConsolidationRunner 把这一点作为不可绕过的可信门禁，而不只依赖模型提示。`CORRECT` 必须满足：来源
均 active、subject/subject_id/type/topic 相同、topic 非空、temporal status 同为 current 或同为
planned、canonical 在有效时间上严格最新，并且 canonical 明确标记 correction/retraction。缺少任一
条件都会拒绝 plan；模型 consolidator 也不能用高 confidence 绕过。

同一可信 slot 中存在不相容 assertion 时，确定性策略输出 `CONFLICT`：

    active claim A ─┐
                    ├─ conflict decision ──> derived memory_conflict marker
    active claim B ─┘                         (no canonical, no source transition)

marker 使用 `FactAuthority.DERIVED_SUMMARY`、`kind=memory_conflict` 和
`tags=[memory-conflict, open]`，保存全部 source ID/version/state/fingerprint、topic、subject、原因和
consolidator/config/input identity。它故意不带 `personal-memory` tag，所以普通 recall、consolidation
和治理不会把 marker 当作用户事实。幂等 key 绑定 decision ID，同一未解决冲突重复运行不会复制 marker。

PersonalMemoryQueryEngine 另外读取 authorized exact scope 的 active conflict marker，并只在至少两条
引用来源仍然 active、且其中至少一条进入当前查询候选时返回 `PersonalMemoryConflictHit`。结果包含全部
source IDs 与实际 matched source IDs，同时强制 ambiguous。上层 Agent 应澄清或并列陈述，不得选择
marker 内容作为事实答案。

后续显式 correction supersede 相关来源后，旧 marker 因不足两条 active source 自动变为 query-inert。
v0.8.2 尚不写回 `status=closed`，避免为了清理派生标记扩张本轮的事务与治理范围；周期 compaction 可在
后续版本加入。consolidation fixture v2 同时检查 operation、canonical、来源生命周期、marker 隔离、
scope leakage 和 replay-safe 写入。

## v0.8.3 OpenAI-compatible 结构化输出

`StructuredOutputModel` 继续是 Reference analyzer、query planner 和 consolidator 共用的最小模型边界。
官方实现 `OpenAICompatibleStructuredOutputModel` 使用异步 HTTP 调用
`{base_url}/chat/completions`，不依赖供应商 SDK，也不获得 Store、scope 或生命周期写权限：

    Reference component
          │ instructions + JSON input + output schema
          ▼
    OpenAICompatibleStructuredOutputModel
          │ bounded request / private credentials
          ▼
    /chat/completions (OpenAI or compatible endpoint)
          │ refusal / finish reason / JSON envelope
          ▼
    Mapping[str, Any]
          │ component-specific Pydantic validation
          ▼
    trusted Doppel binding and runner gates

配置记录 model、base URL、schema mode、strict、timeout、请求/响应字节上限以及可选 generation 参数，
但不记录 API key。`json_schema` 是默认 wire mode；`strict_schema` 默认 false，因为 Doppel reference
schema 含默认字段和开放 metadata，不满足 strict subset 的“全部字段 required、对象关闭额外属性”约束。
这不等于信任任意 JSON：provider 要求顶层 object，Reference component 随后仍用自己的 Pydantic 模型
验证字段、枚举、时间和 extra-forbid 边界。strict-compatible 的自定义 schema 可显式打开 strict。
completion token 上限默认使用 `max_completion_tokens`；仅接受旧参数的兼容服务可显式切换为
`max_tokens`，未配置上限时两者都不会发送。

`json_object` 是兼容较旧本地服务的显式 fallback；schema 会进入 system instruction。两种模式都对
请求和响应大小设硬上限，并区分 timeout、transport、authentication、rate limit、HTTP 失败、拒绝、
content filter、length truncation、异常 finish reason、非法 envelope、非法 JSON 与非 object 内容。
错误只暴露稳定 code、status、retryable 和可解析的 Retry-After，不回显 key、prompt、响应正文或拒绝
文本。核心不自动重试，重试次数、成本预算、退避和熔断属于 host。

provider 的 version 绑定会影响生成行为的配置 fingerprint，但排除 timeout/字节上限等纯运行参数。
Reference analyzer、planner 与 consolidator 又将自身 version 绑定 provider name/version，因此切换模型、
端点或 schema mode 时，不会沿用旧 analyzer 幂等身份、query planner identity 或 consolidation
checkpoint。外部注入的 `httpx.AsyncClient` 生命周期仍归 host；provider 自建 client 可用 `aclose()`
或 async context manager 关闭。

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
- v0.4.4：公共 API 清单、稳定性分级和兼容性快照（已完成）；
- v0.5.0：确定性 Store benchmark、结果 schema 和 correctness gates（已完成）；
- v0.5.1：StyleMiner、可替换 StyleAnalyzer 和材料装配闭环（已完成）；
- v0.5.2：ContentPart/MediaRef/ContentResolver 结构化事件（已完成）；
- v0.5.3：StyleProfessor、受限风格指导和独立可观察质量评测（已完成）；
- v0.5.4：可复用、能力感知的 Store conformance kit 与安全 CLI（已完成）；
- v0.6.0：PostgreSQL 核心 Store、异步连接池和真实数据库 conformance CI（已完成）；
- v0.6.1：pgvector 可选语义索引、hybrid RRF、分页回填与质量门禁（已完成）；
- v0.6.2：Graphiti 重新定位为专用语义/图索引，旧 partial Store 进入弃用窗口（已完成）；
- v0.7.0：派生索引 IndexWriter、双阶段 reconciliation、指纹与孤儿清理（已完成）。
- v0.7.1：中文 IM 记忆质量 fixture、四类基线、分层指标和版本化报告（已完成）。
- v0.7.2：个人记忆 Reference Intelligence、模型无关结构化抽取与证据门禁（已完成）；
- v0.7.3：Memory Consolidator、重复证据合并和冲突/纠正决策（已完成）；
- v0.8.0：中文 lexical/semantic 检索质量与 query planning（已完成）；
- v0.8.1：类型感知的强化、衰减、归档和恢复（已完成）；
- v0.8.2：显式纠正证据、开放冲突标记和 query provenance（已完成）；
- v0.8.3：OpenAI-compatible reference provider 与配置/错误边界（已完成）；
- v0.9.0：最高质量个人检索、held-out/对抗评测、Graphiti 消融、通用 reranking 与拒答校准；
- v0.9.1：非破坏式 PersonalEvent envelope、跨来源个人证据和可审计 scope promotion；
- v0.10.0：Agent tools、Server/CLI/Inspector 与 PyPI 发布准备。

### v0.9 highest-quality personal retrieval

v0.9 的完整配置允许 PostgreSQL、pgvector 和 Graphiti 同时工作。`CompositeSemanticIndex` 并行调用
多个语义/时间索引，以 exact `(scope, memory_id)` 为候选身份执行 weighted RRF，并保留来源、原始
排名、来源 similarity、权重和 RRF contribution。只有已知的 provider/index unavailable 错误可以按
来源降级；意外数据库或程序错误继续抛出。所有融合候选仍由 `PersonalMemoryQueryEngine` 从权威 Store
重载，Graphiti 或 pgvector 都不能单独证明 subject、authority、lifecycle、validity 或 provenance。

current/as-of 查询通过 `TemporalSemanticIndex.search_at()` 把有效时点传给支持时间查询的来源；普通
向量来源仍执行普通 search。返回的 query hit 用 `semantic_source:<name>` reasons 暴露实际贡献来源，
使后续消融、reranking 和诊断不必把一个归一化 RRF 分数误认为跨查询可比较的语义置信度。
