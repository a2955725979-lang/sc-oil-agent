# SC Oil Agent

个人创作者版 SC 中国原油期货研究自动化项目。

## 目录

- `docs/`：系统设计文档分册
- `config/data_dictionary.yaml`：MVP 字段数据字典
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

示例文件用于演示每日输入 JSON 的结构，以及质检器如何输出 `pass / warning / fail`。其中：

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
