# Template · 指数成分股异动监控（异动榜单 + 涨跌分布 + 指数走势）

> 场景：用户说「做个沪深300异动监控」「中证500今天哪些股票异动」「上证50涨跌幅榜做成页面」「科创50成分股放量/换手榜」。
> 这是 bespoke 页面模板：异动榜单是「单产出 → top_values 排行」结构，`build_dashboard` 的标准 table/number panel 装不下这种多榜并列的盘面，所以走「手搓 HTML + 统一 data-kernel」路线。
>
> **这是一个场景模板，不绑定任何具体指数。** 模板里所有指数名都是占位符（`__INDEX_NAME__` 等），由 Agent 在生成时按用户问的指数/股票池替换。沪深300 只是其中一个实例。

## 什么时候用

典型触发信号：

- 主题是「某指数 / 某股票池 的成分股异动、异动榜、龙虎榜式排行」。
- 用户想看：今天哪些成分股涨得多 / 跌得多 / 换手高 / 放量 / 振幅大。
- 想要一个深色盘面风、多榜并列、可分享、打开即实时取数并可生成分享海报的监控页。

不用它的情况：

- 只看**一只**股票/指数的画像（价格+估值+成交）→ 走 [single-stock/](../single-stock/README.md)。
- 主题是**商品期货**多空 / 板块分化 → 走 [commodity-daily/](../commodity-daily/README.md)。
- 只要一两个普通折线/数字卡 → 走 `../../workflows/dashboard-end-to-end.md`。

## 页面结构

对应 [page.template.html](page.template.html)：

| 区块 | 数据来源（output） | 页面表现 |
|---|---|---|
| 公共 share shell | — | `QuantBuddy · 宽宝` 页头、刷新、分享海报、开始使用入口与统一页尾 |
| hero 标签条 | — | `个股异动` · `Agent + Skill 生成` · `实时 HTML` |
| 基准指数卡 | `IDXRET`（涨跌幅）、`IDXPX`（价格序列） | 指数最新点位、当日涨跌幅、近期 sparkline |
| 涨跌分布 | `ADV/DEC/LU/LD`（涨跌家数/涨跌停家数） | 涨跌比 + 分布条 + 4 个计数 |
| 异动面板网格 | `GAIN/LOSE/TURN/VOLR/AMP`（各取 top_values） | 5 个榜单：涨幅/跌幅/换手/放量/振幅 Top10 |
| 公共页尾 | — | 品牌入口 + 简短免责声明 |

## Agent 可编辑空间

这个模板是页面资产，不是一次性 HTML。后续 Agent 可以改：

- 顶部 `INDEX.name` / 标题 / 副标题（英文名）/ kicker，换成本次监控的指数；
- 页尾免责声明文案；
- `PANELS` 数组：增删榜单（如去掉振幅、加「主力净流入」榜），但要同步公式包 outputs；
- `INDEX.count`：成分总数，用于涨跌分布里「平盘 = 总数 − 涨 − 跌」的兜底（不确定就设 0 关闭平盘段）；
- 视觉细节、面板顺序，但不要破坏公共 share shell、移动端布局、分享海报和错误态。

不要随意改：

- output 命名约定（`IDXRET/IDXPX/ADV/DEC/LU/LD/GAIN/LOSE/TURN/VOLR/AMP`）与 `read_mode`；
- `QB.query(CONFIG)` / `QB.topValues` / `QB.lastValue` / `QB.series` 的取数路径；
- 发布前用 `scripts/compile_bespoke_page.py` 内联公共组件与 `assets/data-kernel.js` 的要求；
- `signature` 不对最终用户展示的规则；
- share shell 的页头、页尾、刷新、分享海报、开始使用入口（`https://www.quantbuddy.cn`）。

## 公式包 output 契约

| output | 含义 | read_mode | 模板读取方式 |
|---|---|---|---|
| `IDXRET` | 指数当日涨跌幅(%) | `last_day_stats` | `QB.lastValue(o,'IDXRET')` |
| `IDXPX` | 指数价格/点位序列 | `range_data` | `QB.series(o,'IDXPX',{dropZero:true})` |
| `ADV` / `DEC` | 成分股上涨 / 下跌家数 | `last_day_stats` | `QB.lastValue` |
| `LU` / `LD` | 涨幅 / 跌幅 > 9.9% 家数（涨跌停近似） | `last_day_stats` | `QB.lastValue` |
| `GAIN` | 成分股当日涨幅榜 | `last_day_stats` | `QB.topValues(o,'GAIN')` → `[{asset,name,value}]` |
| `LOSE` | 成分股当日跌幅榜 | `last_day_stats` | `QB.topValues` |
| `TURN` | 成分股换手率榜 | `last_day_stats` | `QB.topValues` |
| `VOLR` | 成分股量比(5日)榜 | `last_day_stats` | `QB.topValues` |
| `AMP` | 成分股振幅榜 | `last_day_stats` | `QB.topValues` |

