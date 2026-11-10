# 增量接入的源消息身份检查

host 配方新增 `examples.checked_ingest.ingest_checked(store, scope, message)`。
先使用 Store 的幂等写入提交，再验证返回的记录；只有来源匹配，后续抽取才可以继续。
SQLite 示例和 PG smoke 已接入，核心 Store API 的既有重复写入语义不变。

## 重放与冲突

- 正文、actor、sender、时间、类型、回复／线程引用、附件和 parts 相同：沿用原 ID。
- 同一稳定 ID 对应不同内容或归属：抛出 `SourceEventConflictError`，host 停止后续处理。
- 不同 scope 的同名 ID 独立；inactive 原始来源不会因重放恢复。
- 缺少 message_id／event_id：先报错，不生成临时身份掩盖重复风险。

检查发生在原子幂等写入返回后，不使用先查询再写入。不同 payload 并发争用同一个 ID 时，
符合幂等合同的 Store 只保留一个，另一方发现不同的已提交来源后报冲突。依赖底层 Store
诚实执行幂等合同，不保证回滚任意自定义 adapter 的错误写入。

## 比较边界

message_id 优先作为身份；存在稳定 message_id 时允许重传 event_id 变化。raw 运输层
payload 不比较，也不覆盖初次保存的 raw，它可能带有 trace 或接收时间。
附件／parts 严格比较完整结构，含 URI；签名 URL 会变化的平台应由 host 先规范化稳定引用。
不下载附件，不自动裁决消息编辑／撤回。actor 和授权仍由可信 host 映射，比较不能认证自称 owner。
错误消息不含正文或账号信息。冲突不覆盖原记录，修改来源需明确修订协议。

## 本轮合成验证

SQLite 与 InMemory 验证重放、正文／actor／sender／时间／引用冲突、并发竞争、跨 scope
同名 ID、缺失身份、过期来源及 raw delivery 变化。

SQLite 多窗口测试执行 owner／contact／agent 消息 → 提案落盘 → 重启 → 整理和索引 →
第二批 owner 更正与 agent 输出 → 整理和索引 → owner 查询。analyzer 仅在测试中按脚本输出。
验证 agent 不成为个人事实、contact 主体独立、旧断言被替代、新候选保留原始证据，
重复运行不再抽取。这是恢复和接入检查，不是自然语言抽取或召回质量成绩。

本轮按用户选择仅用合成数据，没有导出 MemoEcho 聊天正文，也未将真实聊天发给外部模型。

21 项新增用例、74 项相关回归通过，Ruff 与相关入口类型检查通过。已有真实 PG 的合成
schema 重放也通过：五条 manifest 检查、跨 owner 零命中、相同最终记忆 ID、无新增记忆。
使用本地 BGE 做了两次查询 embedding，无付费调用。未重跑全仓或修改旧质量成绩。
本地产物：`data/doppel/personal-workflow-pg-20261110-source-guard-regression.json`。
