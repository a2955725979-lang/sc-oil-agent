## 二十四、项目落地周期与 MVP 路线

这个项目第一阶段不要当成“预测模型”，而应当当成“原油研究自动化系统”。

不要一开始做全能 SC 研究员。第一阶段只做一个可验证功能：

```text
SC 原油期货日报生成器
```

建议周期：

| 阶段 | 时间建议 | 目标 | 交付物 |
| --- | --- | --- | --- |
| 第 0 阶段 | 2-4 天 | 工程骨架 + 数据字典，不做 Agent | 目录结构、20 个 MVP 字段的数据字典 |
| 第 1 阶段 | 3-5 天 | 半自动日报 + 极简 SQLite | `reports/SC_daily_YYYY-MM-DD.md`、3 张极简表 |
| 第 2 阶段 | 3-5 天 | 补齐 SQLite 正式数据库 | 7 张正式表和入库脚本 |
| 第 3 阶段 | 2-4 天 | 加入 Evidence ID | 证据自动编号和证据入库 |
| 第 4 阶段 | 5-10 天 | 再接入 Agent | Agent 负责解释、归因和写报告 |
| 第 5 阶段 | 10 个交易日 | 连续试运行 | 连续 10 篇可审核日报 |

### 24.1 第 0 阶段：工程骨架 + 数据字典

在做 Agent 前，必须先确定每个字段从哪里来、什么口径、什么时候更新、缺失时怎么办。

同时先建立工程目录骨架，避免第一批日报只散落为 Markdown 文件。

建议目录：

```text
sc-oil-agent/
├── data/
│   ├── raw/
│   ├── processed/
│   └── manual/
├── db/
│   └── sc_oil_research.sqlite
├── reports/
│   ├── daily/
│   └── weekly/
├── prompts/
│   ├── system_prompt.md
│   └── daily_report_prompt.md
├── src/
│   ├── fetchers/
│   ├── validators/
│   ├── calculators/
│   ├── database/
│   ├── evidence/
│   └── report_generator/
├── tests/
├── config.yaml
├── requirements.txt
└── README.md
```

数据字典必须落成可被程序读取的配置文件，不只保留在 Markdown 文档里。

建议文件：

```text
config/data_dictionary.yaml
```

示例：

```yaml
SC_close:
  required: true
  source_primary: AKShare
  source_backup: INE
  unit: CNY/barrel
  frequency: daily
  update_time: after_close
  quality_checks:
    - missing_check
    - stale_check
    - range_check
  fail_action: report_as_missing
```

每个字段至少包含：

- required
- source_primary
- source_backup
- unit
- frequency
- update_time
- quality_checks
- fail_action

MVP 先做以下 20 个字段即可：

