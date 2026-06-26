# Template · 商品期货日报（主导矛盾 + 今日异动 + 头部走势）

> 场景：用户说「做一个商品期货日报」「把商品期货今日异动做成页面」「参考 commodity-daily.html 生成一个可分享页」。
> 这是 bespoke 页面模板：`build_dashboard` 的标准 panel 不适合这种报纸式版式，所以走「手搓 HTML + 统一 data-kernel」路线。

## 什么时候用

用这个 recipe 的典型信号：

- 页面主题是商品期货 / 国内期货 / 商品日报 / 今日异动。
- 用户要看多空两侧、板块分化、涨跌幅排行、头部合约走势。
- 页面需要设计感、SVG 自定义图、sparkline，而不只是 line/bar/number/table 的普通看板。

不用它的情况：

- 只要一个普通折线图或几个数字卡 → 走 `build_dashboard`。
- 只看一只股票/指数画像 → 走 [single-stock/](../single-stock/README.md)。

## 页面结构

默认模板对应 [page.template.html](page.template.html)，结构是：

| 模块 | 数据 | 页面表现 |
|---|---|---|
| 主导矛盾 | 各品种最新涨跌幅按板块聚合 | 领涨板块 vs 领跌板块 |
| 今日异动 | 各品种最新涨跌幅 | 双向 movers SVG 分布图 |
| 板块条 | 板块平均涨跌幅、涨跌家数 | 6 个左右板块 summary cell |
| 头部走势 | 4 个代表品种近一月价格序列 | sparkline + 最新价 |

## Agent 可编辑空间

这个模板是页面资产，不是一次性 HTML。后续 Agent 可以改：

- 页头标题、副标题、日期口径、日报摘要；
- 主导矛盾的解释文案、风险提示、今日异动点评；
- `MOVERS` / `SPARKS` 的品种范围，但必须同步公式 outputs 与读取契约；
- 视觉细节和局部模块顺序，但不要破坏公共 share shell、移动端布局、分享海报和错误态。

不要随意改：

- `*_ret` / `*_px` 的 output 命名规则；
- `QB.query(CONFIG)` 和 `QB.lastValue` / `QB.series` 的取数路径；
- 发布前用 `scripts/compile_bespoke_page.py` 内联公共组件与 `assets/data-kernel.js` 的要求；
- `signature` 不对最终用户展示的规则。

## 公式包 output 契约

模板默认约定两类 output：

- `*_ret`：某个期货品种的最新涨跌幅，`read_mode = last_day_stats`，模板用 `QB.lastValue(out, key)` 读取。
- `*_px`：某个期货品种的价格序列，`read_mode = range_data`，模板用 `QB.series(out, key, {dropZero:true})` 读取。

默认品种清单在模板里的 `MOVERS` / `SPARKS` 数组维护。只要保持 output 名一致，页面无需改渲染逻辑。

```js
const MOVERS = [
  {k:"SC_ret", code:"SC", name:"原油", sector:"能化"},
  {k:"CU_ret", code:"CU", name:"沪铜", sector:"有色"},
  {k:"RB_ret", code:"RB", name:"螺纹", sector:"黑色"}
];
const SPARKS = [
  {k:"SC_px", code:"SC", name:"原油", unit:"元/桶"}
];
```

## 一、先验证公式（必须）

注册公式包之前，先在 `quant-buddy-skill` 里用 `runMultiFormulaBatchStream` 跑通。下面只是命名示例，真实 `index_title` 和合约/资产名必须以平台确认为准：

```jsonc
{
  "formulas": [
    "SC_px  = 收盘价(原油)",
    "SC_ret = 涨跌幅(收盘价(原油), 1)",
    "CU_px  = 收盘价(沪铜)",
    "CU_ret = 涨跌幅(收盘价(沪铜), 1)",
    "RB_px  = 收盘价(螺纹)",
    "RB_ret = 涨跌幅(收盘价(螺纹), 1)"
  ],
  "begin_date": 20250501
}
```

> 不确定资产名时，先在 `quant-buddy-skill` 里确认资产/数据名。不要把示例里的中文名当作保证可跑的 source of truth。

## 二、注册公式任务包

