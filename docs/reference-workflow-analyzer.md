# 真实 analyzer 的小样本验通

PG 工作流入口新增 `--analyzer reference --live-llm`。默认仍是 fixture 模式，不读取 LLM key。
reference 模式使用现有 `ReferencePersonalMemoryAnalyzer`，整理仍为确定性 consolidator，
embedding 仍在本地运行。这一步只导入两条合成聊天消息，不是批量历史抽取。

## 同一个 PowerShell 窗口中配置

```powershell
cd D:\project\Doppel
$workflowKey = Read-Host 'LLM API key' -AsSecureString
$env:DOPPEL_API_KEY = [System.Net.NetworkCredential]::new('', $workflowKey).Password
$env:DOPPEL_MODEL = Read-Host '模型 ID（填写渠道当前可用的准确名称）'
$env:DOPPEL_OPENAI_BASE_URL = Read-Host '兼容接口 base URL（不要包含 /chat/completions）'
```

使用支持 Chat Completions、JSON object、`max_tokens`、temperature 与 thinking disabled 的渠道。
本入口固定 `json_object`、`max_tokens=2048`、`temperature=0`、`thinking=disabled`，不自动
切换模型或修复不兼容的参数。没有实际调用即不能确认某个渠道当前支持这些参数。

还需在同一窗口配置 `DOPPEL_WORKFLOW_PG_DSN`。仅针对项目已有的本机测试容器，可用：

```powershell
$workflowContainer = (docker inspect doppel-ablation-pgvector | ConvertFrom-Json)[0]
$workflowPgVars = @{}
foreach ($entry in $workflowContainer.Config.Env) {
    $pair = $entry -split '=', 2
    if ($pair.Count -eq 2) { $workflowPgVars[$pair[0]] = $pair[1] }
}
$workflowUser = [uri]::EscapeDataString($workflowPgVars['POSTGRES_USER'])
$workflowPassword = [uri]::EscapeDataString($workflowPgVars['POSTGRES_PASSWORD'])
$workflowDatabase = [uri]::EscapeDataString($workflowPgVars['POSTGRES_DB'])
$env:DOPPEL_WORKFLOW_PG_DSN = "postgresql://${workflowUser}:${workflowPassword}@127.0.0.1:5432/${workflowDatabase}"
```

上述变量仅保留在本机当前进程；不要打印或发送它们。其他数据库应提供自己的连接配置。
Docker 必须已经启动；工具不会启动容器、重置 schema 或修改旧实验记录。

## 首次运行

使用新的 schema 和目录，不能继续之前 fixture 任务的 journal。仓库已有可选运行环境时：

```powershell
& D:\project\.doppel-eval-cu128\Scripts\python.exe -m scripts.smoke_personal_workflow `
  --live-pg --analyzer reference --live-llm --max-llm-calls 2 `
  --schema doppel_workflow_reference_v1 `
  --directory data/examples/reference-workflow-v1 `
  --embedding-model-path C:\Users\freeze\.cache\huggingface\hub\models--BAAI--bge-small-zh-v1.5\snapshots\7999e1d3359715c523056ef9478215996d62a620 `
  --output data/doppel/reference-workflow-v1-initial.json
```

其他机器请替换 Python 和已有模型路径。命令有真实模型调用，先确认窗口内配置正确。
恢复时使用相同参数，但 `--output` 换成新的报告路径；不要删除 journal／ledger 或更换 cap。

## 调用账本与失败

目录内的 `llm-ledger.jsonl` 在请求生成前记录 reservation 并 flush/fsync。默认两次尝试上限
跨进程保留；失败不退还、不自动重试。cap、存储或模型配置漂移会拒绝复用账本。
该上限不等于价格或 token 预算，也不是平台实际扣费次数。

- 计划已保存后恢复：重放原计划，一般无需再请求 analyzer。
- reservation 保存后进程退出：计为已消耗尝试，是否到达远端未知。
- 模型已响应但计划尚未保存：可能需要再次调用，仍受剩余上限约束。
- HTTP400、超时、非法 JSON：保留账目，停止本次工作流，人工查看结果后再决定恢复。
- usage 不存在时报告 `usage_missing_calls`，不能当成免费或零 tokens。
- 账本尾部损坏或磁盘错误不自动清零；需要人工检查。只支持独占 writer，非多进程账本服务。

账本只存绑定摘要、序号、状态、用量与异常类型，不存 key、请求文本或响应正文。
工作流 journal 和 reference 报告则包含记忆内容，应按私有数据保存。

## 如何看结果

`passed/complete` 是运行及结构一致性结果。reference 模式不要求模型逐字复现合成答案，
也不使用 fixture 模式的固定答案断言。检查 `extracted_claims`、authority、candidate 状态与
evidence IDs，判断是否正确抽取、区分更正。没有抽出记忆仍可能完成流程，必须单独审查质量。

`llm_usage.new_calls` 为本进程尝试数，`reserved_calls` 为该账本累计数，
`observed_tokens` 为实际收到的 usage 汇总；`paid_calls=null` 表示未核对平台账单。
该测例不提供正式质量成绩。当前提交仅完成假 HTTP 验证，真实模型验通尚待本机配置。