| 字段 | 含义 | 首选来源 | 备用来源 | 频率 | 更新时间 | 口径 / 单位 | 是否自动 | 缺失处理 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| SC_close | SC 主力收盘价 | AKShare | INE / 上期所官网、东方财富临时替代 | 日度 | 收盘后 | 主力合约收盘价，人民币 / 桶 | 是 | 用最近交易日并标注 |
| SC_settlement | SC 主力结算价 | INE / 上期所官网 | AKShare、东方财富 | 日度 | 收盘后 | 主力合约结算价，人民币 / 桶 | 半自动 | 用收盘价临时代替并标注 |
| SC_volume | SC 成交量 | AKShare | INE / 上期所官网、东方财富 | 日度 | 收盘后 | 主力合约成交量 | 是 | 标注缺失 |
| SC_open_interest | SC 持仓量 | AKShare | INE / 上期所官网、东方财富 | 日度 | 收盘后 | 主力合约持仓量 | 是 | 标注缺失 |
| SC_near_price | SC 近月价格 | AKShare | INE / 上期所官网、东方财富 | 日度 | 收盘后 | 近月合约收盘价，人民币 / 桶 | 是 | 标注缺失 |
| SC_next_price | SC 次近月价格 | AKShare | INE / 上期所官网、东方财富 | 日度 | 收盘后 | 次近月合约收盘价，人民币 / 桶 | 是 | 标注缺失 |
| SC_calendar_spread | SC 月差 | Python 计算 | 手动计算 | 日度 | 收盘后 | 近月 - 次近月 | 是 | 若任一腿缺失则不计算 |
| Brent_close | Brent 价格 | yfinance | FRED / EIA 现货参考、Investing 手动校验 | 日度 | 外盘收盘后 | 美元 / 桶 | 是 | 用最近交易日并提示外盘时段 |
| WTI_close | WTI 价格 | yfinance | EIA / FRED 现货参考、Investing 手动校验 | 日度 | 外盘收盘后 | 美元 / 桶 | 是 | 用最近交易日并提示外盘时段 |
| USD_CNY | USD/CNY | AKShare / FRED | 中国外汇交易中心、东方财富 | 日度 / 实时 | 收盘后或实时 | 人民币 / 美元 | 是 | 用官方中间价或最近交易日并标注 |
| SC_Brent_spread_simple | SC-Brent 简化价差 | Python 计算字段 | 手动计算 | 日度 | 收盘后 | SC_close / USD_CNY - Brent_close | 是 | 若缺汇率或 Brent 则不计算 |
| SC_WTI_spread_simple | SC-WTI 简化价差 | Python 计算字段 | 手动计算 | 日度 | 收盘后 | SC_close / USD_CNY - WTI_close | 是 | 若缺汇率或 WTI 则不计算 |
| EIA_crude_inventory | EIA API | EIA 网页、财经媒体摘要 | 周度 | EIA 公布后 | 美国商业原油库存 | 是 | 使用上一期并标注 |
| EIA_gasoline_inventory | EIA API | EIA 网页、财经媒体摘要 | 周度 | EIA 公布后 | 美国汽油库存 | 是 | 使用上一期并标注 |
| EIA_distillate_inventory | EIA API | EIA 网页、财经媒体摘要 | 周度 | EIA 公布后 | 美国馏分油库存 | 是 | 使用上一期并标注 |
| OPEC_monthly_summary | OPEC 官网手动摘要 | 路透 / 财经媒体摘要、券商公开研报 | 月度 | 月报发布后 | 供给、需求、平衡表修正 | 半自动 | 使用最近月报并标注月份 |
| IEA_monthly_summary | IEA 官网公开内容手动摘要 | 路透 / 财经媒体摘要、券商公开研报 | 月度 | 月报发布后 | 需求、供给、库存判断 | 半自动 | 使用最近月报并标注月份 |
| exchange_notice | 交易所公告 | INE / 上期所 | 期货公司公告 | 不定期 | 公告发布后 | 保证金、涨跌停、交割、风控 | 半自动 | 无公告则写“无新增” |
| important_oil_news | 重要原油新闻 | 手动新闻摘要 | 财联社、期货日报、公开财经媒体 | 日度 | 日内滚动 | 3-5 条重要新闻摘要 | 半自动 | 无高可信新闻则降低结论强度 |
| manual_notes | 人工备注字段 | 研究员手动输入 | 无 | 日度 | 报告生成前 | 研究员补充判断、异常说明 | 否 | 可为空 |

### 24.2 第 1 阶段：半自动日报 + 极简 SQLite

第一阶段输入可以先手动或半自动，不必一开始追求全自动。

建议输入文件：

```text
data/daily_market_YYYY-MM-DD.csv
data/eia_latest.csv
data/news_YYYY-MM-DD.md
data/manual_notes.md
```

Python 脚本生成：

```text
reports/SC_daily_YYYY-MM-DD.md
```

日报必须包含：

- 今日结论
- 行情回顾
- 价差和汇率
- 库存 / 供需
- 事件影响
- 证据链 / Evidence ID
- 风险反例
- 明日关注
- 人工审核区

这一阶段的目标不是让系统“聪明”，而是让它每天稳定产出。

第一阶段必须同时建立极简 SQLite 空壳，避免后续返工。

极简表：

- data_snapshot：存储日报生成时使用的核心数据快照。
- evidence_database：存储临时或正式 Evidence ID。
- research_reports：存储日报正文、结论和人工审核结果。

每次生成日报都必须创建数据快照编号：

```text
SNAP-YYYYMMDD-序号
```

示例：

```text
SNAP-20260521-001
```

`data_snapshot_id` 必须绑定：

- 本次报告使用的原始数据版本
- 处理后数据版本
- Evidence ID
- 数据质量检查结果
- Prompt 版本
- 计算规则版本
- 代码版本或 Git commit

这样即使 AKShare、yfinance 或人工数据后续发生修正，也可以复现当时日报使用的那一版数据。

### 24.3 第 2 阶段：补齐正式数据库

第二阶段使用 SQLite 即可，不需要一开始上复杂系统。

最小数据库建议 7 张表：

