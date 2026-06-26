---
name: quant-buddy-view
slug: quant-buddy-view
author: guanzhao
version: 0.3.0
description: |
  把量化数据做成「可分享的网页看板」。配合 quant-buddy-skill 使用：先在 quant-buddy-skill 里探索行情/因子/回测，
  确定要持续展示的指标后，用本技能把这些指标注册成「公式任务包」（底层数据更新即自动重算），
  定义看板的取数与渲染方式，生成一份 live 实时取数 HTML 看板，并上传托管得到一个公开可分享的链接。
  适用：行情异动监控页、因子/策略净值看板、上市公司画像卡、定期复盘报告页等。
  典型链路：用户需求 → quant-buddy-skill 探索 → 本技能 注册公式包 + 生成看板 + 发布 → 分享链接。
runtime: python
primaryCredential: quant-buddy API Key
metadata:
  version: 0.3.0
  author: guanzhao
  category: quant-finance
  tags: [quant, dashboard, formula-package, static-page, publish, visualization]
  runtime: python
  primaryCredential: quant-buddy API Key
  requiredCredentials:
    - quant-buddy API Key
  requiredConfigPaths:
    - config.json
  networkEndpoints:
    - https://www.quantbuddy.cn/skill
    - https://www.quantbuddy.cn/user
requiredCredentials:
  - name: quant-buddy API Key
    required: true
    sensitive: true
    storage: config_file
    path: config.json
    field: api_key
    description: quant-buddy 平台 API Key。存储于 skill 目录下 config.json 的 `api_key` 字段（也可用环境变量 QUANT_BUDDY_API_KEY）。仅作为 HTTP `Authorization` 头发送给 networkEndpoints 中声明的 quantbuddy 域名用于鉴权；公式包「取数」和看板内实时取数凭 signature，不需要 api_key。
    how_to_get: "https://www.quantbuddy.cn/login"
requiredConfigPaths:
  - path: config.json
    required: true
    description: 仅包含 quant-buddy api_key 与公开端点配置，由本地脚本读取。
requiredEnvVars:
  - name: QUANT_BUDDY_API_KEY
    required: false
    sensitive: true
    description: 可选。覆盖 config.json 里的 api_key。
networkAccess: true
networkEndpoints:
  - https://www.quantbuddy.cn/skill
  - https://www.quantbuddy.cn/user
runtimeRequirements:
  python: "3.8+"
  packages: []
---

# quant-buddy-view · 量化看板发布

把「在 quant-buddy-skill 里探索得到的指标」沉淀成一个**公开可分享的网页看板**。本技能不做行情查询/回测探索（那是 quant-buddy-skill 的职责），只负责三件事：

1. **注册公式任务包**（`formula_package`）—— 把一组公式 + 各产出的读取模式注册到服务端，拿到 `package_id` + `signature`。底层数据更新后服务端自动重算，取数永远是最新结果。
2. **生成看板 HTML**（`build_dashboard`）—— 用一份 spec 描述「哪些产出、用什么图表/表格展示」，编译成一份 live 实时取数 HTML（骨架自包含、数据打开时实时取）。
3. **发布托管**（`static_page`）—— 把 HTML 上传到对象存储，得到 `https://pages.quantbuddy.cn/...` 公开链接。

## 何时用本技能 vs quant-buddy-skill

- **探索/一次性查询**（"茅台今天涨跌幅"、"跑个均线金叉回测看看"）→ 用 **quant-buddy-skill**。
- **要一个能反复看、能发给别人、数据会自动更新的页面** → 探索清楚后切到 **quant-buddy-view**。

## 入口选择（先判断类型）

> Agent 路由规则：用户要一个**具体页面形态** → 先看 `templates/`；用户要从需求做到链接 → 看 `workflows/`；用户要复杂自定义页面或迁移旧 HTML → 看 `guides/`。

