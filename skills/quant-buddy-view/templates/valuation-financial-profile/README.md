# Template · 个股估值体检

> 场景：用户问「这只股票贵不贵」「基本面是否改善」「估值和财务做成落地页」「PE/PB 历史水位 + 财务趋势 + 现金流质量」。
> 这是 **bespoke 页面模板**：核心是「估值水位 + 财务趋势 + 估值变动归因」。它回答单只股票的估值/基本面问题，比 `single-stock` 更深；不是多股票筛选页，也不是市场泡沫水位页。
>
> **模板展示名**：个股估值体检
> **内部 slug**：`valuation-financial-profile`

## 何时选这个模板

| 用户想要 | 选哪个 |
|---|---|
| 只要一只股票的价格、涨跌、PE/PB、成交额概览 | `single-stock` |
| **判断一只股票贵不贵、基本面是否改善、现金流质量如何** | **个股估值体检**（`valuation-financial-profile`） |
| 多市场过热、泡沫、风险水位 | `bubble-watch` |
| 指数成分股异动榜单 | `index-anomaly` |

判定关键词：**贵不贵 / 估值 / PE/PB 历史水位 / 基本面改善 / 财务趋势 / 现金流质量 / 财报期 / ROE / 归母净利润 / 营收同比**。

不要选它的反例：

- 「茅台最近走势怎么样」且用户没有要财务趋势 → `single-stock`。
- 「找出 PE 最低的 20 只股票」→ 选股/量化流程，不是本模板。
- 「市场是不是泡沫」→ `bubble-watch`。

## 页面形状

- **hero**：标的名、问题答案、最近交易日、估值/基本面双标签。
- **首屏指标**：最新价、日涨跌幅、PE(TTM)、静态 PE、PB、ROE、归母净利润同比、现金流/净利润。
- **估值水位**：PE(TTM)、PB、PCF 三条水位条，明确当前分位。
- **估值天平**：用价格变化、PE 变化反推出盈利代理变化，区分「价格推高估值」和「盈利拖累估值」。
- **估值曲线**：PE/PB/PCF 历史走势。
- **财务趋势**：营收、归母净利润、ROE、经营现金流；默认按报告期累计值展示，避免误读为连续日频经营曲线。
- **口径说明**：静态、TTM、单季、累计、报告期口径不可省略；首屏结论应克制表达，避免把小幅改善写成强投资判断。
- **分享海报**：点击页头“分享”后，用当前页面实时数据生成 PNG 海报；海报固定品牌页头和风险页尾，主体展示估值结论、核心指标、估值水位和归因拆解。

## 公式包 output 契约

本模板只消费 **一套公式包**。注册前必须先在 `quant-buddy-skill` 中验证同一组公式出数。

### 行情与估值

| output | 含义 | read_mode | 页面读取 |
|---|---|---|---|
| `px` | 最新价格 | `last_day_stats` | `QB.lastValue` |
| `chg` | 最近交易日涨跌幅，百分比数 | `last_day_stats` | `QB.lastValue` |
| `px_series` | 价格历史序列 | `range_data` | `QB.series(...,{dropZero:true})` |
| `pe_ttm` | PE(TTM) 最新值 | `last_day_stats` | `QB.lastValue` |
| `pe_static` | 静态 PE 最新值，A 股优先 | `last_day_stats` | `QB.lastValue` |
| `pb` | PB 最新值 | `last_day_stats` | `QB.lastValue` |
| `pcf` | PCF 经营现金流 TTM 最新值 | `last_day_stats` | `QB.lastValue` |
| `pe_ttm_series` / `pb_series` / `pcf_series` | 估值历史序列 | `range_data` | `QB.series` |
| `pe_pctile` / `pb_pctile` / `pcf_pctile` | 历史水位，建议输出 0-100 | `last_day_stats` | `QB.lastValue` |

### 财务与质量

| output | 含义 | read_mode | 页面读取 |
|---|---|---|---|
| `revenue` | 营业收入报告期序列，元 | `range_data` | `QB.series` |
| `net_profit_parent` | 归母净利润报告期序列，元 | `range_data` | `QB.series` |
| `roe` | ROE 报告期序列，百分比数 | `range_data` | `QB.series` |
| `operating_cashflow` | 经营现金流报告期序列，元 | `range_data` | `QB.series` |
| `cashflow_profit_ratio` | 经营现金流 / 归母净利润 | `range_data` | `QB.series` |
| `debt_ratio` | 资产负债率，百分比数 | `range_data` | `QB.series` |

> 注意：经营现金流的公式 `index_title` 不要凭空硬写。先用 `confirmDataMulti("经营现金流")` 确认返回的精确字段，再冻结到公式里。港股/美股字段缺失时，不要伪造；页面会降级显示已返回模块。

## A 股公式起手式

下面以「贵州茅台」为例。换股时同步替换资产名、`user_query` 和日期窗口。

