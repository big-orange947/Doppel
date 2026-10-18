# 可选的来源感知重排

`doppel_memory.source_aware_rerank.SourceAwareReranker` 实现现有 `Reranker`
协议，可接入普通 `Retriever`、带来源的原消息检索或片段检索。
它不是 `PersonalMemoryQueryEngine.memory_reranker` 的另一种签名，默认查询不启用。

```python
from doppel_memory.source_aware_rerank import (
    SourceAwareRerankConfig,
    SourceAwareReranker,
)

reranker = SourceAwareReranker(
    provider=my_scorer,  # PersonalMemoryReranker 协议，返回不透明 ID 的 0..1 分数
    config=SourceAwareRerankConfig(
        include_metadata=True,
        diversity_weight=0.0,  # 默认关闭；实验性多样性必须显式选择权重
        max_candidates=80,
    ),
)
```

调用方必须先授权并从权威 Store 重载候选。重排器不决定 scope 授权、事实真伪、
生命周期或集合完整性，也不会把 top-k 结果变成精确计数。片段返回组合仍在排序后
检查原消息是否被修改或撤销。开启此项不会提升 `agent_output` 的证据权威。

## 两个独立开关

`include_metadata=True` 时，模型的每个候选输入是明确的 JSON：actor、speaker role、
authority、候选时间及原始正文。模型不接收 scope key、用户 ID、记忆 ID 或来源 ID。
候选时间保持原字段语义，不冒充事实有效时间，也不内置“越新越真”。
这会扩展 provider 能看到的信息，使用远程模型时需由 host 明确授权。

`diversity_weight` 控制标准 MMR 形式的排序：

```text
utility = (1 - weight) × relevance - weight × max_redundancy
```

同一 scope 下同一原消息的冗余度为 1；其他文本使用现有通用分词的 token 集合
Jaccard 相似度。每次选择当前 utility 最高者，平分时保持原顺序。降低的是
重复来源/近似文本优先级，没有“主人配额”、角色硬过滤、问题关键词、实体词典
或特定场景规则。它可能也会把有用的重复证据延后，权重需作为实验配置显式冻结。
默认权重为 0，不启用多样性。已完成的三题诊断没有支持 BGE＋元数据＋0.15 权重
组合的准确率收益；请勿把该实验配置当成推荐预设。来源数量和角色占比不是质量分数。

`include_metadata=False, diversity_weight=0.0` 是正文分数的稳定排序控制组。
返回的是原候选快照，`fact`、`raw_text`、authority、scope 和原 similarity 都不改写；
provider 分数和 MMR utility 仅用于排序，不是校准后的事实概率。

## 限制与失败

provider 必须为每个请求局部 ID 返回一个有效分数。超时、输入上限、缺失/重复/
未知 ID、非法分数、请求或模型身份被修改都会显式失败，不伪装成成功重排。
检查 `last_summary`，不要把不可用与低相关性混为一谈。

候选数、字符数、超时都有上限；MMR 是有界窗口内的贪心选择，不读取额外历史。
上游已经漏掉的消息无法凭重排补回。元数据能否提升某个模型的排序质量必须实测；
不应把存在这项能力写成已证明的准确率提升，也不默认替换现有策略。
