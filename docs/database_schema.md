## 十七、数据库设计

Agent 不应每次只临时搜索。为了长期迭代，需要建立自己的最小研究数据库。

### 17.1 表名统一规则

后续开发统一使用以下表名，避免同一张表出现多个名字。

| 表名 | 阶段 | 用途 |
| --- | --- | --- |
| market_prices | MVP 必建 | 行情价格、成交、持仓 |
| fx_rates | MVP 必建 | 汇率数据 |
| spread_table | MVP 必建 | 内外盘价差、月差、期限结构 |
| inventory_data | MVP 必建 | EIA 库存、国内库存等 |
| oil_events | MVP 必建 | 原油相关事件、新闻、公告 |
| evidence_database | MVP 必建 | 证据链编号和证据记录 |
| research_reports | MVP 必建 | 日报、周报、专题和人工审核结果 |
| china_fundamental_data | 二期扩展 | 中国进口、加工量、炼厂开工、成品油需求 |
| sentiment_data | 二期扩展 | 新闻、社媒、人工摘要等情绪数据 |

命名规则：

- 不再使用 `event_database`，统一使用 `oil_events`。
- 不再使用 `research_outputs`，统一使用 `research_reports`。
- MVP 阶段先建 7 张表；`china_fundamental_data` 和 `sentiment_data` 可以等日报稳定后再启用。

### 17.2 表结构设计

#### market_prices

用途：存储 SC、Brent、WTI、Oman、Dubai 等行情数据。

| 字段 | 说明 |
| --- | --- |
| date | 交易日期 |
| symbol | 品种代码，例如 SC、Brent、WTI |
| contract | 合约代码，例如 SC2409 |
| open | 开盘价 |
| high | 最高价 |
| low | 最低价 |
| close | 收盘价 |
| settlement | 结算价 |
| volume | 成交量 |
| open_interest | 持仓量 |
| currency | 计价货币 |
| unit | 计价单位 |
| source | 数据来源 |
| source_status | pass / warning / fail |
| update_time | 入库时间 |

#### fx_rates

用途：存储汇率数据。

| 字段 | 说明 |
| --- | --- |
| date | 日期 |
| pair | 货币对，例如 USD/CNY |
| mid_price | 中间价 |
| close | 收盘价 |
| intraday_price | 日内价格 |
| source | 数据来源 |
| source_status | pass / warning / fail |
| update_time | 入库时间 |

#### spread_table

用途：存储内外盘价差和月差。

| 字段 | 说明 |
| --- | --- |
| date | 日期 |
| sc_contract | SC 合约 |
| sc_close | SC 收盘价 |
| brent_price | Brent 价格 |
| wti_price | WTI 价格 |
| oman_price | Oman 价格 |
| dubai_price | Dubai 价格 |
| usd_cny | USD/CNY 汇率 |
| sc_brent_spread | SC-Brent 价差 |
| sc_wti_spread | SC-WTI 价差 |
| sc_oman_spread | SC-Oman 价差 |
| sc_dubai_spread | SC-Dubai 价差 |
| near_contract | 近月合约 |
| far_contract | 远月合约 |
| calendar_spread | 月差 |
| structure_type | Backwardation / Contango / Flat |
| calculation_method | 计算方法，例如简化口径 / 官方口径 / 手动口径 |
| data_alignment_note | SC、外盘和汇率日期是否同日 |
| source | 数据来源 |
| source_status | pass / warning / fail |

#### inventory_data

用途：存储国内外库存数据。

| 字段 | 说明 |
| --- | --- |
| date | 数据日期 |
| country_or_region | 国家或地区 |
| crude_inventory | 原油库存 |
| gasoline_inventory | 汽油库存 |
| distillate_inventory | 馏分油库存 |
| cushing_inventory | Cushing 库存 |
| port_inventory | 港口库存 |
| refinery_inventory | 炼厂库存 |
| unit | 单位 |
| source | 数据来源 |
| source_status | pass / warning / fail |
| publish_time | 发布时间 |

#### china_fundamental_data（二期扩展）

