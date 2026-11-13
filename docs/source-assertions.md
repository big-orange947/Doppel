# 断言与证据上下文分离（实验性）

`doppel_memory.source_assertions.SourceAssertionPersonalMemoryAnalyzer` 是新的可选
analyzer，不替换默认 analyzer 或上一版全文保留候选。新建独立 journal 使用：

```python
from doppel_memory.source_assertions import (
    SourceAssertionPersonalMemoryAnalyzer,
    assemble_source_assertions,
)

analyzer = SourceAssertionPersonalMemoryAnalyzer(model)  # 默认 reject_batch
# 可选：逐条拒绝无效输出；必须提供同步诊断接收器，异常会中止分析。
analyzer = SourceAssertionPersonalMemoryAnalyzer(
    model, invalid_policy="isolate", diagnostics_observer=save_diagnostic,
)
```

记忆正文是来源中的唯一、连续原文片段，不是模型改写的摘要。`source_assertion` 元数据
保存 evidence_id、Python 字符偏移 start/end 和整条来源文本的 SHA-256。重复出现、无法
唯一定位的片段和带外围空白的片段会被拒绝，不自动选择位置或修改文字。
原始消息仍由既有接入口幂等写入 Store；多个短断言引用同一来源，不再各复制完整正文。
事件时间和原文引用仍需通过既有校验；不修正日期、不把事件发生区间当作状态有效期。

短片段可能缺少否定、代词或引语上下文，因此上层使用时应装配完整证据：

```python
packet = assemble_source_assertions(authorized_original_request, authoritative_records)
# packet["claims"]：各条短断言和来源引用
# packet["sources"]：按 evidence_id 去重的原始消息，全文每条只出现一次
```

调用方负责认证、读取权威记录，并提供同一 exact scope 下的原始消息。装配器不查询数据库、
不授予读取权限、不独立认证来源；它复核 scope、记录状态、角色、主体身份、来源时间、
证据引用、文本指纹及片段边界。任一不匹配整次装配失败，不返回部分材料。偏移按 Python
Unicode 字符计数，不是 UTF-8 字节位置。不能直接用它对普通非断言记录做装配。

普通 query API 仍只返回记录，不会自动调用该装配器。接入者必须按 evidence_id 加载授权
原始消息并使用装配结果，不能把短文本单独交给 Agent 后假定上下文已经齐全。
subject 仍是来源视角，不代表句中所有人物或物品属于该主体。

`isolate` 只隔离 schema、来源绑定和注释结构错误，记录原始索引与封闭原因码；不删除无效
输出中的字段再重试，也不把错误注释悄悄降级为“正确”。原始响应缓存与预算仍由 host 管理。
顶层响应损坏、超量、模型故障和诊断发布失败会中止整个分析。诊断接收器必须由 host 可靠
保存；组件不提供账本或异步诊断服务。全部条目被拒绝时可返回空提案，但不能记作质量通过。

所有标签、片段完整性和语义正确性仍未独立验证；引用逐字命中不是语义证明。新身份隔离
策略、提示词和内容表示，不应复用旧 analyzer 的进度。旧 V1 的请求、版本、全文策略保持。
模块级实验接口，没有新的 Store schema、迁移或根 API 默认变化。

[零模型调用复查记录](../benchmarks/reports/source-assertion-isolation-2026-11-13.md)
验证了保存输出的新解析行为，不是新盲测或线上质量成绩。