`params.json`（UTF-8，Windows 中文务必走 `@file`）：

```json
{
  "formulas": [
    "SC_px  = 收盘价(原油)",
    "SC_ret = 涨跌幅(收盘价(原油), 1)",
    "CU_px  = 收盘价(沪铜)",
    "CU_ret = 涨跌幅(收盘价(沪铜), 1)",
    "RB_px  = 收盘价(螺纹)",
    "RB_ret = 涨跌幅(收盘价(螺纹), 1)"
  ],
  "reads": [
    { "output": "SC_ret", "read_mode": "last_day_stats" },
    { "output": "CU_ret", "read_mode": "last_day_stats" },
    { "output": "RB_ret", "read_mode": "last_day_stats" },
    { "output": "SC_px", "read_mode": "range_data",
      "mode_params": { "lookback_days": 30 } },
    { "output": "CU_px", "read_mode": "range_data",
      "mode_params": { "lookback_days": 30 } },
    { "output": "RB_px", "read_mode": "range_data",
      "mode_params": { "lookback_days": 30 } }
  ],
  "ttl_days": 365
}
```

```bash
python scripts/formula_package.py register @params.json
```

成功后本地会落盘 `output/formula_packages/<package_id>.json`，里面有 `package_id` + `signature`。`signature` 是凭证，不要在最终对话里展示。

## 三、生成页面

准备一份 `compile_params.json`（UTF-8），用 `replacements` 替换页面标题和公式包凭证：

```json
{
  "template": "examples/commodity-daily/page.template.html",
  "out_file": "output/pages/commodity-daily.html",
  "replacements": {
    "__PAGE_TITLE__": "商品期货每日异动",
    "pkg_xxxxxxxx": "pkg_xxx",
    "replace_with_signature": "从本地凭证文件复制，不要发给最终用户"
  }
}
```

```bash
python scripts/compile_bespoke_page.py @compile_params.json
```

如果你新增/删除品种，同步改：

- `MOVERS`：所有参与今日异动与板块聚合的 `*_ret` outputs。
- `SECTOR_ORDER`：板块显示顺序。
- `SPARKS`：下方 sparkline 使用的 `*_px` outputs。

## 四、发布

发布前必须确认：

1. 页面已经由 `compile_bespoke_page.py` 生成，公共 share shell、`qr-mini.js` 和 `data-kernel.js` 均已内联。
2. `endpoint` 用 `https://`。如果页面发布到 `https://pages.quantbuddy.cn`，而 endpoint 是 `http://...`，浏览器会拦 mixed content。

```bash
python scripts/static_page.py upload '{"html_file":"output/pages/commodity-daily.html","title":"商品期货每日异动"}'
```

## 发布前自查

- [ ] 公式已在 `quant-buddy-skill` 真跑通过。
- [ ] `*_ret` 是涨跌幅/收益率，0 是合法平盘，不做 `dropZero`。
- [ ] `*_px` 是价格序列，模板读取时带 `{dropZero:true}`，避免价格缺口画到 0。
- [ ] 页面有错误槽，`QB.query` 抛错时显示「取数失败：...」。
- [ ] 线上发布使用 HTTPS endpoint。
- [ ] 页头固定为 `QuantBuddy · 宽宝`，按钮为 `刷新数据 / 分享 / 开始使用`，页面正文没有旧二维码块。
- [ ] 分享按钮能生成可复制/下载的 PNG 海报，二维码尺寸可扫。
- [ ] 未把 `signature` 打印进面向最终用户的聊天回复。

## 迁移已有 `commodity-daily.html`

如果用户给的是已有页面（例如桌面上的 `commodity-daily.html`）：

1. 保留它的视觉层、`MOVERS`、`SPARKS`、板块映射和文案。
2. 把手写 `fetch + SSE` 取数逻辑替换为 `QB.query(CONFIG)`。
3. 把手写 `last_value` / `range_data` 解包替换为 `QB.lastValue` / `QB.lastDate` / `QB.series`。
4. 用 `scripts/compile_bespoke_page.py` 编译成自包含页面，确认 endpoint 是 HTTPS。

这样这个页面就从“一次性 HTML”变成了本 skill 认可的商品期货日报模板实例。
