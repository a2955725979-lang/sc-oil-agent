# SC Oil Agent

个人创作者版 SC 中国原油期货研究自动化项目。

## 目录

- `docs/`：系统设计文档分册
- `docs/contracts.md`：v0.5 冻结后的 raw_data / daily_input 契约
- `docs/auto_daily_policy.md`：v0.6 Auto Daily Preflight 的失败降级和默认字段策略
- `docs/fetcher_design.md`：v0.5 fetcher 接口与 raw_data 转换契约
- `docs/validation.md`：本地 MVP 流水线 warning / fail 验证记录
- `config/data_dictionary.yaml`：MVP 字段数据字典
- `data/samples/fetchers/`：test-only 的 fetcher raw_data 契约样例
- `data/samples/validation/`：test-only 的 pass / warning / fail 验证样例
- `templates/`：日报、周报、事件点评模板
- `prompts/`：Agent 系统提示词
- `src/`：后续 Python 模块目录
- `db/`：SQLite 数据库位置
- `reports/`：生成的研究报告

## MVP 顺序

1. 建工程骨架和数据字典
2. 半自动日报 + 极简 SQLite
3. 补齐 7 张正式表
4. Evidence ID 自动化
5. 接入 Agent 生成解释
6. 连续 10 个交易日试运行

## 每日数据质检

`data/manual/daily_input_example.json` 只是格式示例，不是真实市场数据，不能用于研究、交易或行情判断。

示例文件用于演示每日输入 JSON 的结构，以及质检器如何输出 `pass / warning / fail`。v0.5 新生成的 daily input 使用 `daily_input_schema_v1`；旧 daily input 缺少 `schema_version` 暂时仍可读取。其中：

- `Oman_price_experimental` 用于演示“未在数据字典中定义的额外字段 warning”，不会进入正式字段质检。
- `OPEC_monthly_summary` 和 `IEA_monthly_summary` 的 warning 来自当前 v1 的 `source_conflict_check` 占位逻辑，不是 `revision_check`。
- 示例预期结果是 `overall_status: warning`，并且 `fail: 0`。

运行示例质检：

```bash
python src/validators/run_quality_validation.py --input data/manual/daily_input_example.json --output data/processed/quality_report_example.json
```

日常使用时，可以复制示例文件并改名：

```text
data/manual/daily_input_YYYY-MM-DD.json
```

然后填入当天真实数据，再运行：

```bash
python src/validators/run_quality_validation.py --report-date YYYY-MM-DD
```

默认输出位置：

```text
data/processed/quality_report_YYYY-MM-DD.json
```

## 每日计算字段

价差/月差计算器只读取本地 `daily_input`，不联网、不入库、不修改原始手填文件。默认输出到：

```text
data/processed/calculated_input_YYYY-MM-DD.json
```

运行示例：

```bash
python src/calculators/spreads.py --input data/manual/daily_input_example.json --output data/processed/calculated_input_example.json
```

当前会生成或重算这些字段：`SC_USD`、`SC_calendar_spread`、`SC_Brent_spread_simple`、`SC_WTI_spread_simple`。processed 层默认覆盖已有计算字段，确保口径统一；如果只是想保留手填计算值，可以加 `--preserve-existing`。

## 非 Agent 日报生成

日报生成器借鉴结构化 daily brief 思路，但当前不依赖 Agent 或外部 skill。它只读取本地 `daily_input` 和 `quality_report`，用固定模板生成 Markdown，不联网搜索，不调用 LLM，不自动生成交易观点，也不伪造正式 Evidence ID。

先生成质量报告：

```bash
python src/validators/run_quality_validation.py --input data/manual/daily_input_example.json --output data/processed/quality_report_example.json
```

再生成示例日报：

```bash
python src/report_generator/generate_daily_report.py --daily-input data/manual/daily_input_example.json --quality-report data/processed/quality_report_example.json --output reports/daily/SC_daily_example.md --data-snapshot-id SNAP-EXAMPLE-001
```

可选生成字段级 Evidence List：

```bash
python src/evidence/generate_evidence_list.py --daily-input data/manual/daily_input_example.json --quality-report data/processed/quality_report_example.json --output data/processed/evidence_list_example.json --data-snapshot-id SNAP-EXAMPLE-001
```

然后让日报引用 Evidence List：

```bash
python src/report_generator/generate_daily_report.py --daily-input data/manual/daily_input_example.json --quality-report data/processed/quality_report_example.json --evidence-list data/processed/evidence_list_example.json --output reports/daily/SC_daily_example.md --data-snapshot-id SNAP-EXAMPLE-001
```

