# 可恢复的个人记忆参考流程

这是 host 侧接入配方，源代码在 `examples/`，不属于安装包的稳定 API，也不是调度器。
它组合现有 `PersonalMemoryMiner`、`BatchTaskRunner`、`ConsolidationRunner` 和
`IndexMaintainer`，不新增抽取算法、不切换默认模型。

## 本地演示

在仓库根目录分两次启动：

```powershell
.\.venv\Scripts\python.exe -m examples.incremental_personal_memory --steps 1
.\.venv\Scripts\python.exe -m examples.incremental_personal_memory
```

第一次保存提案并执行写入，然后正常退出。第二次新进程从整理阶段继续，完成索引维护并查询。
这演示正常退出后的恢复；故障测试另外注入了部分写入、转换、索引及状态保存失败。

数据默认保存在 `data/examples/incremental-memory/`，可用 `--directory` 指定独立目录。
重复运行已完成窗口不会重新抽取或整理。输出包括阶段进度、active 记忆，以及查询命中的
状态、authority 和 evidence IDs。owner 自述可支持的记忆仍为 `candidate`，不自动确认。

默认 analyzer 只返回合成样例的预设结果；`SQLiteManifestIndex` 只持久化 fingerprint/version
目录，没有向量、图、语义检索或模型调用。演示不能作为自然语言抽取或召回质量成绩。
示例的更正整理保留旧、新两条来源；上层使用者仍需区分历史依据与当前声明。

## 执行与提交顺序

```text
host 写入有稳定身份的原始事件
  → miner 读取关闭的历史窗口，提出候选
  → 将提案及下一 checkpoint 保存到本地 journal
  → BatchTaskRunner / ProposalWriter 检查并幂等写入
  → 保存已完成的抽取进度
  → 生成并保存 consolidation plan
  → 执行 canonical 写入与旧记录转换
  → 保存整理进度
  → 分页维护派生索引，仅保存可提交 checkpoint
  → 返回 complete
```

每次 `PersonalMemoryWorkflow.step(window)` 执行一批抽取、一次整理或一页索引维护。
达到 miner 的消息上限时继续下一批，不能把截断当作整个窗口完成。
返回 `ok=False` 时停止推进；异常同样交给 host 处理，不在内部重试。CLI 遇到报告失败时
返回非零退出码。`--steps` 只限制本次执行步数，步数耗尽可能仍未完成。

## 中断如何恢复

提案和整理计划都在副作用发生前保存。计划保存后，部分写入失败或进程退出，下一次优先执行
保存的计划，而不是重新请求模型。成功的部分写入依靠现有幂等键重放；整理计划包含原始
source snapshots，runner 检查来源转换是否已应用。checkpoint 保存失败也不能猜测进度。

这不是外部模型调用的 exactly-once 保证：若模型已经响应、但计划尚未保存就退出，下一次
仍可能重复调用。若旧计划因源版本变化无法重放，应人工检查或显式迁移，不能删除 journal
然后偷偷重算一份新计划。

journal 绑定 workflow key、scope、miner/analyzer 配置身份、consolidator 身份与配置、runner
配置、index identity 及 host 提供的 `storage_identity`。更换这些依赖时拒绝沿用旧进度；自定义组件须如实版本化所有语义配置。
journal 含记忆正文和提案，应作为私有用户数据保存，不含密钥，也不应提交到 Git。
原始 Store、索引与 journal 必须分别持久化和备份。

## 接入实际应用

host 先完成认证、授权和原始事件落盘，再创建 `PersonalMemoryWorkflow`。将默认演示替身换为：

- `PersonalMemoryMiner(real_analyzer, ...)`，analyzer 可使用现有 reference 实现或自定义实现；
- `DeterministicMemoryConsolidator` 或有稳定版本身份的自定义 consolidator；
- 已初始化的 `PostgreSQLVectorIndex`、`GraphitiSemanticIndex` 或符合 `IndexWriter` 的索引。

本配方只允许 conversation 目标和单个 exact scope；不自动扩大到 user scope，不代替审核或
跨会话授权。更换为真实索引后，索引维护的费用、失败和延迟也是真实的，应单独验收。
真实查询仍使用现有 query/retriever 配置；目录测试替身不能直接充当语义候选源。

## 运行边界

- 只支持单 writer／单作业所有者。实例内锁和 journal 的原子替换不是跨进程 lease。
- 输入必须是关闭、按时间顺序且不重叠的窗口；新窗口在上一窗口完成后推进。窗口内原始
  事件须稳定，不能在计划执行期间修改来源。晚到且落在旧 cursor 之前的事件不会自动发现，
  需要独立 backfill 作业；线上接入应使用可靠的到达序列或明确的迟到处理策略。
- 原始事件 ID 必须稳定且不可复用为不同内容。此配方没有增加源事件冲突裁决机制。
- `complete` 是该窗口与一轮维护完成，不保证随后发生的其他写入也已同步。外部治理或
  手动修改后，还需独立调度 [IndexMaintainer](index-maintenance.md)。
- 当前配方没有自动治理、归档调度、模型请求预算、加密、分布式锁或跨存储事务。

本轮验证包含真实 SQLite 重开、独立 CLI 进程恢复和故障注入，使用合成 analyzer 与目录索引。
真实 provider、远程 PG／Neo4j 故障、多实例和 MemoEcho 在线运行仍未验收。

真实 PG＋本地 embedding 的独立入口、存储身份迁移和验证记录见
[PG 工作流验通](personal-workflow-pg.md)。该验证仍使用合成 analyzer，远程模型质量未测。
