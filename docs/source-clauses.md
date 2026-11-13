# 保留原话的抽取候选（实验性）

`doppel_memory.source_clauses.SourceClausePersonalMemoryAnalyzer` 是模块级可选组件，
不替换默认 analyzer，也不增加默认模型调用。将它作为普通 analyzer 交给 miner 即可：

```python
from doppel_memory.source_clauses import SourceClausePersonalMemoryAnalyzer

analyzer = SourceClausePersonalMemoryAnalyzer(model)
```

模型只提出原文断言位置、记忆类型、主题、时间状态及可选事件坐标，不输出改写后的正文、
主体身份、authority、scope 或生命周期操作。程序逐字校验断言与 evidence_id，正文保留
该 evidence 对应的整条原始消息，subject 绑定来源角色，联系人身份仍由既有门禁从 sender_id
绑定。提案仍为 candidate，不会自动成为主人确认的事实。

保留整条消息，是为了避免抽取短语时丢掉否定、引语、条件与其他人的名字。`source_clause`
元数据记录原文断言，但不代替完整上下文。原文“朋友买了设备，我还没买”仍是这整段话，
不会由此变成“主人买了设备”或“朋友没买设备”的新正文。

这不是语义证明。模型可能选错断言、漏掉有用内容，或标错主题、状态及事件类型；引用匹配
不能验证这些标签。subject 表示来源视角，不代表原文涉及的所有人和物都属于该主体。
调用方必须读取完整正文／原始证据，不应仅用该字段推断拥有者、完成状态或精确计数。
这个候选没有连续状态的有效期抽取，不解决跨批次主题对齐。事件时间仍与状态有效期分开。

代价是内容更长，单条消息中的多个属性可能重复保存全文，无法提供紧凑摘要或跨消息合并。
依赖完整多模态正文的抽取不在此候选范围内；当前输入为规范化文本。
默认单源最多 16,000 字符、最多 8 条提案，超限报错，不截断；模型调用预算与缓存由 host 管理。
无效引用或结构错误会使本次分析失败，保留原始来源，由现有工作流决定恢复，不自动修复。
不同限制和模型绑定不同版本；新建独立 journal，不复用其他 analyzer 的进度。

首轮 [冻结对照计划](../benchmarks/reports/source-clause-probe-plan-2026-11-13.md)
使用新的合成样本、真实 SQLite 和目录索引；不代表自然语言语义或检索性能已验收。
实际 [试跑结果](../benchmarks/reports/source-clause-probe-result-2026-11-13.md) 中，默认组与候选组
均在第二条消息停止；候选还出现重复全文记录和新建 Store 后的等分排序变化。保持实验性，
不作为默认推荐，也不能把原文保留率当作语义正确率。

后续增加独立的 [短断言与上下文装配候选](source-assertions.md)，用于减少全文复制并显式
记录无效注释；并非修改本版全文策略或回写上述失败结果。
