---
name: quant-buddy-view
slug: quant-buddy-view
author: guanzhao
version: 0.4.8
description: |
  QBV / quant-buddy-view（用户可能写成 /quant-buddy-view、/qbv、qbv 或 QBV）用于把量化数据做成「公开可分享、实时取数」的网页看板/落地页。
  Use this skill when the user asks to create, update, publish, verify, retrofit, or reuse a Quant Buddy dashboard/static page/template, including shareable pages, public URLs, formula packages, thumbnails, share shell, cover/essence cards, poster/share behavior, single-stock profile pages, valuation/financial profile pages, index-anomaly boards, multi-factor screeners, and commodity daily pages.
  配合 quant-buddy-skill 使用：固定页面请求先用 static_page.py templates/template 选择带 recommend:官方精选 标签的在线精选页；实时取数页必须先在 quant-buddy-skill 验证公式并确认其 api_key 可用，再用本技能注册自有公式包、替换凭证/文案、浏览器验收，并通过 static_page.py upload/update 发布或更新 pages.quantbuddy.cn 链接。默认不从本地历史样板目录或低质 HTML 骨架起步。
  Do not use this skill for one-off 行情查询、普通股票涨跌幅/估值问答、选股/回测探索；those belong to quant-buddy-skill unless the user explicitly wants a reusable/shareable page.
runtime: python
primaryCredential: quant-buddy API Key
metadata:
  version: 0.4.8
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

把「已验证的量化数据与公式」沉淀成一个**公开可分享、实时取数**的网页看板/落地页。本技能不做一次性行情查询或回测探索；默认执行路线是：

1. 先用 `scripts/static_page.py templates` / `template` 筛选在线官方精选页（后台 `recommend:官方精选` 标签）。
2. 用 quant-buddy-skill 验证模板或页面需要的公式，确认真实出数。
3. 用 `scripts/formula_package.py register` 注册当前用户自己的公式包。
4. 替换模板/HTML 里的标的、文案、`package_id`、`signature`。
5. 发布前跑 `scripts/verify_page.mjs <html_or_url> --require-browser` 做浏览器验收；`static-only` 不能算完整验收。
6. 用 `scripts/static_page.py upload` 创建新链接，或用 `update` 覆盖原 `page_id` 且保持 URL 不变。

## 何时用本技能 vs quant-buddy-skill

- **探索/一次性查询**（"茅台今天涨跌幅"、"跑个均线金叉回测看看"）→ 用 **quant-buddy-skill**。
- **要一个能反复看、能发给别人、数据会自动更新的页面** → 探索清楚后切到 **quant-buddy-view**。

## 默认路由

- **固定页面形态**（个股速览、估值体检、成分股异动榜、多因子选股看板、商品日报等）：先 `templates` 列表筛选后台打了 `recommend:官方精选` 的在线精选页，再 `template` 取详情和 `download_url`。
- **宽宝活卡 / 精华卡 / 封面卡 / cover card**：先复用或改造目标 HTML，再按 [guides/essence-cover-card.md](guides/essence-cover-card.md) 接入固定 4:3 实时卡片；对外可叫「宽宝活卡」，但卡片内部不再内置可见的左上角品牌文案，左上角只预留官方标签位。默认完整页面不显示卡片，标准 URL 只传 `?cover=1` 进入卡片模式并隐藏其它元素；卡片必须是官网浅色系、固定信息骨架、可变核心可视化；不要新增 `ratio` / `gallery` 等尺寸参数。
- **没有合适在线模板**：再走 `workflows/dashboard-end-to-end.md`，用 `build_dashboard` 生成声明式实时看板。
- **声明式看板也不够**：才走 `guides/bespoke-page.md` 写 bespoke 主体 HTML，并用公共 shell 编译成自包含页面。
- **改造已发布/已生成页面**：优先 `scripts/retrofit_share_shell.py`，再 `static_page.py update` 保持同一个 `page_id` / URL。
- 本 skill 不再内置本地页面样板，不能从本地历史样板目录或低质 HTML 骨架起步。

## 前置依赖：公式必须先验证

本技能运行时自包含：注册/生成/发布只凭本技能 `config.json` 的 `api_key`。但注册公式包前，每组公式必须先在 quant-buddy-skill 里用 `runMultiFormulaBatchStream` 跑通确认出数；服务端试读只是兜底，不替代这一步。