```jsonc
{
  "formulas": [
    "px = 收盘价(贵州茅台)",
    "chg = 涨跌幅(收盘价(贵州茅台), 1) * 100",
    "px_series = 收盘价(贵州茅台)",
    "pe_ttm_raw = \"A股市盈率（PE, TTM）〔估值数据〕\" * 取出(贵州茅台)",
    "pe_static_raw = \"A股市盈率（PE）〔估值数据〕\" * 取出(贵州茅台)",
    "pb_raw = \"A股市净率（PB）〔估值数据〕\" * 取出(贵州茅台)",
    "pcf_raw = \"A股市现率（PCF，经营活动现金流TTM）〔估值数据〕\" * 取出(贵州茅台)",
    "pe_ttm = \"pe_ttm_raw\"",
    "pe_static = \"pe_static_raw\"",
    "pb = \"pb_raw\"",
    "pcf = \"pcf_raw\"",
    "pe_ttm_series = \"pe_ttm_raw\"",
    "pb_series = \"pb_raw\"",
    "pcf_series = \"pcf_raw\"",
    "pe_pctile = 数值水位(\"pe_ttm_raw\", 750) * 100",
    "pb_pctile = 数值水位(\"pb_raw\", 750) * 100",
    "pcf_pctile = 数值水位(\"pcf_raw\", 750) * 100",
    "revenue_raw = \"A股营业收入〔报告期利润表〕\" * 取出(贵州茅台)",
    "net_profit_parent_raw = \"A股归属于母公司股东的净利润〔报告期利润表〕\" * 取出(贵州茅台)",
    "roe_raw = \"A股净资产收益率ROE\" * 取出(贵州茅台)",
    "assets_raw = \"A股资产总计〔报告期资产负债表〕\" * 取出(贵州茅台)",
    "equity_raw = \"A股股东权益合计〔报告期资产负债表〕\" * 取出(贵州茅台)",
    "operating_cashflow_raw = \"<confirmDataMulti 返回的经营现金流 index_title>\" * 取出(贵州茅台)",
    "revenue = \"revenue_raw\"",
    "net_profit_parent = \"net_profit_parent_raw\"",
    "roe = \"roe_raw\"",
    "operating_cashflow = \"operating_cashflow_raw\"",
    "cashflow_profit_ratio = \"operating_cashflow_raw\" / \"net_profit_parent_raw\"",
    "debt_ratio = (\"assets_raw\" - \"equity_raw\") / \"assets_raw\" * 100"
  ],
  "begin_date": 20230101,
  "user_query": "生成贵州茅台个股估值体检页"
}
```

`reads` 建议：

- 最新指标：`px/chg/pe_ttm/pe_static/pb/pcf/pe_pctile/pb_pctile/pcf_pctile` → `last_day_stats`。
- 历史趋势：`px_series/pe_ttm_series/pb_series/pcf_series/revenue/net_profit_parent/roe/operating_cashflow/cashflow_profit_ratio/debt_ratio` → `range_data`。
- `range_data` 用滚动窗口 `lookback_days`，默认近 3 年（`lookback_days: 1095`）；财务报告期序列要覆盖至少最近 8 期，按报告期密度给足天数。

## 生成页面

准备一份 `compile_params.json`（UTF-8），用 `replacements` 替换页面标题、标的信息与公式包凭证：

```json
{
  "template": "templates/valuation-financial-profile/page.template.html",
  "out_file": "output/pages/valuation-financial-profile.html",
  "replacements": {
    "__PAGE_TITLE__": "贵州茅台 · 个股估值体检",
    "pkg_replace_after_formula_package_register": "pkg_xxx",
    "replace_with_signature": "从本地凭证文件复制，不要发给最终用户",
    "asset: \"贵州茅台\"": "asset: \"贵州茅台\"",
    "market: \"A 股\"": "market: \"A 股\"",
    "question: \"这只股票贵不贵？基本面是否改善？\"": "question: \"这只股票贵不贵？基本面是否改善？\""
  }
}
```

```bash
python scripts/compile_bespoke_page.py @compile_params.json
```

`CONFIG.endpoint` 发布到 `https://pages.quantbuddy.cn` 时必须是 `https://`。编译器会内联公共 share shell、`logo.svg`、`qr-mini.js` 与 `data-kernel.js`，最终 HTML 不应保留本地公共组件外链。

## 稳定 vs Agent 可编辑

可以改：

- 标题、副标题、问题文案、口径说明、风险提示；
- 日期窗口、展示期数、模块顺序；
- 缺字段时的降级文案。
- 基本面结论的阈值和文案，但必须保持“温和改善 / 分化 / 承压”等克制表达。

不要随意改：

- output 命名和 read_mode；
- `QB.query(CONFIG)` / `QB.lastValue` / `QB.series` 取数路径；
- 估值天平的语义：价格变化、PE 变化、盈利代理变化必须分开；
- 静态、TTM、单季、累计、报告期口径说明；
- 发布前用 `scripts/compile_bespoke_page.py` 内联公共组件与 `data-kernel.js`，不把 `signature` 输出到最终聊天回复。

## 发布前自查

- [ ] 公式已在 `quant-buddy-skill` 真跑通，且 `user_query` 是当前资产。
- [ ] 经营现金流字段已用 `confirmDataMulti` 确认，未用占位字段注册。
- [ ] 页面无 `QB_SHARED_` / `__PAGE_TITLE__` / `pkg_replace` / `replace_with_signature` 占位残留。
- [ ] 价格/估值序列不含假 0；价格使用 `{dropZero:true}`。
- [ ] 错误槽能显示取数失败原因，不会空白。
- [ ] 页面明确 PE 静态、PE(TTM)、单季/累计/报告期口径。
- [ ] 财务趋势区明确“报告期累计值”，归母净利同比说明为与 4 个报告期前同口径比较。
- [ ] 分享按钮能打开海报弹层，PNG 预览非空；公开 HTTPS 页可复制图片，受限环境下可下载 PNG。
- [ ] 公开页可访问，首屏、估值水位、估值天平、财务趋势均有内容。
