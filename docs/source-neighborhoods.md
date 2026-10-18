# 可选的原文邻接展开

相邻回复被检索到，不代表它前面的用户原话也进入了候选池。Doppel 提供一个可选的
只读参考组合，在最终选择或重排之前补入相邻原文；不会生成摘要、合并事实或推断关系。
默认检索路径、Store 协议和顶层导出不变。

## 顺序必须由接入方明确提供

Python 包中的 `doppel_memory.source_order` 提供：

- `SourcePosition`：scope、session、稳定原始 ordinal、memory/evidence ID。
- `SourceOrderResolver`：只读 `locate` / `neighbors` 协议，不接收查询或答案。
- `ExplicitSourceOrderIndex`：基于显式位置的内存参考实现，不是持久化索引或权限系统。

不能从时间戳、ID 字典序、角色交替或每个导入分片内的 `turn_index` 猜全局顺序。
同一时刻可以有多条消息，分片位置会重置，会话 ID 也可能在不同租户重复。宿主应
持久化并维护可靠的原始顺序；删除或空消息形成的 ordinal 缺口不自动压缩或跨越。
索引只给出位置关系，不授予读取权限；一致但错误的宿主顺序无法由框架凭空验证。

## 带来源校验的参考组合

`integrations/aml/neighborhood.py` 在仓库中提供 `AttributedNeighborhoodExpander`，
与现有 `AttributedContextRetriever` 配合。`integrations` 当前不在发布 wheel 内。

```python
from doppel_memory.source_order import ExplicitSourceOrderIndex
from integrations.aml.neighborhood import AttributedNeighborhoodExpander

# positions 来自宿主可靠的源消息索引，不包含 query/gold/evidence 标签。
order = ExplicitSourceOrderIndex(positions)
anchors = await candidate_retriever.search(scope, question, limit=80)
expanded = await AttributedNeighborhoodExpander(
    store, resolve_event=resolve_event, source_order=order,
).expand(scope, anchors.snippets)
```

组合重新校验锚点，然后请求同 scope、同 session 的显式相邻位置。回调只返回 ID/
位置，不返回可信文本。每个邻居重新读取 Store 并验证状态、原始事件、来源映射、
说话者和 authority；最后再次检查顺序与原文。模型等待或宿主回调期间失效的锚点、
修改的来源，以及失去有效锚点支持的新增邻居不作为成功结果返回。

输出保留完整原文和独立归属，不把助手回复升级为主人事实。相邻不代表同一事件，
不意味着逻辑支持，也不是图谱关系或多跳推理。原始候选顺序/相似度保留；新增邻居
的 `similarity=0` 是未单独评分的占位，不是向量相似度测量或“不相关”的概率。
`links` 单独解释由哪个锚点和哪个偏移发现了邻居。

## 固定预算与接入注意事项

默认前后各1条、最多80个锚点/240个总候选、300,000个源内容 JSON UTF-8 字节、
整体30秒超时。字节包括来源内容格式化元数据，不是完整 LLM 请求或 token 数。
锚点本身超预算会显式失败，不删除或截短锚点；新增整条邻居超过预算会跳过并在
`rejected` 中记录。数量达到上限时返回预算标志/未访问锚点数。重复来源去重；排序
为原始锚点在前，再按锚点顺序与距离/前后偏移补入，不按角色或特定问题挑邻居。
位置缺失时保留有效锚点并报告，不能编造相邻消息。

跨 scope/session、越界、过量/重复位置、位置与来源不一致或回调修改绑定参数时
显式失败；没有重试、重置或静默成功回退。Store 当前内容校验不是跨全体来源的原子
快照，也不保证一个不可信宿主本身不会读取其他数据。回调是宿主代码，须自行实现
权限、持久化、预算和运行约束；本组合本身不调用 LLM、不写 Store。

**展开必须在最终选择之前。** 若继续使用最多80候选的默认选择器，新增消息可能
再次被候选上限截掉。接入方必须显式调整选择器候选数量、检索放大系数与完整请求
字节/token 预算；不能把240条结果无提示塞进80条管线，也不能宣称额外候选免费。
扩大的普通词法/向量候选池也可能找到同样证据，评测应同时比较同条数的普通检索，
并分别报告内容字节数，而不是把扩容收益全部算给邻接机制。