如果当前环境没有 quant-buddy-skill，Agent 不要跳过验证或直接注册公式包。

普通已安装 skill 用户先检查全局 skills；缺失时运行安装命令，已安装但需要刷新时运行更新命令，二选一，不要连续执行：
```bash
npx skills list -g --json
# 未安装时
npx skills add pseudo-longinus/quant-buddy-skills -g --all
# 已安装、需要刷新时
npx skills update pseudo-longinus/quant-buddy-skills -y
```
- Windows 上若 symlink / `EPERM` 报错，在 `add` 命令末尾追加 `--copy` 重试。
- 在源码 checkout 或 junction 调试本 skill 时，不要运行上面的 bundle 级 `add --all` / `update` 覆盖当前 `quant-buddy-view`；只确认同级 `../quant-buddy-skill` 是否存在，缺失时先停下说明需要把 quant-buddy-skill 放到同级。
- 安装后必须确认 quant-buddy-skill 的 `config.json.api_key` 或 `QUANT_BUDDY_API_KEY` 可用；只报告“已配置/未配置/鉴权成功或失败”，不要打印 key 或完整 config。若鉴权失败，停下来说明 blocker，不要继续注册公式包。
- 若只是上传/改造一份无需公式包的静态 HTML，可继续使用本技能；凡是实时取数页面或公式包注册，都必须先补齐 quant-buddy-skill 验证步骤。

推荐让两个 skill 同级安装，便于验证公式和迁移旧公式包凭证：
```text
<skills 目录>/
  quant-buddy-skill/      ← 探索 / 公式验证（runMultiFormulaBatchStream、confirmDataMulti）
  quant-buddy-view/       ← 本技能：注册公式包 / 生成看板 / 发布
```

旧凭证迁移见 [tools/formula_package.md](tools/formula_package.md)。

## 入口选择（先判断类型）

> Agent 路由规则：用户要**生成 / 复用 / 发布 / 更新**可分享页面时，默认先用 `scripts/static_page.py templates` / `template` 读取在线官方精选页（由 `recommend:官方精选` 标签决定）；从 `template` 返回的 `download_url` 直连 OSS 下载 HTML，替换标的、文案、公式包凭证后，再验收并 `upload` 成用户自己的页面。用户要从需求做到链接 → 看 `workflows/`；用户要复杂自定义页面或迁移旧 HTML → 看 `guides/`。

| 类型 | 展示名 | 入口 | 什么时候用 |
|---|---|---|---|
| 页面模板 | 在线官方精选 | `scripts/static_page.py templates` / `template` | 个股速览、估值体检、异动榜、选股看板、商品日报等固定页面形态；按 `recommend:官方精选` 标签筛列表，再取详情下载 HTML 复用 |
| 封面组件 | 宽宝活卡 / 精华卡 / 封面卡 | [guides/essence-cover-card.md](guides/essence-cover-card.md) | 用户要把页面精华浓缩成 4:3 card、封面、缩略图源图、单独分享卡；卡片左上角仅留官方标签预留位，不显示固定品牌文案；默认隐藏，标准 URL 用 `?cover=1` 进入 card-only 模式 |
| 通用流程 | 标准实时看板 | [workflows/dashboard-end-to-end.md](workflows/dashboard-end-to-end.md) | 用户要“做成可分享看板/链接”，但没有指定固定页面模板 |
| 开发指南 | 自定义页面 | [guides/bespoke-page.md](guides/bespoke-page.md) | `build_dashboard` 做不出的自定义 HTML/CSS/SVG 页面，或迁移已有 HTML |
| 迁移工具 | 旧页套公共外壳 | [tools/retrofit_share_shell.md](tools/retrofit_share_shell.md) | 已发布/已生成 HTML 需要去掉旧二维码、旧页头、旧页尾，并保留同一个 `page_id` 更新 |