Evidence List v1 只是字段级证据，不是研究结论证据，不能直接支撑方向性研究或交易判断。

Evidence ID v1 按输入 JSON 中字段出现顺序编号；同一输入顺序下编号稳定，但不承诺字段重排后仍保持同一编号。

如需把生成后的 Markdown 日报写入 SQLite 的 `research_reports` 表，必须显式加 `--write-db`：

```bash
python src/report_generator/generate_daily_report.py --daily-input data/manual/daily_input_example.json --quality-report data/processed/quality_report_example.json --evidence-list data/processed/evidence_list_example.json --output reports/daily/SC_daily_example.md --write-db
```

自动 `report_id` 只新增不覆盖。显式 `--report-id` 默认也只新增；只有同时传 `--report-id` 和 `--replace` 时才会覆盖旧报告。

`data/manual/daily_input_example.json` 仍然只是格式示例，不是真实市场数据，不能用于研究、交易或行情判断。

当 `overall_status = warning` 时，日报会保留正常结构，但必须写出结论降级原因。当 `overall_status = fail` 时，日报只生成数据失败说明，不输出方向性结论。

## 一键日流程

当数据库已经初始化后，可以用一条命令完成本地 MVP 日流程：

```text
daily_input
→ calculated_input
→ quality_report
→ data_snapshot
→ evidence_list
→ SC_daily Markdown
→ research_reports
```

```bash
python src/pipeline/run_daily_pipeline.py --report-date YYYY-MM-DD
```

第一次运行或数据库不存在时，使用安全初始化参数：

```bash
python src/pipeline/run_daily_pipeline.py --report-date YYYY-MM-DD --init-db
```

`--init-db` 只会在数据库不存在时创建数据库；如果数据库已存在，只做结构检查。它不会删除、清空或重建历史快照。

pipeline 会先把原始输入计算成 `data/processed/calculated_input_YYYY-MM-DD.json`，后续质检、Evidence List 和日报都使用这份 calculated input。默认会重新计算并覆盖 processed 层计算字段；如果需要保留输入里已有的计算字段，可以加：

```bash
python src/pipeline/run_daily_pipeline.py --report-date YYYY-MM-DD --preserve-existing-calculations
```

重复运行会自动新增 `research_reports` 记录，便于复盘不同版本的日报。开发调试时，如果想覆盖同一个报告记录，可以显式使用：

```bash
python src/pipeline/run_daily_pipeline.py --report-date YYYY-MM-DD --report-id RPT-YYYYMMDD-SC-DAILY-DEV --replace
```

返回码含义：

```text
0 = 流程成功，质检结果为 pass 或 warning
1 = 程序或环境错误
2 = 质检结果为 fail，已生成 quality report 和失败版 Markdown，不写 data_snapshot，不生成 evidence_list
```

pass / warning / fail 的完整验收命令见 `docs/validation.md`。`data/samples/validation/` 下的样例不是市场数据，不能用于研究、交易或行情判断。

## Semi-auto daily workflow

v0.6 半自动日流程把 AKShare SC 行情、人工补充文件和既有本地 pipeline 串起来。AKShare 只供应 SC 市场字段；`manual_supplement` 继续供应 Brent、WTI、USD_CNY、EIA、OPEC/IEA、news 和 manual notes。最终日报仍然走既有 `run_daily_pipeline.py`，包括计算字段、质检、`data_snapshot`、Evidence List、Markdown 日报和 `research_reports` 写入。

```bash
python src/workflows/run_semiauto_daily.py \
  --report-date YYYY-MM-DD \
  --manual-supplement data/manual/manual_supplement_YYYY-MM-DD.json \
  --init-db
```

默认输出：

```text
data/raw/akshare_sc_YYYY-MM-DD.json
data/processed/akshare_daily_input_YYYY-MM-DD.json
data/processed/conversion_result_YYYY-MM-DD.json
data/manual/daily_input_YYYY-MM-DD.json
```

如果已经有本地 raw_data 文件，可以用 `--raw-input` 跳过 AKShare 实时调用：

```bash
python src/workflows/run_semiauto_daily.py \
  --report-date YYYY-MM-DD \
  --manual-supplement data/manual/manual_supplement_YYYY-MM-DD.json \
  --raw-input data/raw/akshare_sc_YYYY-MM-DD.json \
  --init-db
```

## Auto Daily Preflight

