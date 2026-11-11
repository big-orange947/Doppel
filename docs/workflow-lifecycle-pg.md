# 真实 PG 的合成生命周期验证

入口 `scripts.smoke_workflow_lifecycle` 使用 PostgreSQLStore、pgvector、本地 PyTorch BGE 和
可恢复工作流。四个合成 scope 分别验证取消、撤回、多次更新、临时状态过期。analyzer 是
脚本替身，不读取 LLM key，不访问真实聊天，不构成自然语言理解或检索质量成绩。

## 五个独立进程阶段

1. `seed`：在全新 schema／journal 中建立初始状态。
2. `interrupt`：推进第二窗口，并在临时状态归档后的索引维护边界注入错误。
3. `resume`：新进程恢复原窗口，清理旧向量，不重新抽取。
4. `update`：第三窗口继续更正一个主题，其他 scope 处理空窗口。
5. `replay`：重复已完成窗口，对比全量记录摘要和 manifest。

`interrupt` 的 `passed=true, complete=false` 表示预期故障已被实际触发，不是整个链路完成。
只有后续恢复、更新和重放都完成，才能汇总本轮结果。故障位于 IndexWriter 应用边界，
不是停数据库、真实网络断连或多实例竞争。

## 运行

先在同一窗口设置 `DOPPEL_WORKFLOW_PG_DSN`，并使用已有可选依赖环境与本地模型。
Docker 需由 host 启动。首次选择全新 `doppel_lifecycle_` schema 和新目录：

```powershell
$lifecycleArgs = @(
  '--live-pg', '--schema', 'doppel_lifecycle_example_v1',
  '--directory', 'data/examples/lifecycle-example-v1',
  '--embedding-model-path', 'PATH_TO_EXISTING_SENTENCE_TRANSFORMER_MODEL'
)
foreach ($stage in @('seed', 'interrupt', 'resume', 'update', 'replay')) {
  python -m scripts.smoke_workflow_lifecycle @lifecycleArgs `
    --stage $stage --output "data/doppel/lifecycle-example-v1-$stage.json"
  if ($LASTEXITCODE -ne 0) { break }
}
```

阶段顺序和已有窗口状态必须匹配；不会猜测进度、重建旧 schema 或覆盖旧报告。
所有合成 Store 记录、向量和 journal 都保留。意外失败后先检查现有阶段与账目，不能
删除进度然后声称是同一轮恢复。这个验通入口不负责通用灾难恢复或生产调度。

每轮逐条检查 active fingerprint 与 inactive 条目清理情况。中断阶段特意验证已有 inactive
向量仍在时，当前查询不会把它重新当作事实。恢复和重放比较全量 Store fingerprint 摘要，
不只比较一条回答文本。查询仍有本地 embedding 成本，重放并不代表零模型计算。

实际结果见 [2026-11-11 验证报告](../benchmarks/reports/workflow-lifecycle-pg-2026-11-11.md)。
