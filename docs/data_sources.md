## 十六、数据源到字段映射

这一部分用于解决“Agent 到执行阶段不知道去哪里取数、字段叫什么、缺失时怎么办”的问题。

### 16.1 MVP 数据源映射表

个人创作者第一阶段优先使用免费、低成本、可手动校验的数据源。Wind、Choice、Bloomberg、Mysteel、隆众、卓创、Platts、Argus 等商业数据暂不作为 MVP 依赖，只作为未来增强项。

| 数据项 | MVP 首选来源 | MVP 备用来源 | 频率 | 成本 | API / 自动化 | 常用字段 | 数据延迟 | 主要用途 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| SC 主力价格 | AKShare 国内期货接口 | INE / 上期所官网手动校验、东方财富页面 | 日度 | 免费 | AKShare 可自动，官网校验半自动 | date, symbol, contract, open, high, low, close, settlement, volume, open_interest | 收盘后更新，免费源可能延迟 | 行情回顾、涨跌归因、日报 |
| SC 主力结算价 | INE / 上期所公告或日行情 | AKShare、东方财富 | 日度 | 免费 | 官网半自动，AKShare 可自动 | date, contract, settlement | 收盘后更新 | 结算口径、换月和复盘 |
| SC 成交量 / 持仓量 | AKShare 国内期货接口 | INE / 上期所、东方财富 | 日度 | 免费 | AKShare 可自动 | date, contract, volume, open_interest | 收盘后更新 | 资金热度、持仓变化 |
| SC 近月 / 次近月价格 | AKShare 国内期货接口 | INE / 上期所、东方财富 | 日度 | 免费 | AKShare 可自动 | date, near_contract, next_contract, near_close, next_close | 收盘后更新 | 月差计算、期限结构 |
| SC 月差 | Python 计算 | 手动用近月和次近月计算 | 日度 | 免费 | 自动计算 | date, near_contract, next_contract, calendar_spread | 依赖 SC 合约行情 | 判断近端供需强弱 |
| Brent 期货价格 | yfinance | FRED / EIA 现货参考、Investing 手动校验 | 日度 | 免费 | yfinance 可自动，FRED/EIA 可自动 | date, symbol, close, source | 外盘收盘后，可能与内盘日期错位 | 外盘锚定、价差和情绪 |
| WTI 期货价格 | yfinance | EIA / FRED 现货参考、Investing 手动校验 | 日度 | 免费 | yfinance 可自动，EIA/FRED 可自动 | date, symbol, close, source | 外盘收盘后，可能与内盘日期错位 | 美国油价参考、外盘情绪 |
| Brent / WTI 现货参考 | FRED / EIA | 手动网页校验 | 日度 / 周度 | 免费 | FRED / EIA 有 API | date, series_id, value, source | 视序列更新 | 校验外盘趋势，不替代期货主数据 |
| USD/CNY 汇率 | AKShare / FRED / 中国外汇交易中心 | 东方财富、Yahoo Finance | 日度 | 免费 | AKShare/FRED 可自动，官方网页半自动 | date, pair, close, mid_price, source | 日度或实时延迟 | 拆分人民币计价影响 |
| SC-Brent 简化价差 | Python 计算 | 手动计算 | 日度 | 免费 | 自动计算 | date, sc_close, usd_cny, brent_close, sc_brent_spread_simple | 依赖 SC、汇率、Brent | 简化内外盘对比 |
| SC-WTI 简化价差 | Python 计算 | 手动计算 | 日度 | 免费 | 自动计算 | date, sc_close, usd_cny, wti_close, sc_wti_spread_simple | 依赖 SC、汇率、WTI | 简化内外盘对比 |
| EIA 原油库存 | EIA API | EIA 网页、财经媒体摘要 | 周度 | 免费 | EIA API 可自动 | date, crude_inventory, cushing_inventory, publish_time | 公布后更新 | 美国库存、短期油价冲击 |
| EIA 汽油库存 | EIA API | EIA 网页、财经媒体摘要 | 周度 | 免费 | EIA API 可自动 | date, gasoline_inventory, publish_time | 公布后更新 | 成品油需求侧观察 |
| EIA 馏分油库存 | EIA API | EIA 网页、财经媒体摘要 | 周度 | 免费 | EIA API 可自动 | date, distillate_inventory, publish_time | 公布后更新 | 柴油和工业需求观察 |
| OPEC 月报摘要 | OPEC 官网手动摘要 | 路透 / 财经媒体摘要、券商公开研报 | 月度 | 免费 / 低成本 | 第一阶段手动录入 | publish_time, report_month, summary, supply_revision, demand_revision | 月报发布后 | 供需平衡和产量政策 |
| IEA 月报摘要 | IEA 官网公开内容手动摘要 | 路透 / 财经媒体摘要、券商公开研报 | 月度 | 部分免费 | 第一阶段手动录入 | publish_time, report_month, summary, demand_revision, supply_revision | 月报发布后 | 全球需求和库存判断 |
| 交易所公告 | INE / 上期所官网 | 期货公司公告、财经媒体 | 不定期 | 免费 | 第一阶段手动或半自动 | publish_time, title, notice_type, affected_contract, url | 公告发布后 | 保证金、交割、风控规则 |
| 重要原油新闻 | 手动新闻摘要 | 财联社、期货日报、公开财经媒体 | 日度 | 免费 / 低成本 | 第一阶段手动录入 | publish_time, event_time, title, summary, source, url, event_type | 取决于来源 | 事件驱动和风险提示 |
| 人工备注 | 研究员手动输入 | 无 | 日度 | 免费 | 手动 | date, note, analyst, related_variable | 报告生成前 | 补充行业判断和异常说明 |

### 16.2 数据缺失时的替代规则

1. AKShare 行情缺失时，优先使用 INE / 上期所官网或东方财富进行手动补录，并标注“手动补录”。
2. Oman / Dubai 数据缺失时，可临时使用 Brent 作为外盘参考，但必须说明 SC 的中东油锚缺失，结论置信度下调。
3. 实时行情缺失时，只能使用最近一个交易日收盘数据，不能写成“当前实时价格”。
4. yfinance、AKShare 等免费源数据异常时，必须用官方源或人工网页校验，不得直接入库为确认数据。
5. 新闻只有媒体转载、没有官方确认时，只能作为事件线索，不能作为事实依据。

### 16.3 个人创作者版本暂不接入的数据源

以下数据源第一阶段暂不作为必要依赖：

- Wind、Choice、iFinD、Bloomberg、Refinitiv
- Mysteel、隆众、卓创、Kpler、Vortexa
- Platts、Argus、DME 付费数据
- vn.py、CTP、实盘交易接口

处理原则：

- 可以在文档中保留为“未来增强项”。
- 不写入 MVP 必需数据源。
- 不作为日报能否生成的阻塞条件。
- 如果报告引用这些来源，必须来自人工已有权限或公开摘要，并标注来源和限制。

