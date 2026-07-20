---
id: single_stock_deep_dive_v1
version: reply_template_v1
output_format: markdown
default_reply_scope: full_answer
source_playbooks:
  - 03_single_stock_deep_dive.md
  - 09_dashboard_guidance.md
---

# Single Stock Deep Dive

用于单只上市公司的综合分析。保留旧 Playbook 03 的七大节、Markdown 表格、计算维度分组、缺失数据和声明规则。

## 输出规则

- 首行直接输出报告标题，不暴露路由、工具、文件、命令或取数过程。
- `## 四、计算维度` 与 `## 五、波动率与风险` 必须分开。
- 数值只使用活页、运行时输出或已核验来源；偶发缺失单元格填 `--`，整维度结构性缺失时删除该可选章节。
- 计算维度按维度分组，每个维度一个小标题和一张指标表；不得混成一张大表。
- 消息面只写有来源和日期的条目；不预测明日涨跌、目标价或精确支撑压力位。
- 🟢 表示改善/低分位/正向，🟡 表示中性/观察，🔴 表示恶化/高分位/风险，⚫ 表示缺失。

## Markdown 骨架

```markdown
**{股票名}（{代码}）全面分析**

时间：截至 {computed_at 日期} | 数据来源：QB / 活页实时数据

---

## 一、行情与估值

**最新价**：{close_price} | **近20日**：{ret_20}% | **近60日**：{ret_60}% | **近120日**：{ret_120}% | **近250日**：{ret_250}%

| 指标 | 最新值 | 1Y分位 | 3Y分位 | 5Y分位 | 信号 |
|------|--------|--------|--------|--------|------|
| PE(TTM) | {pe_ttm} | {pe_1y_pct} | {pe_3y_pct} | {pe_5y_pct} | {signal} |
| PB | {pb_ratio} | {pb_1y_pct} | {pb_3y_pct} | {pb_5y_pct} | {signal} |
| PS(TTM) | {ps_ttm} | {ps_1y_pct} | {ps_3y_pct} | {ps_5y_pct} | {signal} |
| 股息率 | {dividend_yield} | {dy_1y_pct} | {dy_3y_pct} | {dy_5y_pct} | {signal} |

> 分位接近 100% 表示历史高位，接近 0% 表示历史低位，40%–60% 为中性区间。

---

## 二、财务分析

> 最近报告期：{financial_latest_date}

| 指标 | 单季最新 | 单季YoY | 单季QoQ | TTM | TTM YoY | 年度 | 年度YoY | 信号 |
|------|---------|---------|---------|-----|---------|------|---------|------|
| 收入增速 | {value} | {value} | {value} | {value} | {value} | {value} | {value} | {signal} |
| 扣非增速 | {value} | {value} | {value} | {value} | {value} | {value} | {value} | {signal} |
| 毛利率 | {value} | {value} | {value} | {value} | {value} | {value} | {value} | {signal} |
| 净利率 | {value} | {value} | {value} | {value} | {value} | {value} | {value} | {signal} |
| 营业利润率 | {value} | {value} | {value} | {value} | {value} | {value} | {value} | {signal} |
| ROE | {value} | {value} | {value} | {value} | {value} | {value} | {value} | {signal} |
| ROIC(TTM) | -- | -- | -- | {value} | {value} | {value} | {value} | {signal} |
| 经营现金流 | {value} | {value} | {value} | {value} | {value} | {value} | {value} | {signal} |
| 资本开支/收入 | -- | -- | -- | {value} | {value} | {value} | {value} | {signal} |

### 资产负债结构（有返回时）

| 指标 | 最新值 | 上一期值 | 年度YoY |
|------|--------|----------|---------|
| 合同负债 | {value} | {previous_value} | {annual_yoy} |
| 在建工程 | {value} | {previous_value} | {annual_yoy} |

{1–2 句财务定性点评，只基于表内趋势。}

---

## 三、资金 / 交易特征

| 指标 | 最新值 | 5日均线 | 60日趋势 | 3Y分位 | 信号 |
|------|--------|---------|----------|--------|------|
| 成交额占比 | {value} | {ma_5} | {trend_60} | {pct_3y} | {signal} |
| 做空比例 | {value} | -- | {trend_60} | {pct_3y} | {signal} |
| 基金持仓比例 | {value} | -- | {trend_60} | {pct_3y} | {signal} |

| 5日 | 10日 | 20日 | 60日 | 120日 | 250日 |
|-----|------|------|------|-------|-------|
| {value} | {value} | {value} | {value} | {value} | {value} |

{1 句资金特征结论。}

---

## 四、计算维度

### {维度名}得分：{score} {signal}

| 指标 | 最新值 | 说明/口径 | 信号 |
|------|--------|-----------|------|
| {indicator_name} | {value} | {description} | {signal} |

{其余非空维度重复上述小标题和表格；没有额外维度时写“本轮无额外计算维度”。}

---

## 五、波动率与风险

| 指标 | 最新值 | 1Y分位 | 3Y分位 | 5Y分位 | 信号 |
|------|--------|--------|--------|--------|------|
| 年化波动率 | {value} | {pct_1y} | {pct_3y} | {pct_5y} | {signal} |
| 标准差 | {value} | {pct_1y} | {pct_3y} | {pct_5y} | {signal} |

---

## 六、消息面（近30日）

| 时间 | 来源 / 事件 | 影响 |
|------|-------------|------|
| {YYYY-MM-DD} | {来源 + 事件摘要} | {signal} |

{无可靠来源时写“本轮未纳入可核验消息面”，不杜撰。}

---

## 七、综合观察

**估值定性**：{基于估值分位的一句话}

**财务趋势**：{基于增长、利润率、ROE和现金流的一句话}

**资金特征**：{基于成交活跃度、基金持仓和做空的一句话}

**计算维度**：{基于本节实际返回维度的一句话}

**风险因子**：{基于波动率、现金流和估值的一句话}

| 持仓情况 | 定性建议 |
|---------|---------|
| 空仓 | {不给具体价位的定性描述} |
| 已持有 | {不给具体价位的定性描述} |
| 高位浮盈 | {不给具体价位的定性描述} |

**一句话总结**：{有数据支撑的核心判断，不预测明日涨跌}

---

> 数据截至 {computed_at 日期}（财务截至 {financial_latest_date}）；不构成投资建议。
```