用途：存储中国原油和炼化基本面。

| 字段 | 说明 |
| --- | --- |
| date | 数据日期 |
| crude_import | 原油进口量 |
| refinery_run | 原油加工量或炼厂开工率 |
| port_inventory | 港口库存 |
| refinery_inventory | 炼厂库存 |
| gasoline_demand | 汽油需求 |
| diesel_demand | 柴油需求 |
| jet_fuel_demand | 航煤需求 |
| refinery_margin | 炼油利润 |
| source | 数据来源 |
| source_status | pass / warning / fail |
| publish_time | 发布时间 |

#### sentiment_data（二期扩展）

用途：存储新闻、社媒、人工摘要等情绪数据。该表第一阶段不作为日报生成的强依赖。

| 字段 | 说明 |
| --- | --- |
| date | 日期 |
| data_time | 数据对应时间 |
| sentiment_source | 情绪来源，例如 manual_news、public_media、social_media |
| sentiment_type | 情绪类型，例如 news_sentiment、manual_judgement |
| related_asset | 相关资产，默认 SC |
| sentiment_score | 情绪分数 |
| sentiment_label | positive / neutral / negative 或 利多 / 中性 / 利空 |
| sample_size | 样本数量 |
| summary | 情绪摘要 |
| keywords | 关键词 |
| source | 数据来源 |
| source_status | pass / warning / fail |
| publish_time | 发布时间 |

#### oil_events

用途：存储影响油价的事件。

| 字段 | 说明 |
| --- | --- |
| event_id | 事件编号 |
| event_time | 事件发生时间 |
| publish_time | 信息发布时间 |
| event_type | OPEC+ / EIA / 地缘政治 / 政策 / 交易所规则 / 宏观 |
| region | 地区 |
| description | 事件描述 |
| affected_factor | 影响变量，例如供给、需求、库存、汇率 |
| expected_impact | 预期影响 |
| actual_market_response | 实际市场反应 |
| source | 来源 |
| source_level | 来源等级 |
| source_status | pass / warning / fail |

#### evidence_database

用途：存储所有被用于结论的关键证据。

| 字段 | 说明 |
| --- | --- |
| evidence_id | 证据编号 |
| report_id | 关联报告编号 |
| data_snapshot_id | 关联数据快照编号 |
| source_name | 来源名称 |
| source_level | 来源等级 |
| evidence_type | 行情 / 库存 / 新闻 / 公告 / 月报 / 人工备注 / 计算指标 |
| publish_time | 发布时间 |
| data_time | 数据对应时间 |
| extracted_fact | 提取出的事实 |
| raw_value | 原始值 |
| normalized_value | 标准化后的值 |
| unit | 单位 |
| related_variable | 相关变量 |
| conclusion_impact | 对结论的影响 |
| confidence | 证据可信度 |
| url_or_reference | 原文链接或引用 |
| source_status | pass / warning / fail |
| created_time | 入库时间 |

#### research_reports

用途：存储 Agent 输出的研究结论和人工审核结果。

| 字段 | 说明 |
| --- | --- |
| report_id | 报告编号 |
| data_snapshot_id | 数据快照编号，例如 SNAP-20260521-001 |
| date | 报告日期 |
| topic | 研究主题 |
| conclusion | 结论 |
| evidence_ids | 使用的证据编号 |
| confidence | 置信度 |
| report_status | pass / warning / fail |
| prompt_version | Prompt 版本 |
| calculation_version | 计算规则版本 |
| code_version | 代码版本或 Git commit |
| analyst_review | 人工审核结果 |
| error_type | 数据错误 / 口径错误 / 逻辑错误 / 归因过度 / 结论过强 / 遗漏变量 |
| severity | 高 / 中 / 低 |
| error_points | 错误点 |
| need_update_data_source | 是否需要修改数据源 |
| need_update_calculation_rule | 是否需要修改计算规则 |
| need_update_prompt | 是否需要修改 Prompt |
| correction | 研究员修正意见 |
| created_time | 生成时间 |
