# Fetcher Design

本文件定义 v0.5 的 fetcher 接口设计。当前阶段先完成契约层，并提供 AKShare SC 单源行情 fetcher v1；其他真实数据源暂不接入。

## 职责边界

fetcher 只负责：

- 获取或接收原始数据。
- 保留来源、字段、时间戳、单位和原始 payload。
- 输出结构化 `warnings` / `errors`。

fetcher 不负责：

- 研究结论。
- Evidence ID。
- 数据库写入。
- Agent / LLM 解释。
- 双源冲突判断。

## 数据流

```text
fetcher
→ raw_data JSON
→ conversion result
→ daily_input
→ calculated_input
→ quality_report
→ evidence_list
→ daily report
```

## raw_data_contract_v1

顶层结构：

```json
{
  "contract_version": "raw_data_contract_v1",
  "report_date": "2026-05-22",
  "source_name": "sample_source",
  "fetcher_name": "sample_fetcher",
  "fetcher_version": "fetcher_contract_v1",
  "fetched_at": "2026-05-22T16:00:00+08:00",
  "fetch_status": "pass",
  "records": [],
  "warnings": [],
  "errors": []
}
```

规则：

- `contract_version` 是数据契约版本，独立于 `fetcher_version`。
- `fetch_status` 只允许 `pass / warning / fail`。
- fetcher 层错误必须写入 `errors`，不要用异常替代结构化错误输出。
- 只有文件损坏、JSON 不合法、代码调用错误等环境问题才抛异常。

## record_contract_v1

单条字段记录：

```json
{
  "field": "SC_close",
  "value": 620.5,
  "metadata": {
    "unit": "CNY/barrel",
    "date": "2026-05-22",
    "timezone": "Asia/Shanghai",
    "source_field": "close",
    "source_level": "test",
    "url_or_reference": "sample"
  },
  "raw_payload": {}
}
```

`source_level` 只允许：

```text
test / manual / official / third_party / derived
```

## raw_data 转 daily_input

转换输出不是单纯 `daily_input`，而是 conversion result：

```json
{
  "daily_input": {},
  "conversion_warnings": [],
  "conversion_errors": [],
  "usable_for_pipeline": true
}
```

转换规则：

- `records[].field` 映射到 `daily_input.fields.<field>`。
- `records[].value` 原样进入字段值。
- `records[].metadata` 原样保留，并补充 `source_name`、`fetcher_name`、`fetched_at`。
- `fetch_status=fail` 时，`usable_for_pipeline=false`。
- 同一个 raw_data 内重复字段会产生 `conversion_warnings`，并保留第一条。
- 缺少 `records` 或 record 缺少 `field/value` 会进入 `conversion_errors`。

## AKShare SC 行情 Fetcher v1

第一个真实行情 fetcher 使用 AKShare 的交易所日行情接口：

```text
ak.get_futures_daily(start_date=YYYYMMDD, end_date=YYYYMMDD, market="INE")
```

CLI 示例：

```bash
python src/fetchers/akshare_sc.py --report-date 2026-01-15 --output data/raw/akshare_sc_2026-01-15.json
```

v1 规则：

- 主路径优先适配字段：`symbol`、`date`、`close`、`volume`、`open_interest`、`settle`、`variety`。
- `SC_settlement` 的来源字段是 `settle`，不是 `settlement`。
- SC 合约识别兼容 `SC2602` 和 `sc2602`；内部 `contract` 统一大写，`raw_symbol` 保留原始值。
- 主力合约默认按成交量最大选择。
- 如果成交量最大合约与持仓量最大合约不一致，输出 warning。
- `SC_near_price` 和 `SC_next_price` 从有成交量或持仓量的 SC 合约中按合约月份排序选择最近两个可用合约；低流动性只输出 warning，不强行替换。
- AKShare import 失败、接口不存在、接口异常或返回空表时，输出 `fetch_status=fail`、`records=[]`、`errors` 写明原因。
- 真实 raw JSON 输出到 `data/raw/`，默认不提交 Git。

## v0.5 限制

- 只接 AKShare SC 单源行情 fetcher v1。
- 不接 Brent、WTI、汇率、EIA、FRED 或 yfinance。
- 不修改正式数据字典。
- 不修改数据库 schema。
- 不写 `evidence_database`。
- 不接 Agent、LLM 或搜索。
- 不改变现有一键 pipeline 默认流程。