> 硬规则：用户要“某只股票/指数画像页、个股画像、单股画像、单标的页面”时，先用 `templates` 找个股画像/个股速览类在线模板，并用 `template` 取详情和 `download_url`。若没有合适在线模板，才使用 `build_dashboard` 自行构建，但必须保留 `template: "single-stock"` 并满足单标的模板契约；不要手写旧版“1 条价格线 + 4 个数字卡”的最小 spec，`build_dashboard` 会拒绝这种旧骨架。
> 硬规则：用户问“这只股票贵不贵 / 基本面是否改善 / 估值与财务画像 / PE/PB历史水位 / 财务趋势 / 现金流质量”并要求做成落地页或公开链接时，先用 `templates` 找个股估值体检/估值财务类在线模板，验证并注册该模板要求的一套公式包；不要退回普通 `single-stock` 卡片页。
> 硬规则：用户要“某指数 / 某股票池 的成分股异动、异动榜、龙虎榜式排行”（如「中证500今天哪些股票异动」「沪深300异动监控」「上证50涨跌幅榜」）时，先用 `templates` 找成分股异动榜类在线模板，再替换指数、文案和公式包凭证；不要手写一份离题的浅色/通用 HTML。
> 硬规则：用户要“主题股票池 / 概念股 / 行业池 + 多因子评分 / TopN / 回测 / rankIC / K线 / 公式审计”的选股工作台页面时，先用 `templates` 找多因子选股看板类在线模板；公式包角色固定为 `RANK` / `BACKTEST` / `KLINE_*`，`RANK` 必须首屏优先渲染，`BACKTEST` 和 `KLINE_*` 允许局部降级。
> 硬规则：复用官方精选页时，页面 HTML 里的 `package_id + signature` 属于原作者；必须按当前用户目标重新验证公式、注册自己的公式包，并替换页面里的凭证后再发布。不要把官方精选原凭证直接当成用户页面的数据来源。
> 硬规则：单标的画像页的 `subtitle` 和“阅读摘要”只能使用 `build_dashboard` 构建期实时取数结果（最终 outputs）对应的数值。若脚本返回“文案与实时取数结果不一致”，按返回的 `facts` 重写文案后再生成/上传，不要沿用旧查询结果或手工估算。
> 硬规则：所有落地页必须接入 `assets/share-shell/` 公共组件。页头、页尾、刷新按钮、分享海报弹层、复制链接、复制/下载 PNG 和海报固定页头页尾的唯一来源是 `assets/share-shell/shell.html`、`shell.css`、`shell.js`、`poster.js`；模板只负责主体内容和 `getPosterData()`，不要在单个模板里私自复制或改造旧二维码块、旧页头页尾、旧刷新按钮或旧分享弹层。
> 硬规则：分享海报由公共 `poster.js` 默认前端截图页面主体生成，宁缺毋滥；模板可用 `data-qb-poster-target` 标记核心截图区域，`getPosterData()` 只提供标题/摘要和结构化兜底候选，不要依赖 Agent 手写海报版式，也不要把整页内容塞进 `sections`。
> 硬规则：用户要“宽宝活卡 / 精华卡 / 封面卡 / card / cover / 缩略图源图 / 4:3 卡片”时，必须按 [guides/essence-cover-card.md](guides/essence-cover-card.md) 做成**同一份 HTML 内的实时卡片模式**：卡片数据复用页面同一轮 `QB.query` / `STATE` / outputs，不写死数值；默认完整页不显示卡片，标准 URL 显式传 `?cover=1` 时只显示卡片并隐藏页头、页尾和其它主体元素；`?cover=1` 的整个浏览器 viewport 就是 4:3 卡片画布，不允许页面级灰底、padding、margin、letterbox、滚动条或黑屏；720×540、580×435、390×292、320×240 视口都必须贴齐填满；不要新增 `ratio` / `gallery` 等尺寸参数；宽宝活卡必须使用官网浅色系，不允许整卡暗色/黑底/深蓝底；顶部左侧只保留官方标签预留位，不显示固定「宽宝活卡」文案，右侧显示 `YYYY-MM-DD` 更新日期；卡片不是完整页面缩小版，只保留 1 个主判断、1 个大数或标志性小图、2-3 个解释指标、2-3 个短标签；必须先选择数字主导 `numeric-focus` 或视觉主导 `visual-focus`，大数字/等级与主图形二选一，不保留二级阅读块、排行榜或脚注式方法说明；如果卡片标题与外层模板标题重复，卡片标题必须改成一句重点结论；核心表达区按内容选择数字主导或视觉主导样式，继承原页面最有辨识度的可视化语言（如泡沫场、涨跌停结构条、估值水位仪、净值曲线），不要把所有页面都压成通用四宫格；新卡片根节点必须带 `data-qb-live-card`，并给标签预留位、日期、标题、描述、核心区分别加 `data-qb-live-card-brand` / `data-qb-live-card-date` / `data-qb-live-card-title` / `data-qb-live-card-description` / `data-qb-live-card-core`；发布前必须跑 `scripts/verify_page.mjs "<html_or_url>?cover=1" --require-browser --cover-card`，并确保不长期停在“取数中 / 判断生成中 / —”等占位态；本地先验收默认页与 cover URL，用户确认后再 update/upload。
> 硬规则：宽宝活卡版式必须是固定四行骨架：第一行 meta（左侧官方标签预留位为空、右侧日期，日期颜色/粗细/字号走统一 muted token）、第二行标题（统一标题字号/粗细，不随模板任意变大变小）、第三行描述（统一 muted 文本色、字号、行高，通常 1 行，最多 2 行）、第四行核心表达区。卡片外层内边距必须四周一致且响应式收敛；第四区必须吃满前三行之后的剩余空间，内部图形/数字/解释指标不能离容器边界过远、不能留下大块空白。第四区按原链接 HTML 的精华选择 `visual-focus` 或 `numeric-focus`：视觉系保留原页最有辨识度的小图形，数字系保留一个主数字/等级与 2-3 个解释指标。
> 硬规则：用户要“改造已经生成的 HTML / 去掉二维码 / 去掉当前页头页尾 / 适配固定页头页尾”时，优先用 `scripts/retrofit_share_shell.py`。不要靠长提示词让 Agent 手工删 DOM；默认保留旧页面主体 hero 区域，只移除其中的二维码卡片和旧页尾，然后在 `body` 顶部/底部直接插入公共页头页尾；先生成本地迁移版验证，再用 `update:true` 覆盖同一个 `page_id`。

