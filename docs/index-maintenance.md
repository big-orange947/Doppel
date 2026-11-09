# 派生索引维护与恢复

Store 是唯一权威来源。向量和图索引通过 `IndexWriter` 维护，检索返回的候选仍需重新加载
Store，并检查 scope、权限、生命周期与时间。维护器不提供跨 Store 与外部索引的原子事务。

## 有界的两阶段维护

`IndexMaintainer.reconcile(scope, checkpoint=checkpoint, page_size=100)` 每次只处理一页：

1. `records` 扫描 Store，包括 inactive 记录。每条操作前按 exact scope 和 memory ID
   重新读取 Store；active 记录 upsert，inactive 或已硬删除的记录删除索引。
2. `entries` 扫描索引目录。重新读取 Store，删除孤儿／inactive 条目，修复过时条目。
3. 目录扫描结束后，报告 `complete=True`，返回下一周期的 records 空游标与递增 cycle。

扫描页面先校验范围、非空身份、重复项和游标进展。错误页面不会被用于索引写入。
`get` 返回的记录也必须匹配请求的 scope 和 ID。

索引操作返回后，再读一次 Store：若写入期间源记录发生变化，或删除期间源记录恢复为 active，
本页失败且不返回新的 checkpoint。维护器不在内部无限重试，也不触发自动 LLM 补图。
这些检查增加逐条 Store 读取成本；本轮没有宣称维护吞吐或检索延迟得到改善。

## host 如何保存进度

checkpoint 必须按 `(index_identity, scope_key)` 单独持久化。只有拿到非空
`report.committable_checkpoint` 才能更新保存的进度。发生失败时保留旧 checkpoint；
成功的部分操作已经发生，重试依赖 writer 的幂等合同。

典型调用顺序：

```python
report = await maintainer.reconcile(scope, checkpoint=saved_checkpoint)
if report.committable_checkpoint is not None:
    # host 自己实现的持久化；保存成功后才能推进内存中的进度。
    await checkpoints.save(report.committable_checkpoint)
else:
    # 记录 failures；保留 saved_checkpoint，稍后按 host 的策略恢复。
    record_failures(report.failures)
```

一次调用失败后，可以重新创建 runner 并加载同一份旧 checkpoint。若进度保存本身失败，也
重放旧页，不能因为索引写入已成功就猜测下一个 cursor。关闭进程后，Store、索引目录和
checkpoint 都需要各自持久化；仅保存 checkpoint 不会保存一个内存索引。

## 完成与并发的边界

`complete=True` 表示完成一轮扫描，不证明当前时刻整个索引与 Store 完全一致。
记录可能在最后检查后继续变化，因此 host 应周期性开启下一轮维护，检索端始终执行 Store 复核。

特别是：

- records 阶段已硬删除的记录不再出现在重试页中，残留索引由 entries 阶段删除。
- entries 阶段删除条目时若源记录恢复，失败后的同页重放可能已经看不到该目录条目，
  需要下一周期的 records 阶段重建。
- 最终复核能防止 inactive 记录被当作有效事实返回，但不能补回尚未建立的候选；恢复与新增
  的召回缺口仍需维护器修复。
- 多个维护实例仍需 host 协调 lease／调度。操作后的检查可以暴露部分竞争，不是分布式锁，
  也不证明多个并发 writer 已通过生产验证。

## 第三方 writer 回执要求

现有协议与 checkpoint schema 不变。维护器加强了回执检查：

- upsert 必须返回 `INDEXED` 或 `SKIPPED`，并返回与本次源快照匹配的完整 fingerprint 和
  source version；不能只返回 memory ID，或用 `MISSING` 伪装成功。
- delete 必须返回 `DELETED` 或 `MISSING`。
- 所有操作必须匹配 index identity、exact scope 和 memory ID。

缺少这些字段的自定义 adapter 需要补齐回执，否则会收到失败报告且 checkpoint 不推进。
回执检查依赖 adapter 如实报告，不等于独立读取底层向量或图来证明写入成功。

## 本轮验证范围

离线故障注入覆盖扫描后状态变化、写入期间更新／撤回／硬删除、删除期间恢复、
错误 scope／ID／分页、错误回执和失败后的重放。SQLite 测试实际关闭并重开数据库，
从文件恢复 checkpoint 与模拟索引目录，再验证过期、恢复及 superseded 的完整维护周期。
该模拟目录不是实际 PostgreSQL 或 Neo4j，不宣称已完成真实多实例／远程索引故障验收。