> 榜单类 output 用 `last_day_stats`，由服务端返回当日 `top_values`（含 `asset`/`name`/`value`），模板直接渲染，不在前端排序整个市场。

## 一、先验证公式（必须）

注册公式包**之前**，先在 `quant-buddy-skill` 里用 `runMultiFormulaBatchStream` 跑通、确认出数。下面是**命名示例**，真实指数名 / 成分池函数 / 数据 `index_title` 必须以平台 `confirmDataMulti` 确认为准，不要把示例中文名当成保证可跑的 source of truth：

```jsonc
{
  "formulas": [
    "IDXRET = 涨跌幅(收盘价(沪深300), 1) * 100",
    "IDXPX  = 收盘价(沪深300)"
    // GAIN/LOSE/TURN/VOLR/AMP/ADV/DEC/LU/LD 的公式写法依赖平台的成分股池与排行/计数函数，
    // 在 quant-buddy-skill 里确认「指数成分股池」「涨跌幅排行」「换手率」「量比」「振幅」「涨跌家数」对应的真实函数后再落公式。
  ],
  "begin_date": 20250501,
  "user_query": "生成沪深300成分股异动监控看板"   // 换指数时同步改这句，别留旧资产名
}
```

> 换指数（如中证500/上证50/科创50/自定义股票池）时：替换所有指数名与成分池口径，并把 `user_query` 改成当前请求；需要 `task_id` 时新建，不要复用旧的。

## 二、注册公式任务包

确认公式出数后注册（UTF-8，中文务必走 `@file`），`reads` 与上面 output 契约对应：榜单 `last_day_stats`、指数序列 `range_data`、计数/涨跌幅也用 `last_day_stats`（返回 data 内部由 `QB.lastValue` 读取）。

```bash
python scripts/formula_package.py register @params.json
```

成功后本地落盘 `output/formula_packages/<package_id>.json`，含 `package_id` + `signature`。`signature` 是凭证，不要在最终对话里展示。

## 三、生成页面

准备一份 `compile_params.json`（UTF-8），用 `replacements` 替换指数信息与公式包凭证：

```json
{
  "template": "templates/index-anomaly/page.template.html",
  "out_file": "output/pages/<index>-anomaly.html",
  "replacements": {
    "__PAGE_TITLE__": "<指数>成分股异动监控",
    "__INDEX_NAME__": "<指数>",
    "__INDEX_EN__": "CSI 300 Anomaly Monitor",
    "__INDEX_COUNT__": "300",
    "pkg_xxxxxxxx": "pkg_xxx",
    "replace_with_signature": "从本地凭证文件复制，不要发给最终用户"
  }
}
```

```bash
python scripts/compile_bespoke_page.py @compile_params.json
```

如增删榜单，同步改 `PANELS` 数组与公式包 outputs。

## 四、发布

发布前必须：

1. 页面已经由 `compile_bespoke_page.py` 生成，公共 share shell、`qr-mini.js` 和 `data-kernel.js` 均已内联。
2. `CONFIG.endpoint` 用 `https://`，否则发布到 `https://pages.quantbuddy.cn` 会被浏览器拦 mixed content。

```bash
python scripts/static_page.py upload '{"html_file":"output/pages/<index>-anomaly.html","title":"<指数>成分股异动监控"}'
```

## 发布前自查

- [ ] 公式已在 `quant-buddy-skill` 真跑通过、确认出数。
- [ ] 所有 `__INDEX_*__` 占位与 `CONFIG` 已替换，无残留示例文案。
- [ ] 榜单 `*` 用 `last_day_stats`，指数 `IDXPX` 用 `range_data` 且读取带 `{dropZero:true}`。
- [ ] 涨跌幅/计数类 0 是合法值，不做 `dropZero`。
- [ ] 页面有错误槽，`QB.query` 抛错时显示「取数失败：…」。
- [ ] 线上发布使用 HTTPS endpoint，且页面没有本地公共组件或 `data-kernel.js` 外链。
- [ ] 页头固定为 `QuantBuddy · 宽宝`，按钮为 `刷新数据 / 分享 / 开始使用`，移动端无横向溢出。
- [ ] 分享按钮能生成可复制/下载的 PNG 海报，二维码尺寸可扫。
- [ ] 未把 `signature` 打印进面向最终用户的聊天回复。