1. **注册公式任务包**（`scripts/formula_package.py register`）
   - `formulas`：一组 `"变量名 = 表达式"`（沿用 quant-buddy-skill 探索时验证过的公式）。
   - `reads`：对外产出清单，每条声明 `output`（产出名）+ `read_mode`（读取模式）。
   - 成功返回 `package_id` + `signature`，并自动落盘到 `output/formula_packages/<package_id>.json`。
   - ⚠️ `signature` 只在注册时明文返回一次，本地凭证丢失即不可恢复（可 `refresh` 轮换）。

2. **生成看板**（`scripts/build_dashboard.py`）
   - 写一份 spec：`title` + `panels[]`，每个 panel 把某个 `output` 渲染为 `line`/`bar`/`table`/`number`/`text`/`raw`。
   - 固定页面形态先用 `static_page.py templates` / `template` 查在线官方精选详情并下载 HTML；没有合适精选页时，才自行构建满足契约的 spec 或 bespoke 主体。
   - 页面是实时取数的（见下「取数：实时取数」），spec 里不用写 `mode`。
   - 产物默认写到 `output/pages/<slug>.html`；传 `"upload": true` 可一步生成并发布。

3. **发布 / 管理**（`scripts/static_page.py`）
   - `upload`：上传 HTML → 返回 `page_id` + 公开 `url`；可带 `title`（缺省取 `<title>`）和 `description`（页面说明，≤1000 字，列表/详情展示用）。宽宝活卡页面可传 `verify_cover_card:true`，本地通过默认页与 `?cover=1 --cover-card` 后再上传，并返回 / 透传 `cover_card_url`、`has_cover_card`；范式卡 artifact 可传 `verify_card_runtime:true`，只跑快速 card runtime artifact 门禁。
   - `update`：替换已发布页面的内容，**URL / page_id 不变**（页面已分享后想补充/调整时用，访问者刷新即见新内容，不占新配额）。也可只改 `title` / `description`（`description` 传空串 `""` 清空，不传保留原值）。同样支持 `verify_cover_card`、`verify_card_runtime`、`cover_card_url`、`has_cover_card`。
   - `download`：取回已发布页面的 HTML 再编辑（鉴权拿 url → 直连 OSS 下载，不占服务端带宽），改完 `update` 覆盖。
   - `list` / `revoke`：列出 / 撤销我的页面（活跃页上限 200，单页 ≤ 2MB）。
   - `thumbnail`：给某个已发布页面设置 / 替换一张**纯展示封面图**（直传 PNG/JPG，≤2MB）。只用于列表/详情/模板墙的 `<img>` 预览，**不进入 HTML、不影响取数、不占活跃页配额**；按 page_id 命名存 OSS，转模板后仍有效。`upload` / `update` 可带 `thumbnail_file`，HTML 成功后再自动上传封面；缩略图失败只返回 warning，不回滚 HTML。
   - `templates` / `template`：**浏览 / 复用官方精选**——`templates` 列出带 `recommend:官方精选` 的页面（不再以 `is_template/template_status` 作为发现门槛），`template` 看详情拿 `download_url`，直连 OSS 取回 HTML，换成自己的标的/文案/公式包后再 `upload` 成自己的页；返回会透传或派生 `cover_card_url` / `has_cover_card`。
   - `update_template`：已转 published template / 官方精选页需要保留原链接时的安全维护 helper；写回前先 re-query metadata，对 `expected_metadata` 做并发检查，再调用后台 `updateTemplate`，保持同一个 `template_id/page_id/public_url`。可传 `verify_card_runtime:true` 做写回前 artifact 快速门禁。
   - `verify_card_runtime`：批量验收已发布/官方精选页的独立 card artifact；输入 `page_ids` / `template_ids` / `urls`，脚本会下载 HTML、检查 artifact/manifest/runtime、查询 `required_outputs`，并在空白宿主中独立 hydrate，逐项保存 HTML/JSON 结果。
   - `upload` / `update` 发布前会强制检查公共 share shell；缺公共页头/页尾会自动插入并编译，主题色只能通过 `theme` / `--qb-shell-*` 变量覆盖，仍有占位符或旧二维码残留则拒绝发布。
   - 如果一个公开 URL 明明可访问，但 `download` / `update` 返回 `PAGE_NOT_FOUND`，可用 `template --page_id <page_id>` 检查它是否已进入官方精选/旧模板口径；本 skill 对这类页面默认只读取和复用，不要擅自新建 URL 或走普通 `update` 覆盖。若用户明确要求保留原链接更新，停下说明需要后台/admin 路径，不能用新 URL 代替。
   - 权限 / 权责：自己的页面默认仅本人；`is_test` 用户可跨 download / update / thumbnail 其他 is_test 用户页面、`list` 传 `scope=test_all` 看全部 test 用户（普通用户页面一律 `FORBIDDEN`）。**官方精选浏览/复用对全员开放**；官方精选标签、旧模板元数据/上下线/删除、把已有页转旧公共模板都是后台（growthX）动作——本 skill 侧只「读取 + 复用」，不做这些写操作。