| 类型 | 展示名 | 入口 | 什么时候用 |
|---|---|---|---|
| 页面模板 | 个股速览 | [templates/single-stock/](templates/single-stock/README.md) | 单标的画像页：阅读摘要 + 最新价/涨跌幅/20日/60日/PE/PB/成交额数字卡 + 价格主图；必须从 `spec.template.json` 起步 |
| 页面模板 | 个股估值体检 | [templates/valuation-financial-profile/](templates/valuation-financial-profile/README.md) | 单标的估值财务页：PE/PB/PCF 历史水位、财务趋势、现金流质量、估值变动归因；配套 `page.template.html` |
| 页面模板 | 成分股异动榜 | [templates/index-anomaly/](templates/index-anomaly/README.md) | 指数/股票池成分股异动监控：异动榜单 + 涨跌分布 + 指数走势；配套 `page.template.html`，深色盘面、data-kernel 取数 |
| 页面模板 | 多因子选股看板 | [templates/multi-factor-screener/](templates/multi-factor-screener/README.md) | 主题股票池 + 多因子评分 + TopN 榜单 + 回测/rankIC + K 线 + 公式审计；固定角色 `RANK` / `BACKTEST` / `KLINE_*`，RANK 首屏优先渲染 |
| 页面模板 | 商品多空日报 | [templates/commodity-daily/](templates/commodity-daily/README.md) | 商品期货日报：板块多空主导矛盾 + 今日异动 + 头部品种 sparkline；配套 `page.template.html` |
| 页面模板 | 泡沫监测终端 | [templates/bubble-watch/](templates/bubble-watch/README.md) | 市场状态页：综合温度 gauge 仪表盘 + 多市场泡沫水位横截面 + 宏观背景；回答“现在是不是泡沫/市场太热/风险温度计/估值水位”，非单标的画像；bespoke 模板 |
| 通用流程 | 标准实时看板 | [workflows/dashboard-end-to-end.md](workflows/dashboard-end-to-end.md) | 用户要“做成可分享看板/链接”，但没有指定固定页面模板 |
| 开发指南 | 自定义页面 | [guides/bespoke-page.md](guides/bespoke-page.md) | `build_dashboard` 做不出的自定义 HTML/CSS/SVG 页面，或迁移已有 HTML |
| 迁移工具 | 旧页套公共外壳 | [tools/retrofit_share_shell.md](tools/retrofit_share_shell.md) | 已发布/已生成 HTML 需要去掉旧二维码、旧页头、旧页尾，并保留同一个 `page_id` 更新 |