v0.6 Auto Daily Preflight 的目标是：没有 `manual_supplement` 时，也能自动组装最小可运行 `daily_input_schema_v1`，并跑完既有本地日报 pipeline。v0.7-step1 在此基础上增加 Yahoo/yfinance market_fx 真实抓取尝试，用于 `USD_CNY`、`Brent_close`、`WTI_close`。当前状态仍是 auto preflight complete, but not fully automatic：`EIA_crude_inventory` 只有 warning stub，Yahoo/yfinance 也只是免费公开便利源，不是交易所官方源或终端级数据源。当前阶段仍不接 Agent / LLM，不做联网搜索解释，不生成交易建议。

自动链路：

```text
akshare_sc.py
→ raw_data
→ transform.py
→ akshare_daily_input

market_fx.py
→ raw_data
→ transform.py
→ market_fx_daily_input

eia_inventory.py
→ raw_data warning stub 或传入 raw_data
→ transform.py
→ eia_daily_input

default_fields.py
→ default_fields daily_input

merge_daily_input.py
→ daily_input
→ run_daily_pipeline.py
```

默认运行方式会尝试实时抓取 AKShare SC 和 Yahoo/yfinance market/fx；如果任一必要市场字段无法取得，也会 controlled failure，不会编造价格：

```bash
python src/pipeline/run_auto_daily.py --report-date YYYY-MM-DD --init-db
```

当前推荐的人类验收 / 本地可复现命令仍可使用已落地 raw_data，仍然不需要 `manual_supplement` 或人工 `daily_input`：

```bash
python src/pipeline/run_auto_daily.py \
  --report-date YYYY-MM-DD \
  --raw-input data/raw/akshare_sc_YYYY-MM-DD.json \
  --market-fx-raw-input data/raw/market_fx_YYYY-MM-DD.json \
  --init-db
```

如果有真实或上一期 EIA raw_data，可以额外传入；不传时 `eia_inventory.py` 会生成 warning / low confidence stub：

```bash
python src/pipeline/run_auto_daily.py \
  --report-date YYYY-MM-DD \
  --raw-input data/raw/akshare_sc_YYYY-MM-DD.json \
  --market-fx-raw-input data/raw/market_fx_YYYY-MM-DD.json \
  --eia-raw-input data/raw/eia_inventory_YYYY-MM-DD.json \
  --init-db
```

`market_fx.py` 自动字段是 `USD_CNY`、`Brent_close`、`WTI_close`，输出仍然是 `raw_data_contract_v1`。v0.7-step1 默认尝试 Yahoo/yfinance：`USD_CNY` 先取 `CNY=X`，失败后取同一 provider 的 `USDCNY=X`；Brent 使用 `BZ=F`，WTI 使用 `CL=F`。Yahoo/yfinance 是免费公开便利源，不是交易所官方源或终端级数据源；精确日期数据最高只标为 medium confidence。若周末、假日或时区 / 交易时段错位导致 provider 返回最近一个可用交易日，字段会标记 `fallback_used: true`、`source_status: warning`、`confidence: low`、`actual_data_date` 和 `data_alignment_note`。如果必要 market/fx 字段取不到，流程必须 controlled failure，不得静默 stub 或填占位价格。

通过 `--market-fx-raw-input` 传入本地文件时，会跳过 live provider，继续作为可复现 / 测试模式。fixture 或 stub raw_data 必须显式标记 `source_name: market_fx_stub`、`source_level: test`、`is_real_provider: false`。`eia_inventory.py` 当前只明确处理 `EIA_crude_inventory` 的未配置状态，不声称真实抓取 EIA；只有带 `eia_warning_stub: true`、`fallback_used: true`、`pending_manual_review: true` 的 `null` 值才会被验证器降级为 warning，且绝不能当作确认库存数据。

`manual_supplement` 可以覆盖任何自动生成、抓取、默认或计算字段；人工分析师输入拥有最高优先级。但覆盖绝不能静默发生。新增人工字段会标记 `merge_source: manual_supplement_added`，不会标记为 override。所有被覆盖字段都会写入 `merge_source: manual_supplement_override`、`manual_override_used: true`、`manual_override_source: manual_supplement`、覆盖前后数值、可用的上一来源 metadata 和 `manual_override_warning: manual_supplement replaced an existing auto/fetched/default/calculated field`。默认会降级为 `source_status: warning`、`pending_manual_review: true`，除非人工补充显式提供已复核的更强 metadata。

```bash
python src/pipeline/run_auto_daily.py \
  --report-date YYYY-MM-DD \
  --manual-supplement data/manual/manual_supplement_YYYY-MM-DD.json \
  --init-db
```