> 认证只靠 `config.json` 的 `api_key`（query 取数连 api_key 都不需要，凭 package_id + signature）。本技能不维护会话 / task_id。

## 取数：实时取数

看板是实时取数的：HTML 内嵌 `package_id + signature`，访问者打开页面时即时调用 `queryFormulaPackage` 拉取最新数据并渲染——底层数据更新即自动重算，**页面打开就是最新**，这正是公式任务包的设计目的。spec 不需要写 `mode` 字段。

- **页面是"活"的**：数据不焊进 HTML，运行时实时取；构建期只取一次数做质量体检（数据健康 + 单标的文案一致性），不内联。
- **两个前提（均已满足）**：① `queryFormulaPackage` 端点对页面域名 `pages.quantbuddy.cn` 放开 **CORS**（当前 https 端点已放开 `*`）；② `signature` 随页面公开（公式包 query 本就以 signature 作能力令牌、设计上允许嵌入页面）。
- ⚠️ **协议必须一致**：页面发布在 `https://`，`config.json` 的 `endpoint` 也必须是 `https://`，否则浏览器会以 mixed-content 拦截取数。当前 endpoint 已是 `https://www.quantbuddy.cn/skill`。

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
| `scripts/compile_bespoke_page.py` | （单命令） | **【shell 处理脚本】** bespoke 主体 HTML → 内联公共 share shell / logo / qr-mini / data-kernel 的自包含 HTML | [guides/share-shell.md](guides/share-shell.md) |
| `scripts/retrofit_share_shell.py` | （单命令） | **【shell 处理脚本】** 旧 HTML/已发布页面 → 删除旧二维码/旧页头/旧页尾，套入公共 share shell（`assets/share-shell/`），可原链接 update | [tools/retrofit_share_shell.md](tools/retrofit_share_shell.md) |
| `scripts/static_page.py` | `upload` / `update` / `download` / `list` / `revoke` / `thumbnail` / `tags` / `publish_community` / `unpublish_community` / `templates` / `template` / `update_template` / `retrofit_card_runtime` / `verify_card_runtime` | 发布/替换/下载/管理静态页，得到公开链接（`update` 替换内容不换链接；宽宝活卡可加 `verify_cover_card`；范式卡 artifact 可加 `verify_card_runtime` 或批量跑 `verify_card_runtime`；`thumbnail` 设展示封面；`templates`/`template` 浏览复用官方精选；`update_template` 安全改写需要保留原链接的官方精选/旧模板；is_test 可跨用户） | [tools/static_page.md](tools/static_page.md) |
| `scripts/verify_page.mjs` | （单命令） | 发布前/发布后页面验收：1440px、390px、320px 视口，h1、占位符、横向溢出、控制台核心错误；发布前可加 `--require-browser` 强制浏览器验收；宽宝活卡加 `--cover-card` 检查 4:3 视口填满、浅色主题、统一骨架、DOM 标记、无滚动条、无长期占位态；范式卡 artifact 可加 `--card-runtime-only` 跳过整页视口，只验收 artifact/manifest/required_outputs/独立 hydrate | — |
| `scripts/render_cover.py` | （被 `build_dashboard` 调用） | 封面栅格化与合成兜底：`capture_page_cover` 用系统 Edge/Chrome 无头截"封面模式页"为整页 PNG；合成封面（全幅裸图/品牌海报）走 浏览器 → 纯 Python(cairosvg/svglib) → SVG 三层兜底。跨平台、零强依赖，不影响 HTML 发布 | — |
| `scripts/render_existing_page_thumbnail.py` | （单命令） | 给已发布/官方精选 HTML 补封面：下载或读取 HTML → 解析内嵌公式包凭证 → 先取真实 outputs 并临时替换 `QB.query` → 再用系统 Edge/Chrome 截 1200×675 PNG；可带 `upload:true` 直接设置 `thumbnail_url` | [tools/static_page.md](tools/static_page.md) |
| `assets/data-kernel.js` | （前端内核，非脚本） | 手搓 bespoke 页共用的「取数 + 清洗 + 容错」一份；内联进页面 `<script>` 用 | [guides/bespoke-page.md](guides/bespoke-page.md) |
| `assets/share-shell/` | （公共组件） | 所有落地页共用的页头、页尾、刷新按钮、分享海报弹层、海报 canvas、复制链接与复制/下载行为 | [guides/share-shell.md](guides/share-shell.md) |
| `assets/live-card.css` / `assets/live-card.js` | （公共组件） | 宽宝活卡生成时必须复用的浅色外壳、固定骨架、`?cover=1` card-only 开关和数据填充辅助；通过 `compile_bespoke_page.py` 的 `<!-- QB_LIVE_CARD_CSS -->` / `<!-- QB_LIVE_CARD_JS -->` 内联 | [guides/essence-cover-card.md](guides/essence-cover-card.md) |
| `guides/essence-cover-card.md` | （开发指南） | 页面精华浓缩为固定 4:3 实时封面卡：默认隐藏，标准 URL 用 `?cover=1` 进入 card-only 模式，适合作为官网卡片流、缩略图或封面截图源 | — |