> 硬规则：用户要“某只股票/指数画像页、个股画像、单股画像、单标的页面”时，先读 `templates/single-stock/README.md`，复制 `templates/single-stock/spec.template.json` 作为 spec 起点，保留 `template: "single-stock"`。不要手写旧版“1 条价格线 + 4 个数字卡”的最小 spec；`build_dashboard` 会拒绝这种旧骨架。
> 硬规则：用户问“这只股票贵不贵 / 基本面是否改善 / 估值与财务画像 / PE/PB历史水位 / 财务趋势 / 现金流质量”并要求做成落地页或公开链接时，先读 `templates/valuation-financial-profile/README.md`，复制 `templates/valuation-financial-profile/page.template.html` 起步，验证并注册该模板要求的一套公式包；不要退回普通 `single-stock` 卡片页。
> 硬规则：用户要“某指数 / 某股票池 的成分股异动、异动榜、龙虎榜式排行”（如「中证500今天哪些股票异动」「沪深300异动监控」「上证50涨跌幅榜」）时，先读 `templates/index-anomaly/README.md`，复制 `templates/index-anomaly/page.template.html` 起步，替换 `__INDEX_*__` 占位并内联 `data-kernel.js` 再发布；不要手写一份离题的浅色/通用 HTML。
> 硬规则：用户要“主题股票池 / 概念股 / 行业池 + 多因子评分 / TopN / 回测 / rankIC / K线 / 公式审计”的选股工作台页面时，先读 `templates/multi-factor-screener/README.md`，复制 `templates/multi-factor-screener/page.template.html` 起步；公式包角色固定为 `RANK` / `BACKTEST` / `KLINE_*`，`RANK` 必须首屏优先渲染，`BACKTEST` 和 `KLINE_*` 允许局部降级。
> 硬规则：单标的画像页的 `subtitle` 和“阅读摘要”只能使用 `build_dashboard` 构建期实时取数结果（最终 outputs）对应的数值。若脚本返回“文案与实时取数结果不一致”，按返回的 `facts` 重写文案后再生成/上传，不要沿用旧查询结果或手工估算。
> 硬规则：所有落地页必须接入 `templates/_shared/share-shell/` 公共组件。模板只负责主体内容和 `getPosterData()`，页头、页尾、刷新按钮、分享海报弹层、复制链接、复制/下载 PNG 和海报固定页头页尾都由公共 shell 提供；不要在单个模板里私自复制或改造旧二维码块、旧刷新按钮或旧分享弹层。
> 硬规则：分享海报由公共 `poster.js` 默认前端截图页面主体生成，宁缺毋滥；模板可用 `data-qb-poster-target` 标记核心截图区域，`getPosterData()` 只提供标题/摘要和结构化兜底候选，不要依赖 Agent 手写海报版式，也不要把整页内容塞进 `sections`。
> 硬规则：用户要“改造已经生成的 HTML / 去掉二维码 / 去掉当前页头页尾 / 适配固定页头页尾”时，优先用 `scripts/retrofit_share_shell.py`。不要靠长提示词让 Agent 手工删 DOM；默认保留旧页面主体 hero 区域，只移除其中的二维码卡片和旧页尾，然后在 `body` 顶部/底部直接插入公共页头页尾；先生成本地迁移版验证，再用 `update:true` 覆盖同一个 `page_id`。

1. **注册公式任务包**（`scripts/formula_package.py register`）
   - `formulas`：一组 `"变量名 = 表达式"`（沿用 quant-buddy-skill 探索时验证过的公式）。
   - `reads`：对外产出清单，每条声明 `output`（产出名）+ `read_mode`（读取模式）。
   - 成功返回 `package_id` + `signature`，并自动落盘到 `output/formula_packages/<package_id>.json`。
   - ⚠️ `signature` 只在注册时明文返回一次，本地凭证丢失即不可恢复（可 `refresh` 轮换）。

2. **生成看板**（`scripts/build_dashboard.py`）
   - 写一份 spec：`title` + `panels[]`，每个 panel 把某个 `output` 渲染为 `line`/`bar`/`table`/`number`/`text`/`raw`。
   - 若命中页面模板，先复制模板目录里的 `spec.template.json` 或 `page.template.html`，再替换资产、日期、解读文案和可选模块。
   - 页面是实时取数的（见下「取数：实时取数」），spec 里不用写 `mode`。
   - 产物默认写到 `output/pages/<slug>.html`；传 `"upload": true` 可一步生成并发布。