如果人工直接提供 `SC_USD`、`SC_calendar_spread`、`SC_Brent_spread_simple`、`SC_WTI_spread_simple` 等计算字段，会保留该字段并标记 `calculation_method: manual_override`、`calculation_version: manual_override_v1`。如果只覆盖原始输入字段，则优先由现有计算器重新计算计算字段。最终 `daily_input.context` 会记录 `manual_override_count`、`manual_override_fields`、`manual_override_applied` 和 `manual_added_fields`。

默认文本字段包括 `exchange_notice`、`important_oil_news`、`manual_notes`、`OPEC_monthly_summary`、`IEA_monthly_summary`，全部标记为 warning / low confidence，不得用于强结论或交易判断。

当前 Auto Daily Preflight 的验收目标是“无人工 daily_input 也能跑出 warning 日报”，不是自动生成完整研究判断。失败降级规则见 `docs/auto_daily_policy.md`。

## Business table writing

v0.7 Step 2 增加可选的业务表持久化目标。默认 pipeline 仍只写 `data_snapshot` 和 `research_reports`；只有显式开启时，才会把日频 pipeline 产物写入 `market_prices`、`fx_rates`、`spread_table` 和 `evidence_database`。这不是实时流式行情入库，也不新增 Agent、交易信号或 schema migration。

独立 writer 可以先单独运行，且要求 `research_reports` / `data_snapshot` 父记录已存在后再写 Evidence FK：

```bash
python src/database/write_business_tables.py \
  --calculated-input data/processed/calculated_input_YYYY-MM-DD.json \
  --quality-report data/processed/quality_report_YYYY-MM-DD.json \
  --evidence-list data/processed/evidence_list_YYYY-MM-DD.json \
  --db db/sc_oil_research.sqlite \
  --data-snapshot-id SNAP-YYYYMMDD-001 \
  --research-report-id RPT-YYYYMMDD-SC-DAILY-001 \
  --summary-output data/processed/business_write_summary_YYYY-MM-DD.json
```

也可以在日报 pipeline 中开启，写入顺序固定为 `calculated_input → quality_report → data_snapshot → evidence_list → Markdown report → research_reports → write_business_tables`：

```bash
python src/pipeline/run_daily_pipeline.py \
  --report-date YYYY-MM-DD \
  --input data/manual/daily_input_YYYY-MM-DD.json \
  --init-db \
  --write-business-tables \
  --business-write-summary-output data/processed/business_write_summary_YYYY-MM-DD.json
```

Auto Daily Preflight 也只做透传：

```bash
python src/pipeline/run_auto_daily.py \
  --report-date YYYY-MM-DD \
  --init-db \
  --write-business-tables \
  --business-write-summary-output data/processed/business_write_summary_YYYY-MM-DD.json
```

写入是幂等的，重复写同一日报 artifact 不应产生重复行。`overall_status == fail` 时默认不会写 `market_prices`、`fx_rates` 或 `spread_table`；只有显式 `--allow-fail-write` 的独立 writer 才允许 fail core writes。`evidence_database` 保持字段级 Evidence，只在 FK readiness 满足后写入；不生成结论级 Evidence 或交易建议。

个人日常验收与操作 runbook 见 `docs/daily_db_persistence_runbook.md`。这是 v0.7 Step 3 的 acceptance path：`--write-business-tables` 显式启用业务库持久化，默认 pipeline 仍保持安全关闭；`business_write_summary` 提供每次写入的行数审计。

## Real-date smoke test

v0.7.1 增加手动 real-date smoke test，用于验证真实 AKShare + market_fx provider 能否跑通 auto daily、日报生成和业务库持久化。该 smoke test 不进入 CI，不做调度，不验证交易准确性，也不生成交易信号。

```bash
python scripts/run_real_date_smoke.py --report-date YYYY-MM-DD --init-db
```

详细步骤、绿 / 黄 / 红验收标准和手工 SQL 检查见 `docs/real_date_smoke_test_runbook.md`。

## LLM input package

v0.8.1 增加 deterministic `llm_input_package_v1`，用于把现有 pipeline artifacts 打包成未来 LangGraph / LLM 层可消费的结构化 JSON。它不调用 LLM、不运行 Agent、不生成市场结论或交易信号，也不改变质检、Evidence、日报、业务表写入或数据库 schema。

```bash
python src/llm/generate_llm_input_package.py \
  --calculated-input data/processed/calculated_input_YYYY-MM-DD.json \
  --quality-report data/processed/quality_report_YYYY-MM-DD.json \
  --evidence-list data/processed/evidence_list_YYYY-MM-DD.json \
  --business-write-summary data/processed/business_write_summary_YYYY-MM-DD.json \
  --daily-report reports/daily/SC_daily_YYYY-MM-DD.md \
  --output data/processed/llm_input_package_YYYY-MM-DD.json
```

