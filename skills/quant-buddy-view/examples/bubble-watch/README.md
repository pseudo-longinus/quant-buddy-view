# Template · 泡沫监测终端（多市场泡沫水位 + 宏观背景）

> 场景：用户问「现在 A 股是不是泡沫了」「市场是不是太热了 / 该不该减仓」「估值水位 / 拥挤度 / 风险温度计」「全球哪个市场最热」「创业板 / 纳指泡沫到什么程度」。
> 这是 **bespoke 页面模板**：核心是「一个综合温度读数（gauge 仪表盘）+ 多市场泡沫水位横截面 + 宏观背景面板」。它回答的是**市场状态（过热 / 泡沫 / 风险）**，不是单标的画像，也不是当日榜单。

## 何时选这个模板（vs 其它模板）

| 用户想要 | 选哪个 |
|---|---|
| 「贵州茅台 / 沪深300 做个画像页」（单标的 KPI + 价格线） | `single-stock` |
| 「茅台贵不贵 / 基本面有没有改善」（单标的估值 + 财务趋势） | `valuation-financial-profile` |
| 「商品期货今天哪个板块强 / 弱」（当日横截面异动） | `commodity-daily` |
| 「沪深300 今天哪些成分股涨跌 / 换手 / 放量榜」（成分股榜单） | `index-anomaly` |
| **「现在是不是泡沫 / 市场太热了 / 风险温度计 / 估值水位」** | **`bubble-watch`（本模板）** |

判定关键语义：出现 **泡沫 / 过热 / 拥挤 / 估值分位 / 风险溢价 / 市场水位 / 情绪 / 该不该减仓** 这类「市场状态温度」诉求，才路由到本模板。

不要选它的反例：

- 「茅台贵不贵」→ 单标的估值与财务画像，走 `valuation-financial-profile`（除非用户明确要「市场整体泡沫水位」）。
- 「今天哪些股票涨停 / 涨幅榜」→ `index-anomaly`。
- 「商品期货今天怎么走」→ `commodity-daily`。

## 这个模板的「形状」

- **市场池基本固定**为 7 个主流指数：A 股 `SH`(上证)/`HS3`(沪深300)/`CYB`(创业板)/`KC5`(科创50)、港股 `HSI`(恒生)、美股 `NDX`(纳指100)/`SPX`(标普500)。换市场池 = 改公式包，成本高，不是「随手换标的」型模板。
- **hero**：主 gauge 仪表盘（综合 / 用户关注的某个市场的泡沫读数）+ 7 市场泡沫水位横向对比条，使用深色实时看板结构。
- **泡沫场**：用横轴展示历史分位，用泡泡大小展示偏离均线程度；颜色只表达冷热区间，不表达涨跌。
- **支撑面板**：宏观背景（中美利率 / 利差 / 美元 / VIX / M2 / 社融）、流动性与情绪驱动（利率 / 利差 / VIX / A 股成交额）、头部指数走势（纳指100 / 沪深300 / 恒生），解释「钱为什么热 / 为什么撤」。

## 公式包 output 契约（已对线上真实包核对）

本模板用**两个公式包**：`froth`（泡沫水位）+ `macro`（宏观背景）。

### froth —— 各市场泡沫读数

| output | 含义 | read_mode | 读取 |
|---|---|---|---|
| `<MKT>_bias` | 该市场当前乖离度（偏离均线的泡沫度） | `last_day_stats` | `QB.lastValue` |
| `<MKT>_pos` | 该市场在历史区间的位置 / 分位（水位） | `last_day_stats` | `QB.lastValue` |
| `NDX_px` / `HS3_px` / `HSI_px` | 代表性指数价格序列 | `range_data` | `QB.series(o,k,{dropZero:true})` |
| `A_turnover` | A 股成交额序列（情绪 / 流动性代理） | `range_data` | `QB.series(o,k,{dropZero:true})` |

> `<MKT>` ∈ `SH / HS3 / CYB / KC5 / HSI / NDX / SPX`，`_bias` 与 `_pos` 各一套（共 14 个 `last_day_stats` 单值输出）。

### macro —— 宏观背景 / 流动性 / 风险

| output | 含义 | read_mode | 读取 |
|---|---|---|---|
| `CN10Y_now` / `US10Y_now` | 中 / 美 10 年期国债收益率 | `last_day_stats` | `QB.lastValue` |
| `SPREAD_now` | 中美利差 | `last_day_stats` | `QB.lastValue` |
| `DXY_now` | 美元指数 | `last_day_stats` | `QB.lastValue` |
| `VIX_now` | 恐慌指数 | `last_day_stats` | `QB.lastValue` |
| `M2_now` / `SF_now` | M2 / 社融 | `last_day_stats` | `QB.lastValue` |
| `CN10Y_px` … `SF_px` | 上述每项的序列 | `range_data` | `QB.series(o,k,{dropZero:true})` |