3. **发布 / 管理**（`scripts/static_page.py`）
   - `upload`：上传 HTML → 返回 `page_id` + 公开 `url`；可带 `title`（缺省取 `<title>`）和 `description`（页面说明，≤1000 字，列表/详情展示用）。
   - `update`：替换已发布页面的内容，**URL / page_id 不变**（页面已分享后想补充/调整时用，访问者刷新即见新内容，不占新配额）。也可只改 `title` / `description`（`description` 传空串 `""` 清空，不传保留原值）。
   - `download`：取回已发布页面的 HTML 再编辑（鉴权拿 url → 直连 OSS 下载，不占服务端带宽），改完 `update` 覆盖。
   - `list` / `revoke`：列出 / 撤销我的页面（活跃页上限 10，单页 ≤ 2MB）。
   - `thumbnail`：给某个已发布页面设置 / 替换一张**纯展示封面图**（直传 PNG/JPG，≤2MB）。只用于列表/详情/模板墙的 `<img>` 预览，**不进入 HTML、不影响取数、不占活跃页配额**；按 page_id 命名存 OSS，转模板后仍有效。可选锦上添花，不是发布必需。
   - `templates` / `template`：**浏览 / 复用公共模板**——`templates` 列模板（普通用户只见 published），`template` 看某模板详情拿 `download_url`，直连 OSS 取回 HTML，换成自己的标的/文案/公式包后再 `upload` 成自己的页。
   - `upload` / `update` 发布前会强制检查公共 share shell；缺公共页头/页尾会自动插入并编译，主题色只能通过 `theme` / `--qb-shell-*` 变量覆盖，仍有占位符或旧二维码残留则拒绝发布。
   - 权限 / 权责：自己的页面默认仅本人；`is_test` 用户可跨 download / update / thumbnail 其他 is_test 用户页面、`list` 传 `scope=test_all` 看全部 test 用户（普通用户页面一律 `FORBIDDEN`）。**公共模板浏览/复用对全员开放**（普通用户只读 published）；模板的提交/改写/上下线仅 is_test，把已有页转公共模板是后台（growthX）动作——本 skill 侧只「读取 + 复用」模板，不做这些写操作。

> 认证只靠 `config.json` 的 `api_key`（query 取数连 api_key 都不需要，凭 package_id + signature）。本技能不维护会话 / task_id。

## 取数：实时取数

看板是实时取数的：HTML 内嵌 `package_id + signature`，访问者打开页面时即时调用 `queryFormulaPackage` 拉取最新数据并渲染——底层数据更新即自动重算，**页面打开就是最新**，这正是公式任务包的设计目的。spec 不需要写 `mode` 字段。

- **页面是"活"的**：数据不焊进 HTML，运行时实时取；构建期只取一次数做质量体检（数据健康 + 单标的文案一致性），不内联。
- **两个前提（均已满足）**：① `queryFormulaPackage` 端点对页面域名 `pages.quantbuddy.cn` 放开 **CORS**（当前 https 端点已放开 `*`）；② `signature` 随页面公开（公式包 query 本就以 signature 作能力令牌、设计上允许嵌入页面）。
- ⚠️ **协议必须一致**：页面发布在 `https://`，`config.json` 的 `endpoint` 也必须是 `https://`，否则浏览器会以 mixed-content 拦截取数。当前 endpoint 已是 `https://test.quantbuddy.cn/skill`。

## 硬规则

1. **中文参数走 @file 或环境变量**：Windows PowerShell 命令行直接传中文会被 GBK 截断。注册公式、写 spec 一律用 `@params.json`（UTF-8）或 `FP_PARAMS/BD_PARAMS/SP_PARAMS` 环境变量。
2. **公式必须先验证再注册（硬门槛）**：提交注册的每一组公式，**必须先在 quant-buddy-skill 里用 `runMultiFormulaBatchStream` 跑一遍并确认出数**（公式语法两边一致，可原样验证），跑成功才允许 `register`。不要凭空发明未验证的表达式，也不要"直接注册、错了再说"——注册时的服务端试读只是兜底，不替代这一步。
3. **验证参数也要换干净**：调用 `runMultiFormulaBatchStream` 时，`user_query` 必须反映当前用户请求和当前资产；若传 `task_id` 必须为本次新任务。复制示例时不能只替换 `formulas`，却留下“贵州茅台 factsheet”等旧 `user_query`，否则后台审计和回放会被污染。
4. **signature 是凭证**：不要打印到面向最终用户的对话里；看板会把它写进公开 HTML 供实时取数，发布前确认可接受。
5. **失败要说清**：脚本返回 `code != 0` 时，向用户复述「卡在哪一步（命令名）+ 错误摘要」，不要以空白或纯日志结束。

## 工具一览

> 参数约定：所有脚本参数是**一个 JSON 字符串**位置参数（或 `@params.json` / 环境变量），如 `list '{"scope":"test_all"}'`。命令行也兼容 `--scope test_all` / `--key=value` 直觉写法（仅简单参数；公式、spec 等复杂结构仍走 `@file`/环境变量以免 GBK 截断）。

