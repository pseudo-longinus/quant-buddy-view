# Template · 单标的画像页（factsheet）

> 场景：用户说「帮我做个茅台的页面」「看看贵州茅台最近怎么样」「做个 XX 股票的监控」。
> 这是最高频的需求。本模板不是简单堆面板，而是一个**可分享的个股 factsheet**：顶部摘要 + 关键指标卡 + 全宽主图 + 趋势/估值/活跃度观察。

## 怎么用这个 recipe

- **用户模糊地问**（只给了股票名）→ 直接套下面的模板，把资产名换掉即可，默认生成 factsheet。
- **用户有具体意图**（"我要看它的资金流""近三年走势""跟沪深300比"）→ 模板是**起点不是笼子**，在此基础上加/换公式与面板（见末尾「按意图改」）。
- **用户明确问贵不贵 / 基本面是否改善 / PE/PB 历史水位 / 财务趋势 / 现金流质量** → 改走 [valuation-financial-profile/](../valuation-financial-profile/README.md)，不要把深度估值财务问题压回普通 factsheet。

---

## 一、先建立心智模型：数据（一维/二维）+ 函数运算

公式体系的底座只有两件事——**数据**和**作用在数据上的函数**。不存在"某些指标是函数、某些只能引用"这种分类。

**数据有两种形态：**

| 形态 | 是什么 | 例子 |
|---|---|---|
| **二维**（资产×日期矩阵） | 全市场/一组资产在每个交易日的值。A 股绝大多数行情与基本面都是二维 | 收盘价、成交额、市值、PE/PB、因子、选股信号 |
| **一维**（只随日期变） | 单条时间序列 | 指数净值、宏观指标、回测净值曲线 |

数据在公式里用 **`index_title` 双引号引用**，如 `"全市场每日收盘价"`。引用名必须用平台返回的精确 `index_title`（比如"涨跌幅"实际叫 `"全市场每日回报率"`，写错就报"数据名不存在"）——不确定就先在 quant-buddy-skill 用 `confirmDataMulti` 查准。

**函数作用在数据上做计算，和维度解耦：**

- **`取出(资产名)`**：从**任意二维矩阵**里抽出某只资产的一维序列。所有二维数据都支持——这是底层计算，不是某些数据才"写死"能取。
  ```
  茅台成交额 = "全市场每日成交额" * 取出(贵州茅台)
  茅台 PE   = "A股市盈率（PE, TTM）〔估值数据〕" * 取出(贵州茅台)
  ```
- **`涨跌幅(数据, n)` / `平均(数据, N)`** 等变换：作用在一条数据（一维或二维皆可）上。

**`收盘价(资产名)` 等只是"快捷函数"**：是封装好的便捷读取，`收盘价(贵州茅台)` ≡ `"全市场每日收盘价" * 取出(贵州茅台)`，一步出单股。只有少数高频数据（收盘/开盘/最高/最低价）有这种快捷封装；没有快捷函数的（PE/PB/成交额…）就用通用写法 `"数据名" * 取出(资产名)`。**两者不是两类东西，只是有没有快捷封装的区别，底层都是「二维数据 + 取出」。**

> 一维数据（指数净值/宏观）本身已是一维，**不要再套 `取出`**。
> 公式左侧变量名**不要和 `index_title` 同名**（否则循环依赖），用 `茅台PE` / `pe_val` 之类。

---

## 二、起手模板（以贵州茅台为例）

### ① 先在 quant-buddy-skill 跑通公式（**必做，不可跳过**）

注册公式包**之前**，这组公式必须先在 quant-buddy-skill 里用 `runMultiFormulaBatchStream` 跑一遍、**确认出数**——公式包的公式语法与它完全一致，可原样粘过去验证。只有跑成功（资产名解析得了、公式不报错、结果非空）的公式，才允许提交注册。

```jsonc
// 在 quant-buddy-skill 里调用 runMultiFormulaBatchStream，formulas 与下面注册用的完全相同：
{
  "formulas": [
    "px     = 收盘价(贵州茅台)",
    "chg    = 涨跌幅(收盘价(贵州茅台), 1) * 100",
    "ret20  = (收盘价(贵州茅台) / 前几天(收盘价(贵州茅台), 20) - 1) * 100",
    "ret60  = (收盘价(贵州茅台) / 前几天(收盘价(贵州茅台), 60) - 1) * 100",
    "pe     = \"A股市盈率（PE, TTM）〔估值数据〕\" * 取出(贵州茅台)",
    "pb     = \"A股市净率（PB）〔估值数据〕\" * 取出(贵州茅台)",
    "amt_yi = (\"全市场每日成交额\" * 取出(贵州茅台)) / 100000000"
  ],
  "begin_date": 20250601,
  "user_query": "生成贵州茅台的个股画像看板"
}
```

