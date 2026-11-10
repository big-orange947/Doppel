# 指定日期查询的时间不确定性

`as_of` 判断事实在某个时刻是否有效。observation time、当前／历史标签和事件 occurrence
time 不能自动替代 `valid_from`／`valid_to`。每条 hit 新增
`candidate_evidence.as_of_match`：

| 值 | 含义 |
|---|---|
| `not_requested` | 未指定 as_of；不代表其他时间维度已核验 |
| `validity_match` | 通过已知有效区间检查；至少有一个可解析端点 |
| `timeless` | 无有效区间，记录自身标为 timeless |
| `uncertain` | 缺少有效区间或提供的端点不可解析，无法确认指定日期 |

一个端点缺省沿用现有开放区间语义；两个端点缺省不能把 current 当作所有历史日期都成立。
分类依据 Store 字段，不独立证明这些字段或模型归一化正确。

## 保留证据，同时说明限制

过去 active historical／unknown 记录缺少有效区间时会被 as-of 过滤，而 current 记录可能
保留并得到 `valid_at_as_of` reason。现在它们都可作为不确定候选返回：

- `as_of_match="uncertain"`；
- reasons 包含 `validity_time_uncertain`，不再包含 `valid_at_as_of`；
- warnings 提示候选不能证明指定时点有效，观测时间不是有效时间。

调用方可把正文、原始证据与标记交给 Agent。框架不强制拒答，不生成答案，不用领域词
或题目规则推断日期。已知不相交的区间仍排除；无日期的 expired／superseded 记录不恢复
可见。scope、subject、authority、observation cutoff 与 planned≠actual 门禁保留。
索引时间提示不能代替 Store 字段。

## 其他字段与兼容性

`complete` 描述读取／候选发现的完整性，不是时间已确定。`ambiguous` 描述多条声明的
语义兼容性，单条记忆也可时间不确定。`effective_at` 保留旧排序坐标及 observation fallback，
不能作为有效日期证明。精确计数包含时间不确定候选时返回 `indeterminate`、`value=null`。

当前／prior／unbounded 筛选与排序不变；interval 的 occurrence uncertainty 协议不变。
不回写日期、不改排序权重，也不保证所有证据都能进入有限 top-k。

这是 provisional 模型的新增默认字段。旧输入省略它仍可读取，默认 `not_requested`；
禁止未知输出字段的消费者需要更新模型。as-of 的返回集合、reasons、warnings 和计数可能
变化，应保留旧报告／缓存，不能将旧结果解释成已执行新检查。无新根导出。
