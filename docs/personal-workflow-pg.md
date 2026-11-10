# 真实 PostgreSQL／pgvector 工作流验通

`scripts.smoke_personal_workflow` 将 host 参考执行器接到真实 PostgreSQL、pgvector 和
本地 SentenceTransformer。analyzer 仍是合成替身；本入口不读取 LLM key，也不调用付费 API。

运行环境需包含 `asyncpg`、`sentence-transformers`、PyTorch 与已下载的本地模型文件。
模型只从指定目录加载，不联网下载；超出模型长度的输入报错，不能静默截断。
它使用独立的、由本地文件和编码配置绑定的向量身份，不复用旧 FastEmbed profile。

## 配置

在运行命令的同一终端安全设置 `DOPPEL_WORKFLOW_PG_DSN`。使用带明确数据库名称的
`postgresql://.../database` URL；不支持 query/fragment 或关键词形式的 DSN。
密钥不得写入命令行、报告或 Git。Docker 需由 host 启动，本工具不启动／重启容器。

选择新的 `doppel_workflow_` 前缀 schema 和独立 journal 目录。示例：

```powershell
python -m scripts.smoke_personal_workflow --live-pg `
  --schema doppel_workflow_example_v1 `
  --directory data/examples/pg-workflow-v1 `
  --embedding-model-path PATH_TO_EXISTING_SENTENCE_TRANSFORMER_MODEL `
  --steps 1 --output data/doppel/pg-workflow-initial.json

# 同一 schema／目录／模型，新进程继续；每次报告使用新路径。
python -m scripts.smoke_personal_workflow --live-pg `
  --schema doppel_workflow_example_v1 `
  --directory data/examples/pg-workflow-v1 `
  --embedding-model-path PATH_TO_EXISTING_SENTENCE_TRANSFORMER_MODEL `
  --output data/doppel/pg-workflow-restart.json
```

再次运行已完成任务仍会执行查询与 manifest 检查，但不会重做已完成的工作流阶段。
`passed=true, complete=false` 只表示本次有界步骤成功，不代表完整链路验收通过。

工具保留合成记录、schema、向量和 journal，不清库、不覆盖旧报告。schema 与 journal 的
存在状态不匹配时停止，避免把旧库当成新任务；初始化期间若发生中断，也可能进入这个状态，
需要检查，而不是自动删除或重建。首次初始化及创建 extension 需要对应数据库权限。

## 存储身份与日志迁移

`PersonalMemoryWorkflow` 新增必填 host 参数 `storage_identity`，绑定具体存储目标。
SQLite 示例使用解析后的数据库绝对路径；PG 入口使用 server／port／database／schema 的摘要。
密码轮换不改变身份。这个身份由可信 host 提供，不是框架对数据库的独立认证。

旧配方的日志未绑定存储位置，因此现在会拒绝复用。先完成或人工审核迁移旧任务，不自动清除进度。
若只想运行新的合成 SQLite 演示，可指定新的目录，并保留旧数据：

```powershell
python -m examples.incremental_personal_memory --directory data/examples/incremental-memory-v2
```

真实模型抽取、远程故障、多实例、迟到事件和实际聊天数据的质量仍需单独验收。
当前结果与限制见 [2026-11-10 验证记录](../benchmarks/reports/personal-workflow-pg-2026-11-10.md)。
