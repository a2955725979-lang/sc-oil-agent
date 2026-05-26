# Auto Daily Preflight Policy

v0.6 Auto Daily Preflight 的目标是在没有人工 `daily_input` 的情况下，自动组装出最小可运行的 `daily_input_schema_v1`，并交给既有 `run_daily_pipeline.py` 完成计算、质检、快照、Evidence List、Markdown 日报和 `research_reports` 留痕。

这仍然不是最终自动化投研系统。当前阶段不接 Agent / LLM，不做联网搜索解释，不输出方向性交易建议，也不把默认文本字段当作真实研究依据。

## 字段来源

v0.6 第一阶段自动覆盖三类输入：

- AKShare SC fetcher：`SC_close`、`SC_settlement`、`SC_volume`、`SC_open_interest`、`SC_near_price`、`SC_next_price`。
- market_fx fetcher：`USD_CNY`、`Brent_close`、`WTI_close`。
- default fields：`exchange_notice`、`important_oil_news`、`manual_notes`、`OPEC_monthly_summary`、`IEA_monthly_summary`。

`EIA_crude_inventory` 暂不自动抓取。现阶段缺失库存字段时，依赖数据字典的 warning 降级规则；后续 v0.6 Step 4 再接周度库存 fetcher。

## 失败与降级策略

| 字段或类别 | 当前策略 |
| --- | --- |
| `SC_close` / AKShare 主行情 | 缺失或 fetch_status 为 fail 时，视为 controlled data failure，不生成正常日报。 |
| `USD_CNY` | 可使用最近一期，整体保留 warning，metadata 标注 stale / fallback。 |
| `Brent_close` / `WTI_close` | 可使用最近一期，整体保留 warning，metadata 标注外盘日期和 fallback。 |
| `EIA_crude_inventory` | 本阶段不自动抓取；缺失时保持 warning，不能用于强结论。 |
| 文本类字段 | 自动填默认 warning、low confidence 文本，不得用于强结论或交易判断。 |

原则是：

```text
价格核心字段缺失 -> fail
外盘 / 汇率可用最近一期 -> warning
库存可用上一期或缺失 -> warning
文本类字段默认空值 -> warning
```

## 输出约束

自动生成的最终输入必须是 `daily_input_schema_v1`。自动字段必须保留来源 metadata；默认文本字段必须写明 `source_status: warning` 和 `confidence: low`。

当日报整体为 warning 时，报告必须保留降级原因，不能把默认文本、缺失库存或 stale 外盘数据包装成确定性研究结论。

`run_auto_daily.py` 只负责自动生成 `daily_input` 并调用现有 pipeline。它不重写计算、质检、入库或报告生成逻辑，也不修改数据库 schema。
