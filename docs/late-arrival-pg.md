# 迟到补处理：真实 PostgreSQL／pgvector 验证

`scripts.smoke_arrival_pg` 将 [ArrivalInbox](late-arrival.md) 接到真实 PostgreSQLStore、
pgvector 和已有的本地 SentenceTransformer 模型。analyzer 是脚本替身，只使用合成消息。
不读取 LLM key，不下载模型，不启动／重启 Docker，不清理已有数据库。

## 四个独立进程

1. `seed`：两个独立 scope 各写入较新的初始状态。
2. `interrupt`：给主 scope 补入更早的声明，以及已结束有效期的状态；在索引维护边界注入故障。
3. `resume`：新进程接回同一冻结批次和 index 阶段，修复索引后才确认队列，不重新抽取。
4. `replay`：队列已空，验证再次读取不修改完整 Store 记录摘要。

`interrupt` 的 `passed=true, complete=false` 表示预期故障确已触发，不能当作完整链路完成。
只有完成 `resume`、`replay` 并检查账目后，才能汇总验通结果。故障在 IndexWriter 边界，
不是实际断开 PG 网络或重启服务器。

每一阶段检查较新值仍是当前值、另一个 scope 保持独立、空 scope 无命中。迟到的有界状态
必须在有效期内的 as-of 查询命中，在当前及区间外查询中排除；as-of 命中须标记为
`validity_match`。原始消息的 `created_at` 不变。恢复后，新旧声明都须保留在当前值的证据链中。

完成阶段逐条检查 active 记录的向量 manifest fingerprint 和 inactive 条目清理情况。
真实 PG 模式还要求当前／历史最终命中实际获得 semantic 候选支持，不能只靠词法路径通过。
中断阶段允许向量不一致，但必须实际检测到不一致且队列仍未确认。

## 运行

先按 [PG 工作流配置](personal-workflow-pg.md) 设置当前终端的 `DOPPEL_WORKFLOW_PG_DSN`，
并提供已有模型目录。选择新的 `doppel_arrival_` schema 与独立目录：

```powershell
$arrivalArgs = @(
  '--live-pg', '--schema', 'doppel_arrival_example_v1',
  '--directory', 'data/examples/arrival-example-v1',
  '--embedding-model-path', 'PATH_TO_EXISTING_SENTENCE_TRANSFORMER_MODEL'
)
foreach ($stage in @('seed', 'interrupt', 'resume', 'replay')) {
  python -m scripts.smoke_arrival_pg @arrivalArgs `
    --stage $stage --output "data/doppel/arrival-example-v1-$stage.json"
  if ($LASTEXITCODE -ne 0) { break }
}
```

入口拒绝覆盖已有报告。首次要求 schema 和目录均不存在，后续要求二者及前阶段账目存在。
工作流同时绑定存储、索引和冻结历史身份；恢复时要求保留原批次及原 index 阶段。
意外失败后保留全部状态并检查，不能删除后把重跑声称为恢复。该验证入口只支持上述固定阶段，
不是通用灾难恢复调度器。测试数据、inbox、journal 和向量全部保留。

示例已结束状态使用明确提供的 `valid_from`／`valid_to`；这验证时间过滤，不验证模型能否从
自然语言推断日期。较旧主题声明按现有显式更正策略整理，不保证保留其独立旧值供任意历史问答。
来源仍为 candidate，不自动成为主人确认的事实。

实际记录见 [2026-11-11 验证报告](../benchmarks/reports/late-arrival-pg-2026-11-11.md)。
多实例、真实网络故障、Graphiti、缺失上下文的抽取质量和生产吞吐仍未在此验证。
