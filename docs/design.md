# Doppel 设计说明

> v0.2.1：面向 IM Agent 的 role-aware、exact-scope、backend-neutral 记忆协议。

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
7. Store 能力声明与跨后端一致性测试。

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
| 中层 | `client.ingest/ingest_messages/recall` | 标准 IM 流程和结构化结果 |
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

不支持的管理操作应抛出 `NotImplementedError`。调用方可以使用 `capabilities.require()` 做
前置检查。

## SQLite 参考语义

SQLite 是稳定参考后端：

- 单连接操作由 async lock 串行化，避免跨线程并发使用同一连接；
- 文件数据库开启 WAL 和 busy timeout；
- 幂等唯一索引包含 `scope_key`；
- 所有 extra dimensions 持久化；
- schema 使用 `doppel_meta.schema_version` 迁移；
- v0.2 schema 在打开时迁移到 v0.2.1 schema；
- 普通 search 排除 inactive states；
- `transition` 原子检查 expected state 并递增 version。

InMemory 与 SQLite 必须通过同一份 conformance suite。Graphiti 在通过完整 suite 前保持
experimental 状态。

## v0.3 Processor 草案

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

Processor 不直接写 Store，也不决定最终确认策略。建议的 Proposal 字段：

- kind/content/scope；
- actor/authority/confidence；
- source event/message；
- processor name/version；
- proposed state；
- idempotency key；
- derived chain 和 metadata。

第一批 Processor：

1. `EventProcessor`：确定性原始事件；
2. `FactExtractor` protocol：事实候选；
3. `RelationExtractor` protocol：关系候选。

LLM 实现属于 optional adapter。第一版 hooks 只提供 `before_process`、`after_proposal`、
`before_write`、`after_write` 和 `on_error`，不建立通用中间件系统。

## 路线图

- v0.2.1：协议、SQLite 和 conformance 稳定化；
- v0.3：MemoryProposal/Processor、状态策略、有限 hooks；
- v0.4：检索器/Reranker、FTS5、IM 导入格式和消息关系原语；
- v0.5：稳定 Graphiti、PostgreSQL/pgvector、可选风格工具和 benchmark。