- market_prices
- fx_rates
- spread_table
- inventory_data
- oil_events
- research_reports
- evidence_database

其中 `evidence_database` 必须保留，因为没有证据表，后续很难复盘“为什么当时这么判断”。

### 24.4 第 3 阶段：加入 Evidence ID

每一条关键结论必须能追溯到具体证据。

示例：

```text
结论：EIA 原油库存下降，对短期油价偏利多。
证据：EVID-20260521-001
来源：EIA Weekly Petroleum Status Report
数据时间：截至某周
发布时间：某日
影响变量：美国原油库存
影响方向：利多
```

系统需要自动生成 Evidence ID，并写入 `evidence_database`。

### 24.5 第 4 阶段：再接入 Agent

等数据、计算、报告模板和数据库能稳定运行后，再让 Agent 参与。

边界说明：

- 如果只是把本文作为纯 Prompt 使用，Agent 可以承担检索、筛选和初步验证工作。
- 如果进入工程落地阶段，取数、清洗、计算和入库应交给 Python 和数据库，Agent 只消费结构化数据、证据和人工备注。
- 工程落地时，Agent 的核心价值是解释、归因、组织证据、生成报告和提出后续验证清单。
- Agent 不允许直接读取杂乱网页后生成研究结论。

Agent 只能消费结构化输入包，例如：

```json
{
  "report_date": "2026-05-21",
  "market_data": {},
  "spread_data": {},
  "inventory_data": {},
  "event_data": [],
  "evidence_list": [],
  "quality_warnings": [],
  "manual_notes": ""
}
```

结构化输入包必须由 Python 脚本或人工审核流程生成。Agent 不能绕过数据质量检查直接解释原始网页、截图或未入库数据。

Agent 只负责三件事：

1. 解释数据变化。
2. 识别矛盾和反例。
3. 生成日报文本。

Agent 不应该独自负责找数、算数、存数、判断、写报告和下结论的全部流程。

更稳的分工是：

| 角色 | 负责内容 |
| --- | --- |
| Python | 取数、清洗、计算、入库 |
| 数据库 | 历史沉淀、证据链、版本记录 |
| Agent | 解释、归因、写报告、提出验证清单 |
| 人工研究员 | 审核、修正、补充行业判断 |

### 24.6 MVP 输入

第一批输入只需要：

1. SC 日行情
2. Brent / WTI 日行情
3. USD/CNY
4. EIA 库存
5. OPEC / IEA 月报摘要
6. 3-5 条原油相关新闻

暂不接入 Wind、Bloomberg、Kpler、Vortexa 等复杂商业数据，除非团队已经有稳定权限。

口径说明：

- MVP 阶段使用 Brent / WTI 是为了降低数据接入难度，只能视为简化外盘对比。
- 若未接入 Oman / Dubai，不得声称已经完成严格的 SC 中东油锚定分析。
- 当报告涉及“SC 内外盘强弱”时，必须提示 Oman / Dubai 缺失会降低结论置信度。

### 24.7 MVP 数据库

先建立 7 张表：

- market_prices
- fx_rates
- spread_table
- inventory_data
- oil_events
- research_reports
- evidence_database

### 24.8 MVP 日报输出

日报必须包含：

- 今日结论
- 行情回顾
- 价差和汇率
- 库存 / 供需
- 事件影响
- 证据链 / Evidence ID
- 风险反例
- 明日关注

### 24.9 人工审核机制

每篇日报后必须保留人工审核区。

```text
人工审核：
- 是否接受结论：是 / 否
- 错误类型：数据错误 / 口径错误 / 逻辑错误 / 归因过度 / 结论过强 / 遗漏变量
- 严重程度：高 / 中 / 低
- 错误点：
- 需要补充的数据：
- 是否需要修改数据源：是 / 否
- 是否需要修改计算规则：是 / 否
- 是否需要修改 Prompt：是 / 否
- 研究员修正意见：
```

人工审核结果应写入 `research_reports`，用于后续优化。

### 24.10 个人创作者三阶段路线

#### 第一阶段：SC 日报 MVP

目标：先做稳定的 SC 原油期货日报生成器。

技术组合：

- 数据采集：AKShare、INE / 上期所、EIA、FRED、yfinance、手动新闻摘要
- 存储：SQLite
- 分析：Python + pandas
- 报告：Markdown + Agent 生成解释
- 审核：人工审核写回 `research_reports`

第一阶段不做：

