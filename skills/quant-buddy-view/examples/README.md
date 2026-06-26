# 离线参考模板（Offline reference templates）

> **线上模板优先**：用户提到模板市场 / 官方模板 / 公共模板 / 已发布模板时，先走在线接口
> `scripts/static_page.py templates`（列模板）/ `template`（取详情 + `download_url`），直连 OSS 下载 HTML，
> 替换标的/文案/公式包凭证后再 `upload`。
>
> **本目录的定位**：上述线上模板的**离线兜底**与**模板开发源**。当用户要一个具体页面形态、但没指明公共模板，
> 或线上接口不可用时，从这里挑一个最贴近的形态起步。

每个模板独占一个目录：

```text
examples/<template-name>/
  README.md              # 何时用它、数据契约、Agent 可编辑槽位
  spec.template.json     # 标准 build_dashboard 页面用（适用时）
  page.template.html     # bespoke 自定义 HTML 页面用（适用时）

assets/share-shell/      # 所有落地页共用的页头/页尾/分享弹层组件（不是模板，是公共组件）
  shell.html             # 公共页头、页尾、分享弹层结构
  shell.css              # 公共外壳样式
  shell.js               # 刷新/分享/复制/下载绑定
  poster.js              # 固定版式海报 canvas 渲染器 + 动态主体适配
```

| 展示名 | 模板 slug | 何时选它 | 渲染路径 |
|---|---|---|---|
| 个股速览 | `single-stock/` | 单只股票/指数画像页：价格走势 + 估值/活跃度卡片 | `build_dashboard` spec |
| 个股估值体检 | `valuation-financial-profile/` | 单标的估值与基本面落地页：PE/PB/PCF 水位、财务趋势、现金流质量、估值归因 | bespoke HTML 模板 + `data-kernel.js` |
| 商品多空日报 | `commodity-daily/` | 商品期货日报：板块多空矛盾、异动品种、sparkline | bespoke HTML 模板 + `data-kernel.js` |
| 成分股异动榜 | `index-anomaly/` | 指数成分股异动监控：涨/跌/换手/量/振幅榜单、涨跌分布、指数走势 | bespoke HTML 模板 + `data-kernel.js` |
| 市场泡沫水位 | `bubble-watch/` | 多市场泡沫/过热水位监控：综合水位表 + 各市场偏向/仓位条 + 宏观背景 | bespoke HTML 模板 + `data-kernel.js` |
| 多因子选股看板 | `multi-factor-screener/` | 主题股票池 + 多因子评分 + TopN 榜单 + 回测/rankIC + K 线 + 公式审计 | bespoke HTML 模板 + `data-kernel.js` |

若没有任何模板匹配用户要的页面形态，用 `../workflows/dashboard-end-to-end.md` 走标准面板，或 `../guides/bespoke-page.md` 做自定义 HTML。

所有落地页都必须接入 `../assets/share-shell/`。模板可以自定义主体布局与数据解读，但不得自行 fork QuantBuddy 页头、页尾、主体二维码块、刷新按钮或分享海报弹层。bespoke 页面发布/本地验证前应先用 `scripts/compile_bespoke_page.py` 编译。

模板使用准则：数据契约与布局骨架保持稳定，但把标题、摘要、解读文案、风险提示、面板说明、可选面板增补留作 Agent 可编辑字段。

Agent 弹性契约：

| 区域 | 保持稳定 | Agent 可定制 |
|---|---|---|
| 数据契约 | output 名、read 模式、必需公式校验、query/解包辅助 | 目标标的、日期窗口、可选额外 output |
| 布局骨架 | 页面分区、响应式约束、公共外壳、`getPosterData()`、错误/加载态 | 用户意图明确时的分区顺序、可选面板/模块 |
| 文案 | 不留陈旧占位文案、不编造结论、不暴露 signature | 标题、副标题、摘要、解读、风险提示、面板说明 |
| 视觉系统 | QuantBuddy 品牌外壳、页头操作、分享海报结构、桌面/移动可读布局 | 强调色文案、图表侧重、模板视觉语言内的 bespoke 细节 |

新增模板时，在此目录下新建一个子目录，而不是放一个散落的 markdown。子目录 README 应回答下一个 Agent 的三个问题：何时选它、需要哪些数据 output、哪些页面区域是有意可编辑的。
