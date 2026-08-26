# Doppel 设计说明

> 面向 IM Agent 的模块化记忆框架设计（v0.2 修订，与代码同步）。

## 定位

Doppel 是面向即时通讯代理的开源记忆框架，提供说话人感知、会话隔离、关系记忆、
事件摄入、检索和人格材料组织等基础组件。

> An open-source, role-aware memory framework for IM agents.

- **IM-oriented**：原生建模说话人、会话、引用、联系人和平台，而非只接收一段文本。
- **role-aware**：每条记忆带 actor 与事实权威，AGENT 输出不会默认成为 OWNER 风格样本。
- **scoped**：检索始终显式指定 namespace，绝不越权。
- **pluggable**：存储、提取、检索、渲染全部可替换；后端能力显式声明。
- **framework**：不生产回复，不规定材料消费方式。

## 职责边界

**Doppel 负责**（记忆领域内聚）：

1. IM 消息标准化：ChatMessage（actor/message_id/event_id/时间/消息类型/回复关系/引用/附件元数据）。
2. Scope 与 namespace：可靠性隔离模型，但不替开发者决定最终检索策略
   （scope 可扩展，ScopePolicy 可注册）。
3. 记忆摄入与生命周期：单条/批量/幂等/更新/删除/过期/合并/去重/来源追踪/记忆状态。
4. 检索与过滤：scope + kind + actor + authority + 时间范围 + tags + importance + limit。
5. 结构化材料生成：MaterialBundle（events/background/relations/style_samples/provenance）
   + 可替换 renderer。
6. 后端抽象与能力声明：StoreCapabilities（semantic/temporal/graph/hard_delete/...），
   不支持的操作明确报错，而不是假装成功。

**Doppel 不负责**：Agent 对话路由、最终回答生成、工具调用、消息发送、自动发送权限、
完整短期上下文管理、具体平台协议、用户确认 UI、统一 LLM provider 管理、
强制 prompt 模板、对"怎样才算像本人"的唯一判断。

## 三层 API

| 层 | 接口 | 说明 |
| --- | --- | --- |
| 低层 | `store.search/write/forget` | 开发者完全控制 |
| 中层 | `client.ingest / ingest_messages / recall` | 标准流程 + filters 组合 |
| 高层 | `client.materials / persona_materials` + `bundle.render()` | 结构化材料 + 可替换 renderer，persona 只是 preset |

## 关键原语（与其他框架的差异化）

1. **说话人感知**：owner/contact/agent/system（可扩展自定义 actor）。
2. **事实权威**：human_self / peer_statement / agent_output / derived_summary（可替换权重）。
3. **IM scope**：owner + agent + platform + chat type + conversation + counterpart + thread
   （五元组强类型 + extra_dimensions 扩展）。
4. **关系化记忆**：RelationMemory（counterpart/relationship/address/attributes）。
5. **可溯源**：RecallResult 回到 message_id/event_id/后端记忆 ID/actor/scope/提取器/提取时间/原始内容。

## 路线图

- **v0.2（当前）**：稳定核心协议 + InMemory/SQLite + 后端契约测试 + 三层 API + provenance + 能力声明。
- **v0.3**：MemoryProcessor 管线（EventProcessor/FactExtractor/RelationExtractor 协议）
  + 确认闭环状态（candidate/confirmed/rejected/superseded/expired）+ hooks/middleware。
- **v0.4**：IM 专用能力（reply/quote/thread 关系、联系人/群关系、平台导入格式、owner 风格样本 preset）。
- **v0.5**：Graphiti 时间关系/冲突事实、StyleMiner/StyleProfessor（可选模块）、PostgreSQL/pgvector、benchmark。

## 后端契约

`tests/store_contract.py` 是后端契约测试：新后端实现 `MemoryStore` 后跑同一套断言
（scope 隔离/幂等/删除/filter/provenance/时间查询），保证社区后端行为一致。