| 脚本 | 命令 | 作用 | 文档 |
|---|---|---|---|
| `scripts/formula_package.py` | `register` / `query` / `list` / `revoke` / `refresh` | 公式任务包：注册取数能力，凭包凭证流式取数 | [tools/formula_package.md](tools/formula_package.md) |
| `scripts/build_dashboard.py` | （单命令） | spec → live 实时取数看板 HTML | [tools/build_dashboard.md](tools/build_dashboard.md) |
| `scripts/compile_bespoke_page.py` | （单命令） | bespoke 模板 → 内联公共 share shell / logo / qr-mini / data-kernel 的自包含 HTML | [guides/share-shell.md](guides/share-shell.md) |
| `scripts/retrofit_share_shell.py` | （单命令） | 旧 HTML/已发布页面 → 删除旧二维码/旧页头/旧页尾，套入公共 share shell，可原链接 update | [tools/retrofit_share_shell.md](tools/retrofit_share_shell.md) |
| `scripts/static_page.py` | `upload` / `update` / `download` / `list` / `revoke` / `thumbnail` / `templates` / `template` | 发布/替换/下载/管理静态页，得到公开链接（`update` 替换内容不换链接；`download` 取回 HTML 再编辑；`thumbnail` 设展示封面；`templates`/`template` 浏览复用公共模板；is_test 可跨用户） | [tools/static_page.md](tools/static_page.md) |
| `scripts/verify_page.mjs` | （单命令） | 发布前/发布后页面验收：1440px、390px、320px 视口，h1、占位符、横向溢出、控制台核心错误 | — |
| `assets/data-kernel.js` | （前端内核，非脚本） | 手搓 bespoke 页共用的「取数 + 清洗 + 容错」一份；内联进页面 `<script>` 用 | [guides/bespoke-page.md](guides/bespoke-page.md) |
| `templates/_shared/share-shell/` | （公共组件） | 所有落地页共用的页头、页尾、刷新按钮、分享海报弹层、海报 canvas、复制链接与复制/下载行为 | [guides/share-shell.md](guides/share-shell.md) |
| `templates/valuation-financial-profile/page.template.html` | （页面模板，非脚本） | 个股估值体检：估值水位、财务趋势、估值天平归因 | [templates/valuation-financial-profile/README.md](templates/valuation-financial-profile/README.md) |
| `templates/index-anomaly/page.template.html` | （页面模板，非脚本） | 成分股异动榜：异动榜单、涨跌分布、指数 sparkline | [templates/index-anomaly/README.md](templates/index-anomaly/README.md) |
| `templates/commodity-daily/page.template.html` | （页面模板，非脚本） | 商品多空日报：多空主导、异动榜、板块条、sparkline | [templates/commodity-daily/README.md](templates/commodity-daily/README.md) |

> **两条生产路**：标准看板走 `build_dashboard`（声明式快路）；要自定义版式/SVG 的设计页则**手搓 HTML**，
> 数据层统一调 `assets/data-kernel.js`（`QB.query` 取数、`QB.series/lastValue/topValues` 解包清洗），别再每页各抄 `fetch`/解包、各踩"假 0/缺口"的坑。见 [guides/bespoke-page.md](guides/bespoke-page.md)。
> 发布前用 `scripts/verify_page.mjs <html_file>` 检查桌面与 390px/320px 移动端，确保无 `QB_SHARED_` / `replace_with_signature` / `pkg_replace` 残留、存在 `<h1>`、无关键横向溢出和核心取数脚本错误。

## 配置

`config.json`：填入 `api_key`（从 https://www.quantbuddy.cn/login 获取），或设环境变量 `QUANT_BUDDY_API_KEY`。可建 `config.local.json` 覆盖 `endpoint` / `api_key` 等（不入库）。`formula_package.py`、`build_dashboard.py`、`static_page.py` 共用同一个 `endpoint`。
