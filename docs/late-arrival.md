# 迟到消息：按到达顺序接收，保留原时间补处理

按 `(消息时间, ID)` 推进的历史游标无法发现后来新增、但时间落在游标之前的消息。
本配方增加 host 侧 `ArrivalInbox`，不改核心 Store 游标或消息时间，不回退已有主作业。

## 数据路径

```text
host 认证并确定 exact scope
  → ArrivalInbox.append：先持久化到达序号与稳定消息身份
  → reserve：冻结尚未处理的一批消息
  → ingest_checked：幂等写入原始 Store
  → 批次独立的 PersonalMemoryWorkflow
     抽取 → 整理 → 索引维护，保留原消息时间
  → 全部完成后 acknowledge 队列
```

批次基于到达序号选择，供 miner 使用的历史快照仍按原消息时间排序。同时间戳消息可以
分到不同批次而不遗漏；较旧消息后到也会成为新批次。批次 ID 绑定持久化 inbox 身份、scope、
到达行和完整 payload。新增消息不会改变已经冻结、正在执行的批次。

## 可运行的纯合成示例

```powershell
python -m examples.late_arrival --stage current
python -m examples.late_arrival --stage late --steps 1
python -m examples.late_arrival --stage late
```

先处理 11 月 2 日的新声明，再补到 11 月 1 日的旧声明，中途退出后恢复。
预期最终仍是较新的深色偏好，但保留两条原始证据。重复最后命令会发现队列已空，不再抽取。
默认目录 `data/examples/late-arrival`，可用 `--directory` 选择新的独立目录。
analyzer 是合成替身，索引只保存目录，不访问外部模型或真实聊天。

## 接入方式

`drain_once(inbox, scope, store, workflow_factory)` 每次处理一批。factory 接收 `ArrivalBatch`，
按 `batch.identity` 建立独立作业，并向 `PersonalMemoryWorkflow` 传入：

```python
history=batch.history(),
history_identity=batch.identity,
workflow_key=batch.identity,
```

其余 Store、storage_identity、miner、consolidator、index 按原参考流程配置。
自定义 history 必须携带非空身份，且与工作流 exact scope 匹配。默认不提供 history 时，
既有绑定和 StoreHistoryReader 路径保持不变。身份由可信 host 提供，并非 reader 的独立认证。

`drain_once` 的接法更严格：必须使用 `batch.history()` 返回的原生 `FrozenHistory`，
执行器在源消息写入前核对实际 reader 的 scope、批次身份和完整消息快照。只传对
`history_identity`、却换成 StoreHistoryReader 或另一份快照，会停止且保留未确认批次。
这个检查防接线错误，不是对可信 host 中任意代码的安全隔离。

补处理窗口是冻结消息的原时间跨度，不代表那个时间段的所有历史已收齐。独立批次可以
覆盖相同或更早时间范围，旧主作业的 cursor 和 checkpoint 不会被覆盖。

## 故障与边界

- 入队提交后原始 Store 不可用：批次留在队列，恢复后重放原始写入。
- 部分处理成功：重用同一批次、同一历史身份和持久化计划，不扩入新到达消息。
- 工作流完成、ack 失败：恢复时识别已完成作业，再确认队列，不重复抽取。
- 同 ID 不同内容：沿用来源冲突检查，报错，不覆盖队列或 Store。
- 重复入队、读取新／待恢复批次及确认前，复核持久化消息身份与入队时的内容指纹。
  内容损坏或指纹不匹配时停止，不把损坏消息重新冻结为可接受的新批次。既有 batch ID
  格式与 journal 绑定不变，不需重置旧队列。
- 失败不会自动跳过／dead-letter。冲突可能阻塞该 scope 的消费，需要 host 处理。
- SQLite 事务保护 append/reserve/ack，但只支持独占 consumer；不是跨进程处理 lease。
- 队列、Store、journal 分别持久化，无跨三者的原子事务。队列保留已完成 payload，
  不提供自动清理／压缩、备份或生产吞吐保证。

本地指纹是完整性检查，不是签名；同时修改内容和校验数据的写入者仍需由 host 权限控制。
冻结后另有完整 payload 的 batch ID 校验；入队内容指纹沿用来源检查对运输 raw 元数据的排除规则。

此方案必须处在消息接入口。绕过 inbox 直接写 Store，或此前已经漏掉的消息，不会自动被
发现，需显式导入队列或另行审计。未使用队列的旧时间游标仍有原来的迟到边界。

到达序号不是有效期，也不是新增的“首次获知时间”字段。补处理不将 source time 改成到达时间，
不据此自动修正事实。重叠来源的语义冲突仍由现有 consolidation／policy 处理。
这不保证模型理解迟到上下文；默认 miner 只分析冻结批次，缺少上下文时仍需质量验证。

补处理不启用工作流内治理：旧消息跨度不是当前治理时钟。host 应单独按可信当前时点调度
治理与索引维护，避免用旧窗口倒退生命周期时间。

首轮使用真实 SQLite、合成 analyzer 和目录索引，包含独立 CLI 进程恢复。没有使用真实聊天、
真实外部模型、Graphiti 到达队列联测或多实例生产验证。
后续真实 PG／pgvector 入口与范围见 [迟到补处理 PG 验证](late-arrival-pg.md)。

验证：新增 8 项测试，相关流程共 48 项通过；全量回归 2,557 passed、33 skipped、
3 subtests passed。Ruff 全仓通过，三个变更 Python 示例的 Pyright 检查无错误。
这些结果验证恢复与来源边界，不代表自然语言抽取或检索质量分数。

后续 [边界检修记录](../benchmarks/reports/late-arrival-audit-2026-11-11.md) 补充了
reader 内容绑定、队列内容校验和修复后的真实 PG 回归；首轮数字保留为当时的验证记录。