> **为什么必做**：公式跑不出数的原因（资产名错、数据名拼错、`取出` 用法不对、口径不符）只有真跑一遍才暴露。在 quant-buddy-skill 验证是**正路**；本技能注册时的服务端试读只是**最后兜底**，不是用来代替这一步的——别"直接注册、错了再说"。
> **追踪字段也要同步**：换股票时，不只替换 `formulas` 里的资产名，`user_query` 也必须改成当前用户请求/当前资产；不要留下示例里的“贵州茅台 factsheet”。若需要 `task_id`，为本次验证新建，不要复用旧任务 ID。

### ② 注册公式包 `params.json`（UTF-8，中文务必走 @file）

```json
{
  "formulas": [
    "px     = 收盘价(贵州茅台)",
    "chg    = 涨跌幅(收盘价(贵州茅台), 1) * 100",
    "ret20  = (收盘价(贵州茅台) / 前几天(收盘价(贵州茅台), 20) - 1) * 100",
    "ret60  = (收盘价(贵州茅台) / 前几天(收盘价(贵州茅台), 60) - 1) * 100",
    "pe     = \"A股市盈率（PE, TTM）〔估值数据〕\" * 取出(贵州茅台)",
    "pb     = \"A股市净率（PB）〔估值数据〕\" * 取出(贵州茅台)",
    "amt_yi = (\"全市场每日成交额\" * 取出(贵州茅台)) / 100000000"
  ],
  "reads": [
    { "output": "px",  "read_mode": "range_data",
      "mode_params": { "lookback_days": 365 } },
    { "output": "chg", "read_mode": "last_day_stats" },
    { "output": "ret20", "read_mode": "last_day_stats" },
    { "output": "ret60", "read_mode": "last_day_stats" },
    { "output": "pe",  "read_mode": "last_day_stats" },
    { "output": "pb",  "read_mode": "last_day_stats" },
    { "output": "amt_yi", "read_mode": "last_day_stats" }
  ],
  "ttl_days": 365
}
```

```bash
python scripts/formula_package.py register @params.json
```

> ⚠️ 这里的 `formulas` 必须与步骤 ① 验证通过的**完全一致**。注册时服务端会再试读兜底（跑不出数会 `REGISTER_FAILED`），但这只是双保险，不能替代步骤 ①。

> **默认口径说明**：`chg` = 日涨跌幅（`涨跌幅(…,1) * 100`，单位为百分比）；`ret20/ret60` 是约 20/60 交易日前后价格变化，已乘以 100 作为百分比；`pe` = TTM（滚动 12 个月，负值=亏损股）；`amt_yi` 已换算成亿元。要别的口径见末尾。

### ③ 生成看板 `spec.json`（factsheet）

先复制模板，不要从空白 spec 手写：

```powershell
Copy-Item examples\single-stock\spec.template.json spec.json
```

保留 `"template": "single-stock"`。这个字段会触发 `build_dashboard` 的模板契约校验，防止重新退回旧版「1 条线 + 4 个数字卡」页面。

```json
{
  "template": "single-stock",
  "title": "贵州茅台 · 个股画像",
  "subtitle": "近一年走势、估值、成交活跃度与中短期趋势概览。请在生成前把这句话改成基于实际数据的一句话结论。",
  "package_id": "pkg_xxx",
  "panels": [
    {
      "title": "阅读摘要",
      "type": "text",
      "span": "full",
      "text": "截至最近交易日：贵州茅台价格、涨跌幅、估值与成交额见下方指标卡。生成页面时应把这里改成一句基于真实数据的结论。"
    },
    { "title": "最新收盘价", "output": "px", "type": "number", "description": "价格序列末个有效值" },
    { "title": "日涨跌幅", "output": "chg", "type": "number", "unit": "%", "description": "最近交易日" },
    { "title": "20日表现", "output": "ret20", "type": "number", "unit": "%", "description": "短期动量" },
    { "title": "60日表现", "output": "ret60", "type": "number", "unit": "%", "description": "中期动量" },
    { "title": "市盈率 TTM", "output": "pe", "type": "number", "description": "滚动 12 个月" },
    { "title": "市净率 PB", "output": "pb", "type": "number", "description": "最新可得估值" },
    { "title": "成交额", "output": "amt_yi", "type": "number", "unit": "亿元", "description": "最新交易日" },
    {
      "title": "近一年收盘价",
      "output": "px",
      "type": "line",
      "span": "full",
      "height": 380,
      "description": "主图应占整行，作为画像页的视觉中心"
    }
  ]
}
```

