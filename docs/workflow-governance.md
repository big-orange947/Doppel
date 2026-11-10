# 参考工作流的可选治理阶段

`examples.personal_memory_runtime.PersonalMemoryWorkflow` 可显式接入现有治理协议：

```python
from doppel_memory import DeterministicMemoryGovernancePolicy

workflow = PersonalMemoryWorkflow(
    directory,
    workflow_key="my-governed-job-v1",
    storage_identity=storage_identity,
    store=store,
    scope=scope,
    miner=miner,
    consolidator=consolidator,
    index=index,
    governance_policy=DeterministicMemoryGovernancePolicy(),
)
```

这是 host 配方的组合能力，不新增核心规则或默认模型。默认 `governance_policy=None`，仍走
抽取 → 整理 → 索引；启用后走抽取 → 整理 → 治理 → 索引。默认关闭时保留原绑定结构和
日志字段，不会隐式启用归档。启用／停用或修改政策配置会改变绑定，不能直接复用旧任务日志。
`governance_config` 只能在显式提供 policy 时使用。

## 时间与运行方式

治理时间明确使用本轮关闭窗口的 `window.end`，不是计算机现在时间。仅重复运行已完成的同一
窗口不会推进时间；host 需要提交后续非重叠窗口。即使新窗口没有消息，miner 也不会调用
analyzer，但仍会继续整理、治理和维护索引。因此可按已知有效期归档临时状态，无需新对话。

现有确定性政策只对指定 memory types 的明确过期 `valid_to` 归档：等于治理时间时不归档，
严格早于治理时间时才归档。它不会从“最近没提过”推断失效，也不会把计划升级成经历。
政策还可能按已有证据规则强化 importance；衰减默认关闭。host 可传入自己的政策／配置。

取消与撤回仍由提案中的明确 `revision_kind` 和现有 consolidation 处理，不根据正文关键词
猜测。记忆缺少有效期时，指定日期查询按 [时间不确定性](as-of-uncertainty.md) 交付候选。

## 恢复与索引

治理计划在任何 replacement 写入／source transition 前保存，绑定 scope、政策身份、runner
配置和窗口时钟。只有执行成功才提交 checkpoint 并进入索引阶段。转换中断或最后保存进度失败，
重启后重放原计划；不重新评价政策或丢弃已成功操作。

归档保留过期快照并将旧来源 supersede，不硬删除证据。后续维护移除 inactive 索引条目。
维护完成前仍可能看到旧候选，最终 Store revalidation 继续控制可见性。这不是跨存储事务，
只有单个 host writer 的恢复语义。显式历史查询可能读到来源和归档快照，不能假定每个 hit
都是独立事实；完整去重／材料装配仍需结合 provenance。

## 合成回归覆盖

- 两窗口中的计划取消、当前事实撤回与历史更正：当前／planned 不再返回旧值，历史保留说明；
- 取消计划不新增 episode；episode-only 历史计数为零；
- 三窗口的同主题更新：每轮只返回最新当前值，保留所有原始证据；
- 临时状态在后续空窗口被归档，稳定背景仍有效，过去有效期仍可显式 as-of 查询；
- 转换失败、进度落盘失败后重启恢复，归档不重复，原治理时钟不漂移；
- 默认关闭与显式启用的任务绑定不可混用。

analyzer 是测试内的脚本替身，索引是 SQLite 目录替身。验证的是 SQLite 持久化、协议组合与
索引状态，不是自然语言理解、向量召回、真实 PG 远程故障或线上多实例验证。
本轮只使用合成数据，不导出真实聊天，不调用外部模型。

新增八项生命周期／恢复用例通过，相关定向回归 105 项通过。全仓回归 2544 passed、
33 skipped、三个 subtests 通过；Ruff 与工作流类型检查通过。仍有一个既有的第三方
Graphiti/Pydantic 弃用提示。这些数量不是性能或记忆准确率指标。