> **三条生产路**：固定页面先复用在线模板；标准看板走 `build_dashboard`（声明式快路）；要自定义版式/SVG 的设计页才写 bespoke 主体 HTML。
> 数据层统一调 `assets/data-kernel.js`（`QB.query` 取数、`QB.series/lastValue/topValues` 解包清洗），别再每页各抄 `fetch`/解包、各踩"假 0/缺口"的坑。见 [guides/bespoke-page.md](guides/bespoke-page.md)。
> 发布前用 `scripts/verify_page.mjs <html_file> --require-browser` 检查桌面与 390px/320px 移动端，确保无 `QB_SHARED_` / `replace_with_signature` / `pkg_replace` 残留、存在 `<h1>`、无关键横向溢出和核心取数脚本错误。宽宝活卡还要对 `?cover=1` 跑 `--cover-card`。若机器没有 Playwright/Chrome/Edge，脚本会明确标记为 `static-only`，不能当完整浏览器验收。

## 配置

`config.json`：填入 `api_key`（从 https://www.quantbuddy.cn/login 获取），或设环境变量 `QUANT_BUDDY_API_KEY`。可建 `config.local.json` 覆盖 `endpoint` / `api_key` 等（不入库）。`formula_package.py`、`build_dashboard.py`、`static_page.py` 共用同一个 `endpoint`。