```bash
python scripts/build_dashboard.py @spec.json          # 仅生成本地 HTML
# 用户要“看板页/分享页”且没有说仅本地时，在 spec.json 里加 "upload": true 一步发布
```

> **首跑校验一眼**：`pe/pb/amt` 用 `取出` 收敛后应是一维 → number 卡取到的是「末个有效数值」。若某卡显示为空或像表格，多半是该产出仍是二维，回到公式确认 `取出` 写对了（`build_dashboard` 的取数体检也会在为空时 `code:1` 指出是哪个 output）。

---

## 三、解读：把"近期动态"的结论写进页面

用户若说"分析一下近期动态"，**别只给图**——解读是 Agent 的活。至少改两处：

- `subtitle`：写一句总判断；
- 第一个 `text` panel：写 2-3 句说明价格、估值、成交活跃度和趋势。

```json
"subtitle": "截至 06-11：股价处近一年中低位，日内回落，PE TTM 约 20 倍，成交额较近期均值放大。"
```

> 不要把 `text` panel 留成占位文案。若没有足够数据支撑，就写清楚"本页仅展示价格/估值/成交额概览，未纳入盈利预测与行业比较"。

> `build_dashboard` 会校验 `subtitle` 和“阅读摘要”里的关键数值是否匹配构建期实时取数结果（最终 outputs）。若返回 `文案与实时取数结果不一致`，用返回的 `facts` 重写收盘价、涨跌幅、20/60 日表现、PE、PB、成交额后再上传。

### Agent 可编辑空间

这个模板的稳定部分是：公式验证流程、`px/chg/ret20/ret60/pe/pb/amt_yi` 这些默认 outputs、`spec.template.json` 的 factsheet 骨架、统一分享页头页尾。Agent 可以按用户问题生成或调整：

- 标题、副标题和第一个 `text` panel 的分析摘要；
- 指标卡说明、风险提示、结论措辞；
- 增加对比基准、资金流、财务指标等额外公式和 panel；
- 调整图表时间窗口、panel 顺序和展示重点。

如果只是换股票，不要发明未验证公式；先在 `quant-buddy-skill` 确认资产名和公式能出数，再注册公式包。

---

## 四、按意图改（模板是起点不是笼子）

| 用户意图 | 怎么改 |
|---|---|
| 看更长/更短的走势 | 调 `px` 的 `lookback_days`（近半年=180、近两年=730） |
| 近一年累计涨幅，不要日涨跌幅 | `chg = 收盘价(贵州茅台) / 前几天(收盘价(贵州茅台), 240) - 1`（约一年≈240 交易日） |
| 静态 PE 而非 TTM | 把 `pe` 的数据名换成 `"A股市盈率（PE）〔估值数据〕"` |
| 加成交量 | 加 `vol = "全市场每日成交量" * 取出(贵州茅台)` + 一个 number 面板 |
| 加均线叠在价格上 | 加 `ma60 = 平均(收盘价(贵州茅台), 60)`，与 `px` 同 `range_data`，line 面板放一起 |
| 加相对基准 | 加沪深300/白酒指数收盘价或收益率，与 `px` 同期展示 |
| 加估值观察 | 加 PE/PB 的 `range_data` 折线，或同业/指数分位表 |
| 换一只股票 | 把所有 `贵州茅台` 换成目标股票全称，并同步更新验证参数里的 `user_query`；名字不确定先在 quant-buddy-skill 里确认资产 |

> 公式函数全表见 quant-buddy-skill 的 `presets/functions.yaml`；二维数据名见 `presets/data_catalog.yaml`。

> 页面是实时取数的：打开时调 `queryFormulaPackage` 拉最新数据，底层更新即自动重算，无需重建。
