## 十八、证据链编号机制

每条用于关键结论的证据必须生成唯一编号，避免输出“根据数据显示”这种不可追溯表述。

### 18.1 Evidence ID 规则

格式：

```text
EVID-YYYYMMDD-序号
```

示例：

```text
EVID-20260521-001
```

### 18.2 每条证据必须包含的信息

- evidence_id：证据编号
- report_id：关联报告编号
- source_name：来源名称
- source_level：来源等级
- evidence_type：证据类型
- publish_time：发布时间
- data_time：数据对应时间
- extracted_fact：提取出的事实
- raw_value：原始值
- normalized_value：标准化后的值
- unit：单位
- related_variable：相关变量
- conclusion_impact：对结论的影响
- confidence：证据可信度
- url_or_reference：原文链接或引用
- created_time：入库时间

### 18.3 示例

```text
evidence_id: EVID-20260521-001
report_id: RPT-20260521-SC-DAILY
data_snapshot_id: SNAP-20260521-001
source_name: EIA 周度库存报告
source_level: Level 1
evidence_type: 库存
publish_time: 2026-05-21 22:30 北京时间
data_time: 截至 2026-05-15 当周
extracted_fact: 美国商业原油库存环比下降
raw_value: 原始报告中的库存变化数值
normalized_value: 标准化为百万桶后的数值
unit: 百万桶
related_variable: 美国原油库存
conclusion_impact: 库存端偏利多原油
confidence: 高
url_or_reference: EIA Weekly Petroleum Status Report
created_time: 2026-05-21 23:10 北京时间
```

### 18.4 输出要求

Agent 在“依据”部分必须引用 Evidence ID。

阶段规则：

- 第 0 到第 2 阶段尚未完成证据库时，可以在报告中使用临时 Evidence ID，并在后续入库时补齐。
- 第 3 阶段完成 `evidence_database` 后，所有关键结论必须引用正式 Evidence ID。
- 严格模式下，如果无法生成或追溯 Evidence ID，只能输出保守结论，并明确说明证据链不完整。

示例：

```text
依据 1：美国商业原油库存环比下降，库存端偏利多原油。证据编号：EVID-20260521-001。
```

