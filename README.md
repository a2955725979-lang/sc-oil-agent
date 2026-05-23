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

## 一键日流程

当数据库已经初始化后，可以用一条命令完成“质检 + 写入数据快照”：

```bash
python src/pipeline/run_daily_pipeline.py --report-date YYYY-MM-DD
```

第一次运行或数据库不存在时，使用安全初始化参数：

```bash
python src/pipeline/run_daily_pipeline.py --report-date YYYY-MM-DD --init-db
```

`--init-db` 只会在数据库不存在时创建数据库；如果数据库已存在，只做结构检查。它不会删除、清空或重建历史快照。

返回码含义：

```text
0 = 流程成功，质检结果为 pass 或 warning
1 = 程序或环境错误
2 = 质检结果为 fail，已生成 quality report，但不写入 data_snapshot
```
