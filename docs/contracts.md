# Contracts

本文件冻结 v0.5 的数据交换契约。当前冻结是非破坏性的：新生成文件和 test-only samples 必须写明版本；旧 `daily_input` 暂时仍可被现有 validation / pipeline 读取，避免打断 v0.4 主链路。

## raw_data_contract_v1

`raw_data` 是 fetcher 的唯一输出，不直接进入研究结论，也不直接写入一键 pipeline。

顶层 key 固定为：

```text
contract_version
report_date
source_name
fetcher_name
fetcher_version
fetched_at
fetch_status
records
warnings
errors
```

规则：

- `contract_version` 必须等于 `raw_data_contract_v1`。
- `fetch_status` 只允许 `pass / warning / fail`。
- `records`、`warnings`、`errors` 必须是数组。
- 顶层不开放扩展字段。
- 扩展字段只允许放在 `records[].metadata` 或 `records[].raw_payload`。
- `metadata.source_level` 只允许 `test / manual / official / third_party / derived`。

单条 record 固定为：

```json
{
  "field": "SC_close",
  "value": 620.5,
  "metadata": {},
  "raw_payload": {}
}
```

## daily_input_schema_v1

`daily_input` 是验证链输入。新生成的 `daily_input` 必须写：

```json
{
  "schema_version": "daily_input_schema_v1",
  "report_date": "2026-05-22",
  "context": {},
  "fields": {}
}
```

顶层 key 固定为：

```text
schema_version
report_date
context
fields
```

规则：

- `schema_version` 必须等于 `daily_input_schema_v1`。
- `context` 是 daily input 的顶层扩展口，用于保留来源、fetcher、计算、样例提示等上下文。
- `fields.<field>` 固定为 `{ "value": ..., "metadata": {...} }`。
- 字段扩展只允许放在 `fields.<field>.metadata`。
- 旧文件缺少 `schema_version` 暂时兼容到 v0.6 前；新生成文件和新样例必须带版本号。

## Conversion Result

`raw_data` 转 `daily_input` 的 CLI 输出 conversion result：

```json
{
  "daily_input": {},
  "conversion_warnings": [],
  "conversion_errors": [],
  "usable_for_pipeline": true
}
```

规则：

- conversion result 是转换诊断，不是 `daily_input_schema_v1`。
- CLI 始终写出 conversion result。
- 只有 `usable_for_pipeline=true` 时才写出 daily input 文件。
- `raw_data.fetch_status=fail` 或转换存在错误时，不写 daily input。

## Version Upgrade

- v1 contract/schema 的字段含义、顶层 key 和状态枚举不得静默改变。
- 如需破坏性变更，新增 `raw_data_contract_v2` 或 `daily_input_schema_v2`。
- 新版本需要独立 validator、样例和迁移说明。
- v0.5 不接入严格 JSON Schema 依赖，冻结测试使用标准库 validator。
