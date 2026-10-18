# 可选的原文片段返回

长消息不必作为一个不可分割的整体交给回答模型。Doppel 提供无损分块工具，
以及仓库内的说话者感知片段检索参考组合；不会改动原始记忆或默认召回行为。

## 与应用无关的分块工具

`doppel_memory.passages` 随 Python 包提供，不需要模型、数据库或 IM 协议。

```python
from doppel_memory.passages import TextSpanConfig, iter_text_spans

config = TextSpanConfig(max_chars=1200, overlap_chars=160)
for span in iter_text_spans(original_text, config):
    assert span.text == original_text[span.start:span.end]
```

偏移是 Python Unicode 码点下标，区间为 `[start, end)`，不是 UTF-8 字节数、
UTF-16 单元或模型 token 数。不会 `.strip()`、摘要或改写。一般优先在窗口后半段
的空白处结束，没有空白时按字符窗口切分；所有原文字段都保留，窗口可以重叠。
这保证文本还原，不保证每个片段独立完整，也不证明片段对某个问题足够。

## 带权限和来源校验的参考组合

`integrations/aml/passages.py` 是仓库内的可选接入参考，与现有
`AttributedContextRetriever` 配合；`integrations` 目前不在发布 wheel 内。
普通 `recall`、`search`、`search_evidence` 的协议及默认结果均不变。

```python
from integrations.aml.passages import (
    AttributedPassageRetriever,
    PassageRetrievalConfig,
)

passages = AttributedPassageRetriever(
    source_retriever=context_retriever,  # 已配置 exact-scope 原消息检索
    config=PassageRetrievalConfig(
        source_limit=20, max_passages=80,
        max_chars=1200, overlap_chars=160,
    ),
    reranker=optional_reranker,  # 现有 Reranker 协议；也可省略
)
result = await passages.search(scope, question, limit=20)
for passage in result.passages:
    original = await passages.resolve_original(scope, passage)
    assert original[passage.start:passage.end] == passage.text
```

流程是授权原消息召回 → 原文重新校验 → 轮转生成有上限的片段 → 可选片段重排 →
来源再次校验。轮转使前面的长消息不会在生成阶段独占全部片段名额；没有用问题、
答案或主题规则决定切分位置。达到候选上限时 `candidate_budget_exhausted` 会明确标记，
尾部片段可能没进入候选，不能宣称全文都被重排。

每条返回保留原始 `memory_id`、`evidence_id`、scope、actor、authority、role、时间、
会话与消息位置，另外带唯一 `passage_id`、原文 SHA-256、原文长度和区间。
同一原消息的多个片段可有相同 `memory_id`，但 `passage_id` 不同；片段级引用应使用
`passage_id`，再沿 `memory_id` 回源。历史助手片段仍是 `agent_output`，不是主人事实。

重排器只能决定顺序，不能注入新片段、跨 scope、改写文本或提升 authority。
重排等待期间被撤销或修改的原消息不返回。`resolve_original` 同样检查当前状态、
来源映射、原文哈希和区间，不保证返回已被修改或删除的历史版本。

## 预算与评测边界

片段候选和原消息候选不是同一个成本单位，神经重排可能增加本地计算。
字符窗口也不是上下文字节预算；应用仍须把来源元数据一起计入上下文预算。
当前不负责 Agent 的全局上下文管理、自动补齐省略段、跨 scope 授权或存储迁移。

评测片段时，仅仅引用了带标注的原消息 ID 不能证明包含答案依据。应检查实际片段
内容与答案质量，并区分来源可追溯、引用合法和语义支持。已打开题目的诊断成绩
不能代替新题测试或正式 LongMemEval/AML 成绩。
