# Auto Daily Preflight Policy

v0.6 Auto Daily Preflight 的目标是在没有人工 `daily_input` 的情况下，自动组装出最小可运行的 `daily_input_schema_v1`，并交给既有 `run_daily_pipeline.py` 完成计算、质检、快照、Evidence List、Markdown 日报和 `research_reports` 留痕。v0.7-step1 增加 Yahoo/yfinance market_fx 真实抓取尝试，用于 `USD_CNY`、`Brent_close`、`WTI_close`。

当前状态是：auto preflight complete, but not fully automatic。它不是最终自动化投研系统。当前阶段不接 Agent / LLM，不做联网搜索解释，不输出方向性交易建议，也不把默认文本字段、EIA 空值占位或 Yahoo/yfinance 免费便利源数据当作官方确认研究依据。

## 运行命令

如果本机已配置可用的 AKShare 和 yfinance，可以直接运行；若必要 market/fx 字段无法取得，流程会 controlled failure，不会编造价格：

```bash
python src/pipeline/run_auto_daily.py --report-date YYYY-MM-DD --init-db
```

当前推荐的人类验收 / 本地可复现命令是使用已落地的 raw_data 文件，仍然不需要 `manual_supplement` 或人工 `daily_input`：

```bash
python src/pipeline/run_auto_daily.py \
  --report-date YYYY-MM-DD \
  --raw-input data/raw/akshare_sc_YYYY-MM-DD.json \
  --market-fx-raw-input data/raw/market_fx_YYYY-MM-DD.json \
  --init-db
```

如果有真实或上一期 EIA raw_data，可以额外传入；不传时会生成 warning stub：

```bash
python src/pipeline/run_auto_daily.py \
  --report-date YYYY-MM-DD \
  --raw-input data/raw/akshare_sc_YYYY-MM-DD.json \
  --market-fx-raw-input data/raw/market_fx_YYYY-MM-DD.json \
  --eia-raw-input data/raw/eia_inventory_YYYY-MM-DD.json \
  --init-db
```

## 字段来源

当前自动覆盖四类输入：

- AKShare SC fetcher：`SC_close`、`SC_settlement`、`SC_volume`、`SC_open_interest`、`SC_near_price`、`SC_next_price`。
- market_fx fetcher：`USD_CNY`、`Brent_close`、`WTI_close`。v0.7-step1 默认使用 Yahoo/yfinance：`USD_CNY` 先取 `CNY=X`，再取同一 provider fallback `USDCNY=X`；Brent 使用 `BZ=F`；WTI 使用 `CL=F`。
- EIA inventory stub：`EIA_crude_inventory`，默认输出 `value: null`、`fetch_status: warning`，metadata 标记 `pending_manual_review: true` 和 `confidence: low`。
- default fields：`exchange_notice`、`important_oil_news`、`manual_notes`、`OPEC_monthly_summary`、`IEA_monthly_summary`。

`EIA_crude_inventory` 还没有真实自动抓取。现阶段由 stub 明确写入 warning / low confidence 占位字段，并依赖数据字典的 warning 降级规则；后续再接周度库存 fetcher。

## 合并与覆盖优先级

自动合并的优先级固定为：

```text
manual_supplement > real fetched raw data > fallback raw data > explicit warning stub > default text fields
```

`manual_supplement` 可以覆盖任何自动生成、抓取、默认或计算字段；人工分析师输入拥有最高优先级。但覆盖绝不能静默发生。

当 `manual_supplement` 新增一个自动输入中不存在的字段时，最终字段会保留人工值和人工 metadata，并标记 `merge_source: manual_supplement_added`；这不是覆盖，因此不会标记 `manual_override_used`。

当 `manual_supplement` 覆盖已有字段时，最终 `daily_input` 的字段 metadata 必须保留 `merge_source: manual_supplement_override`、`manual_override_used: true`、`manual_override_source: manual_supplement`、覆盖前后数值、可用的上一来源 metadata（`previous_source_name`、`previous_source_status`、`previous_confidence`、`previous_unit`、`previous_data_time`、`previous_fetched_at`）和 `manual_override_warning: manual_supplement replaced an existing auto/fetched/default/calculated field`。默认还会降级为 `source_status: warning`、`confidence: low`（若人工未提供）和 `pending_manual_review: true`；只有人工补充显式提供 `source_status: pass` 且带 `human_reviewed` / `manual_reviewed` / `reviewed` 标记时，才保留更强的已复核状态。

如果人工直接提供 `SC_USD`、`SC_calendar_spread`、`SC_Brent_spread_simple`、`SC_WTI_spread_simple` 等计算字段，会保留该字段并标记 `calculation_method: manual_override`、`calculation_version: manual_override_v1`。如果只覆盖原始输入字段，则优先由现有计算器重新计算计算字段。

最终 `daily_input.context` 会写入 `manual_override_count`、`manual_override_fields`、`manual_override_applied` 和 `manual_added_fields`。

## 失败与降级策略

