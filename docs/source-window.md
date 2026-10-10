# 可选的原始消息关联窗口

独立消息的向量检索可能召回问题，却漏掉紧邻的简短回复；回复本身可能
没有问题中的实体名称。`doppel_memory.source_window` 为最高配置检索增加
可选的同源消息关联，不改变默认 `HighConfigRetrieval` 或稳定根模块 API。

```python
from doppel_memory.source_window import SourceWindowConfig, SourceWindowRetrieval

# high_config 是已配置的 HighConfigRetrieval；resolver 是宿主的源消息关联器。
retrieval = SourceWindowRetrieval(
    high_config,
    resolver,
    config=SourceWindowConfig(anchor_limit=3, neighbors_per_anchor=2),
)
result = await retrieval.query(query, authorized_scopes, now=reference_time)
```

宿主实现异步 `RawContextResolver.resolve_context(scope, anchor,
observed_until=..., limit=...)`，返回有真实回复、线程或源会话关联的
`MemoryRecord` 序列。输入不含问题或答案；不能用语义猜测代替来源关联。
群聊尤其不能把时间相邻的两个不同人的消息自动当成互相回复。

默认仅为前三条 raw 结果各取最多两条关联消息，每次关联器最多等待五秒。
窗口保留前三条锚点，随后放置去重的关联消息，再补回其余原始结果，仍
遵守原 raw 输出上限。关联消息可能挤掉低排名结果，不保证整体召回提高。
后续装配器仍应执行自己的条目与字节预算；本模块不会拼接或截断原文。

每条关联记录重新从权威 Store 读取，检查原文、版本、元数据、事件标识、
确切 scope、confirmed 状态、ingestor 来源、观察时间和角色权限。即使另一个
scope 也在本次授权列表中，关联消息也不能跨出锚点的 scope。越界抛错；
失效记录、超时或非法关联器响应可见地降级。日志不保留关联器异常原文。
关系本身的正确性仍由宿主源映射负责，Store 完整性不等于链接语义证明。

助手发言继续是 `agent_output` 原始对话，不会成为主人的事实。个人事实、
图路径、来源证据和事件聚合值不变；补回的消息不能让 indeterminate count
升级为 exact。结果单独报告 links、added/displaced IDs、失败与拒绝数。

实验状态：有独立合成控制，四个已打开案例的来源窗口对照中修复了一处
漏召回，另外三题正确性未改变；这不是泛化或盲测证明。公开评测适配器按
原始 session/turn 关联，而不是传输分块内的 turn 序号；这是单用户/助手
历史的策略，不是通用 IM 群聊策略。未宣称默认策略、盲测成绩或发布验收。