- 不接 Wind、Choice、iFinD、Bloomberg 等商业终端
- 不接 Mysteel、隆众、卓创、Kpler、Vortexa 等高成本产业链数据
- 不接 vn.py、CTP、实盘交易接口
- 不做自动交易
- 不做收益预测模型
- 不让 Agent 独立找数、算数、入库和下结论

#### 第二阶段：研究系统化

目标：把日报生成器升级成可复盘的研究工作台。

技术组合：

- OpenBB：作为多数据源统一接口和未来 MCP / Dashboard 入口
- AKShare：继续作为国内公开数据入口
- SQLite：继续用于轻量存储
- PostgreSQL：当数据量、多人协作或 Dashboard 需求上升时再迁移
- Agent：消费结构化数据、证据链和人工备注，负责解释和报告生成

第二阶段重点不是增加复杂模型，而是提高数据稳定性、复盘能力和报告一致性。

#### 第三阶段：交易和实盘前准备

目标：只有当研究系统连续稳定运行后，才进入交易准备阶段。

可选技术：

- vn.py：接 CTP 行情、模拟交易、风控模块和实盘接口
- 专业数据：Wind、Choice、Mysteel、隆众、卓创、Platts、Argus

硬规则：

- 研究系统输出不直接驱动实盘交易。
- Agent 不允许直接下单。
- 进入 vn.py 阶段前，必须先完成模拟交易、风控测试、日志审计和人工确认。
- Agent 最多生成市场解释、风险提示、观察清单和候选交易假设。

## 二十五、工程落地评分与改进方向

当前框架的定位是“研究系统设计文档”，不是单纯 Prompt。

| 维度 | 目标状态 |
| --- | --- |
| 研究定位 | 明确是研究员助手，不是喊单工具 |
| 研究范围 | 聚焦 SC，同时覆盖中东油、Brent、WTI、汇率、交割和库存 |
| 数据看板 | 需要落实到来源、字段、频率、API 和备用源 |
| 输出模板 | 支持日报、周报、事件点评和专题研究 |
| 风控边界 | 禁止绝对化判断、禁止虚构来源、禁止收益承诺 |
| 工程落地 | 通过数据库、Evidence ID 和指标口径实现可执行 |
| 可迭代性 | 通过人工审核和研究报告入库形成长期资产 |

下一步最优先任务：

1. 先建立 `sc-oil-agent/` 工程目录骨架。
2. 将 20 个 MVP 字段落成 `config/data_dictionary.yaml`。
3. 建立极简 SQLite：`data_snapshot`、`evidence_database`、`research_reports`。
4. 再做 SC 原油期货半自动日报生成器。
5. 补齐 7 张正式表和 `source_status` 质量状态。
6. 每天生成日报，先追求稳定，不追求复杂。
7. 每篇日报必须人工审核并沉淀修正意见。

### 25.1 MVP 验收标准

项目是否落地，不看它能不能说得专业，而看以下事项：

1. 能否连续 10 个交易日生成 SC 日报。
2. 每篇日报是否至少引用 3 条可追溯证据。
3. SC、外盘、汇率、月差是否口径一致。
4. 每篇日报是否有“反例和不确定性”。
5. 人工审核意见是否能写回数据库。
6. 每个核心数据源是否都有 `source_status`。
7. Agent 是否只消费结构化输入包，而不是直接解释杂乱网页。
8. 核心字段数据获取成功率是否大于或等于 90%。
9. 10 天内是否不因单字段缺失中断日报生成。
10. 每个核心结论是否至少对应 1 个 Evidence ID。
11. 高严重程度人工审核错误是否小于或等于 1 次 / 10 篇。
12. 数据为 `warning` 或 `fail` 时，是否能自动降低结论置信度或生成失败报告。

如果这些条件做不到，项目仍然主要是 Prompt 工程。

如果这些条件做到，项目就开始变成真正的研究系统。

### 25.2 当前项目判断

当前项目值得做，但第一阶段应定位为“原油研究自动化系统”，不是预测模型。

关键风险：

- 数据权限和数据稳定性比 Agent 能力更重要。
- 没有高频产业链数据时，投研价值上限会受限。
- 如果没有人工审核闭环，系统很难持续变好。
- 如果没有 Evidence ID，报告很难复盘和纠错。

建议优先补齐：

1. 工程目录骨架。
2. `config/data_dictionary.yaml`。
3. 极简 SQLite 和 `data_snapshot_id`。
4. 半自动日报脚本。
5. Evidence ID 自动生成。
6. 人工审核写回机制。