| 字段或类别 | 当前策略 |
| --- | --- |
| `SC_close` / AKShare 主行情 | 缺失或 fetch_status 为 fail 时，视为 controlled data failure，不生成正常日报。 |
| `USD_CNY` | Yahoo/yfinance 先尝试 `CNY=X`，再尝试同 provider 的 `USDCNY=X`。两者都失败时 controlled failure，不得编造。最近可用交易日只可作为 warning fallback。 |
| `Brent_close` / `WTI_close` | Yahoo/yfinance 使用 `BZ=F` / `CL=F`。周末、假日或时区 / 交易时段错位时，最近可用交易日可作为 warning fallback，metadata 必须标注实际日期。 |
| `EIA_crude_inventory` | 本阶段不真实自动抓取；默认写入 warning stub / `null` 值 / pending manual review，不能用于强结论。若传入真实或上一期 raw_data，必须保留 date / source metadata。 |
| 文本类字段 | 自动填默认 warning、low confidence 文本，不得用于强结论或交易判断。 |

原则是：

```text
价格核心字段缺失 -> fail
外盘 / 汇率可用最近交易日 -> warning
库存可用上一期或显式空值占位 -> warning
文本类字段默认空值 -> warning
```

`EIA_crude_inventory` 只有在 `value: null` 且 metadata 同时包含 `eia_warning_stub: true`、`fallback_used: true`、`pending_manual_review: true`、`source_status: warning` 时，才会按 explicit warning stub 降级为 warning。它绝不能被视为已确认库存数据。

## v0.7 业务表写入

v0.7 Step 2 增加可选业务表写入，目标是把日频 pipeline 产物持久化到 `market_prices`、`fx_rates`、`spread_table` 和 `evidence_database`。该能力默认关闭；开启后也必须遵守既有 pipeline 顺序：

```text
calculated_input
→ quality_report
→ data_snapshot
→ evidence_list
→ Markdown report
→ research_reports
→ write_business_tables
```

业务表写入不新增数据源、不改 schema、不做实时 streaming，也不引入 Agent、LLM 推理或交易信号。`source_status`、字段 metadata 和 warning 必须尽量保留。

`overall_status == fail` 时，默认不得写入 `market_prices`、`fx_rates` 或 `spread_table`，避免失败质量数据沉淀进历史行情表；只有独立 writer 显式 `--allow-fail-write` 时才允许 core table 写入。`evidence_database` 仍可在有 Evidence List 且 FK readiness 满足时写入。

`evidence_database` 只保存字段级 Evidence。若传入 `research_report_id` 或 `data_snapshot_id`，writer 必须先确认对应 `research_reports` / `data_snapshot` 父记录存在；若未提供 ID，则对应 FK 可为 `NULL`。不得生成结论级 Evidence。

## v0.7 Step 3 持久化验收

端到端 DB persistence 通过 fixture-based replay 验证：测试使用本地 AKShare raw fixture、market_fx raw fixture、临时 SQLite DB 和 `--write-business-tables`，覆盖 Auto Daily Preflight 到 business tables 的完整路径。自动化测试不依赖真实网络。

live smoke test 只作为手动操作记录在 `docs/daily_db_persistence_runbook.md`；Yahoo/yfinance 等免费公开 provider 不保证可用性或时效性。live 数据 stale / unavailable 时应 warning 或 controlled failure，不得伪造。

fail-quality run 默认不写 `market_prices`、`fx_rates` 或 `spread_table`。`evidence_database` 只有在 `research_reports` / `data_snapshot` readiness 满足且 Evidence List 存在时才写入。

## v0.9 Step 0 调度触发

v0.9 Step 0 增加 `scripts/run_scheduled_daily.py`，作为外部 scheduler 可调用的 trigger wrapper。它不是 daemon，不安装 cron / launchd / GitHub Actions，也不改变 Auto Daily 的计算、质检、Evidence、日报、业务表或 LLM input package 生成逻辑。

该 trigger 默认开启 `--write-business-tables` 和 `--generate-llm-input-package`，并写入 `scheduled_daily_summary_v1`。同一天重复运行默认 `report_id` 时，不带 `--replace` 可能失败；这是防止静默覆盖 `research_reports` 的安全行为。

调度仍然是外部且显式 opt-in。trigger 保留 no Agent、no LLM call、no trading signal、no final directional conclusion 边界。详细操作见 `docs/scheduler_trigger_runbook.md`。

## 输出约束

自动生成的最终输入必须是 `daily_input_schema_v1`。自动字段必须保留来源 metadata；默认文本字段必须写明 `source_status: warning` 和 `confidence: low`。

Yahoo/yfinance 是免费公开便利源，不是交易所官方源或终端级数据源。精确日期数据最高只标为 `confidence: medium`；若 provider 返回最近一个可用交易日，必须标记 `source_status: warning`、`confidence: low`、`fallback_used: true`、`original_report_date`、`actual_data_date` 和 `data_alignment_note`。market/fx 价格字段不得静默 stub、不得用占位值、不得伪造。

fixture / stub raw_data 仍可用于可复现测试，但必须在 metadata 中保留 `source_name: market_fx_stub`、`source_level: test`、`is_real_provider: false`、`fetched_at` 和 `fallback_used`。

当日报整体为 warning 时，报告必须保留降级原因，不能把默认文本、EIA stub 空值、缺失库存或 stale 外盘数据包装成确定性研究结论。

`run_auto_daily.py` 只负责自动生成 `daily_input` 并调用现有 pipeline。它不重写计算、质检、入库或报告生成逻辑，也不修改数据库 schema。