也可以在 pipeline 中显式开启：

```bash
python src/pipeline/run_daily_pipeline.py \
  --report-date YYYY-MM-DD \
  --input data/manual/daily_input_YYYY-MM-DD.json \
  --init-db \
  --generate-llm-input-package \
  --llm-input-package-output data/processed/llm_input_package_YYYY-MM-DD.json
```

package 会保留 `overall_status`、字段 `source_status`、`confidence`、fallback / date alignment 信息和字段级 Evidence 边界。`evidence_items` 只能支持字段可用性和来源可追溯性，不能直接支持方向性市场结论。详细说明见 `docs/llm_input_package.md`。

## Scheduler trigger

v0.9 Step 0 增加 scheduler-safe trigger wrapper，可由 cron、launchd、GitHub Actions 或其他外部调度器调用。它不是 daemon，也不会安装系统级计划任务；只是安全地触发现有 Auto Daily，并默认开启业务表写入和 LLM input package 生成。

```bash
python scripts/run_scheduled_daily.py --report-date YYYY-MM-DD --init-db
```

同一天重复运行默认 `report_id` 时，如果不加 `--replace` 可能失败，这是避免静默覆盖日报的安全行为。本地调试可使用：

```bash
python scripts/run_scheduled_daily.py --report-date YYYY-MM-DD --replace --init-db
```

运行详情、锁文件、cron / launchd 示例和 summary 字段见 `docs/scheduler_trigger_runbook.md`。该 trigger 仍不调用 LLM、不运行 Agent、不生成交易信号或最终方向性结论。

## Local Scheduler v1.0

v1.0 增加 macOS LaunchAgent 作为第一个本地无人值守调度方式。它仍然调用 `scripts/run_scheduled_daily.py`，不会安装调度任务，除非你显式运行安装 helper。

```bash
python scripts/install_launchagent.py \
  --project-root "$(pwd)" \
  --python-executable "$(which python)" \
  --hour 18 \
  --minute 30
```

LaunchAgent 环境变量很少，可能不继承 Terminal 的 conda/base 环境；`--python-executable` 建议传项目环境里的绝对 Python 路径。安装、卸载、健康检查、日志和回滚见 `docs/local_scheduler_runbook.md`。该本地调度仍不运行 Agent / LLM，不生成交易信号。

## Fetcher 契约与 AKShare SC 行情

v0.5 已冻结 `raw_data_contract_v1` 和 `daily_input_schema_v1`，并新增 AKShare SC 单源行情 fetcher v1。契约边界见 `docs/contracts.md`，接口设计见 `docs/fetcher_design.md`，样例见 `data/samples/fetchers/`。

fetcher 样例同样不是市场数据，不能用于研究、交易或行情判断。

AKShare SC 行情 fetcher 只输出冻结后的 `raw_data_contract_v1`，暂不自动进入一键 pipeline：

```bash
python src/fetchers/akshare_sc.py --report-date YYYY-MM-DD --output data/raw/akshare_sc_YYYY-MM-DD.json
```

将 raw_data 转成 AKShare partial daily input：

```bash
python src/fetchers/transform.py --input data/raw/akshare_sc_YYYY-MM-DD.json --output data/manual/akshare_daily_input_YYYY-MM-DD.json
```

人工补充 Brent、WTI、USD/CNY、库存、新闻和备注等字段：

```text
data/manual/manual_supplement_YYYY-MM-DD.json
```

再合并成 pipeline 使用的最终 daily input：

```bash
python src/fetchers/merge_daily_input.py --base data/manual/manual_supplement_YYYY-MM-DD.json --overlay data/manual/akshare_daily_input_YYYY-MM-DD.json --output data/manual/daily_input_YYYY-MM-DD.json
```

半自动链路：

```text
akshare_sc.py
→ transform.py
→ akshare_daily_input
+ manual_supplement
→ merge_daily_input.py
→ daily_input
→ run_daily_pipeline.py
```

然后运行已有质检：

```bash
python src/validators/run_quality_validation.py --input data/manual/daily_input_YYYY-MM-DD.json --output data/processed/quality_report_YYYY-MM-DD.json
```

真实 raw JSON 默认写入 `data/raw/`，不会提交到 GitHub。自动测试使用本地 fixture，不联网，也不依赖真实 AKShare 可用性。
真实 `data/manual/daily_input_YYYY-MM-DD.json` 也默认不提交 GitHub；`daily_input_example.json` 仍保留为格式示例。
