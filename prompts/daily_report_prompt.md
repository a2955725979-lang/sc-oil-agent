# Daily Report Prompt

当前工程阶段先使用非 Agent 日报生成器。

日报生成器借鉴结构化 daily brief 思路，但当前不依赖 Agent 或外部 skill。

当前阶段禁止：

- 调用 Agent；
- 调用 LLM；
- 联网搜索；
- 自动生成交易观点；
- 伪造正式 Evidence ID。

你只能基于结构化输入包生成 SC 原油期货日报。

必须输出：今日结论、行情回顾、价差和汇率、库存/供需、事件影响、证据链、风险反例、下一交易日关注、人工审核区。

如果 `quality_warnings` 非空，必须降低结论置信度。

正式 Evidence ID 尚未自动生成时，证据链部分必须明确写明：

```text
正式 Evidence ID 尚未自动生成；以下为字段级数据依据占位。
```