> 利率 / 利差 / 收益率类 0 可能是合法值，spark 用 `dropZero` 仅对「价格 / 点位 / 成交额」类开；对收益率序列按数据含义谨慎。

## 稳定 vs Agent 可编辑

可以改（Agent customizable）：

- 标题、副标题、解读文案、风险提示、面板描述；
- gauge 中心用哪个市场（或综合）做主读数；
- 7 市场对比条的展示顺序、泡沫场强调文案、宏观 / 流动性 / 情绪维度的取舍与强调；
- 视觉细节、配色强调（但保持模板视觉语言：深色品牌外壳 + 浅色内容面 + 金色做结构强调）。

不要随意改：

- output 命名约定（`<MKT>_bias`/`<MKT>_pos`/`*_now`/`*_px`/`A_turnover`）与 `read_mode`；
- `QB.query(CONFIG)` / `QB.lastValue` / `QB.series` 的取数路径；
- 发布前用 `scripts/compile_bespoke_page.py` 内联公共组件与 `assets/data-kernel.js` 的要求；
- `signature` 不对最终用户展示的规则；
- share shell 的页头、页尾、刷新、分享海报、开始使用入口（`https://www.quantbuddy.cn`）。

## 视觉规范（与 guides/share-shell.md 对齐）

- 页头与内容主体统一使用**深色实时看板**视觉；顶部公共 share shell 固定展示 QuantBuddy 品牌、刷新、分享和开始使用入口。
- 红 / 绿只用于市场方向；**金色用于 gauge 的泡沫 / 危险区与结构强调**，不表达涨跌含义。
- gauge 是本模板的招牌视觉，泡沫场是第二招牌视觉；两者都应保留，避免退回纯报告卡片。

## 一、先验证公式（必须）

注册公式包**之前**，先在 `quant-buddy-skill` 里用 `runMultiFormulaBatchStream` 跑通、确认 `froth` 与 `macro` 的全部 output 出数。`user_query` 写当前请求（如「生成多市场泡沫监测看板」），换市场 / 口径时同步改，别留旧资产名；需要 `task_id` 时新建，不要复用旧的。

## 二、注册公式任务包

```bash
python scripts/formula_package.py register @params.json
```

成功后本地落盘 `output/formula_packages/<package_id>.json`，含 `package_id` + `signature`。`signature` 是凭证，不要在最终对话里展示。本模板有两个包，分别注册得到 froth / macro 的凭证。

## 三、生成页面

准备一份 `compile_params.json`（UTF-8），用 `replacements` 替换标题与两套公式包凭证：

```json
{
  "template": "examples/bubble-watch/page.template.html",
  "out_file": "output/pages/bubble-watch.html",
  "replacements": {
    "__PAGE_TITLE__": "泡沫监测终端",
    "pkg_xxxxxxxx_froth": "pkg_froth_xxx",
    "pkg_xxxxxxxx_macro": "pkg_macro_xxx",
    "replace_with_signature_froth": "froth 包 signature，从本地凭证文件复制",
    "replace_with_signature_macro": "macro 包 signature，从本地凭证文件复制"
  }
}
```

```bash
python scripts/compile_bespoke_page.py @compile_params.json
```

如需改标题 / 解读 / 风险提示文案，先改模板或在 `replacements` 里增加对应占位。

## 四、发布

发布前必须：

1. 页面已经由 `compile_bespoke_page.py` 生成，公共 share shell、`logo.svg`、`qr-mini.js` 和 `data-kernel.js` 均已内联。
2. `CONFIG.*.endpoint` 用 `https://`，否则发布到 `https://pages.quantbuddy.cn` 会被浏览器拦 mixed content。

```bash
python scripts/static_page.py upload '{"html_file":"output/pages/bubble-watch.html","title":"泡沫监测终端"}'
```

## 发布前自查

- [ ] froth / macro 公式已在 `quant-buddy-skill` 真跑通、确认出数。
- [ ] 所有 `__PAGE_TITLE__` 等占位与两套 `CONFIG` 已替换，无残留示例文案。
- [ ] 价格 / 点位 / 成交额序列用 `range_data` 且读取带 `{dropZero:true}`；收益率 / 利率类按含义处理 0。
- [ ] 页面有错误槽，`QB.query` 抛错时显示「取数失败：…」而不是空白或假图。
- [ ] 线上发布使用 HTTPS endpoint，且页面没有本地公共组件、`logo.svg`、`qr-mini.js` 或 `data-kernel.js` 外链。
- [ ] 页头固定为 `QuantBuddy · 宽宝`，按钮为 `刷新数据 / 分享 / 开始使用`，红绿只用于方向、金色用于结构。
- [ ] 分享按钮能生成可复制/下载的 PNG 海报，二维码尺寸可扫。
- [ ] 未把 `signature` 打印进面向最终用户的聊天回复。
