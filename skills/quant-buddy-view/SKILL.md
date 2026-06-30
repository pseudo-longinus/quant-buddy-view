---
name: quant-buddy-view
slug: quant-buddy-view
author: guanzhao
version: 0.4.1
description: |
  QBV / quant-buddy-view（用户可能写成 /quant-buddy-view、/qbv、qbv 或 QBV）用于把量化数据做成「公开可分享、实时取数」的网页看板/落地页。
  Use this skill when the user asks to create, update, publish, verify, retrofit, or reuse a Quant Buddy dashboard/static page/template, including shareable pages, public URLs, formula packages, thumbnails, share shell, poster/share behavior, single-stock profile pages, valuation/financial profile pages, index-anomaly boards, multi-factor screeners, and commodity daily pages.
  配合 quant-buddy-skill 使用：固定页面请求先用 static_page.py templates/template 选择在线模板；实时取数页必须先在 quant-buddy-skill 验证公式并确认其 api_key 可用，再用本技能注册自有公式包、替换凭证/文案、浏览器验收，并通过 static_page.py upload/update 发布或更新 pages.quantbuddy.cn 链接。默认不从本地历史样板目录或低质 HTML 骨架起步。
  Do not use this skill for one-off 行情查询、普通股票涨跌幅/估值问答、选股/回测探索；those belong to quant-buddy-skill unless the user explicitly wants a reusable/shareable page.
runtime: python
primaryCredential: quant-buddy API Key
metadata:
  version: 0.4.1
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

1. 先用 `scripts/static_page.py templates` / `template` 筛选在线公共模板。
2. 用 quant-buddy-skill 验证模板或页面需要的公式，确认真实出数。
3. 用 `scripts/formula_package.py register` 注册当前用户自己的公式包。
4. 替换模板/HTML 里的标的、文案、`package_id`、`signature`。
5. 发布前跑 `scripts/verify_page.mjs <html_or_url> --require-browser` 做浏览器验收；`static-only` 不能算完整验收。
6. 用 `scripts/static_page.py upload` 创建新链接，或用 `update` 覆盖原 `page_id` 且保持 URL 不变。

## 何时用本技能 vs quant-buddy-skill

- **探索/一次性查询**（"茅台今天涨跌幅"、"跑个均线金叉回测看看"）→ 用 **quant-buddy-skill**。
- **要一个能反复看、能发给别人、数据会自动更新的页面** → 探索清楚后切到 **quant-buddy-view**。

## 默认路由

- **固定页面形态**（个股速览、估值体检、成分股异动榜、多因子选股看板、商品日报等）：先 `templates` 列表筛选，再 `template` 取详情和 `download_url`。
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

> Agent 路由规则：用户要**生成 / 复用 / 发布 / 更新**可分享页面时，默认先用 `scripts/static_page.py templates` / `template` 读取在线公共模板；从 `template` 返回的 `download_url` 直连 OSS 下载 HTML，替换标的、文案、公式包凭证后，再验收并 `upload` 成用户自己的页面。用户要从需求做到链接 → 看 `workflows/`；用户要复杂自定义页面或迁移旧 HTML → 看 `guides/`。

| 类型 | 展示名 | 入口 | 什么时候用 |
|---|---|---|---|
| 页面模板 | 在线公共模板 | `scripts/static_page.py templates` / `template` | 个股速览、估值体检、异动榜、选股看板、商品日报等固定页面形态；先列表筛选，再取详情下载 HTML 复用 |
| 通用流程 | 标准实时看板 | [workflows/dashboard-end-to-end.md](workflows/dashboard-end-to-end.md) | 用户要“做成可分享看板/链接”，但没有指定固定页面模板 |
| 开发指南 | 自定义页面 | [guides/bespoke-page.md](guides/bespoke-page.md) | `build_dashboard` 做不出的自定义 HTML/CSS/SVG 页面，或迁移已有 HTML |
| 迁移工具 | 旧页套公共外壳 | [tools/retrofit_share_shell.md](tools/retrofit_share_shell.md) | 已发布/已生成 HTML 需要去掉旧二维码、旧页头、旧页尾，并保留同一个 `page_id` 更新 |

> 硬规则：用户要“某只股票/指数画像页、个股画像、单股画像、单标的页面”时，先用 `templates` 找个股画像/个股速览类在线模板，并用 `template` 取详情和 `download_url`。若没有合适在线模板，才使用 `build_dashboard` 自行构建，但必须保留 `template: "single-stock"` 并满足单标的模板契约；不要手写旧版“1 条价格线 + 4 个数字卡”的最小 spec，`build_dashboard` 会拒绝这种旧骨架。
> 硬规则：用户问“这只股票贵不贵 / 基本面是否改善 / 估值与财务画像 / PE/PB历史水位 / 财务趋势 / 现金流质量”并要求做成落地页或公开链接时，先用 `templates` 找个股估值体检/估值财务类在线模板，验证并注册该模板要求的一套公式包；不要退回普通 `single-stock` 卡片页。
> 硬规则：用户要“某指数 / 某股票池 的成分股异动、异动榜、龙虎榜式排行”（如「中证500今天哪些股票异动」「沪深300异动监控」「上证50涨跌幅榜」）时，先用 `templates` 找成分股异动榜类在线模板，再替换指数、文案和公式包凭证；不要手写一份离题的浅色/通用 HTML。
> 硬规则：用户要“主题股票池 / 概念股 / 行业池 + 多因子评分 / TopN / 回测 / rankIC / K线 / 公式审计”的选股工作台页面时，先用 `templates` 找多因子选股看板类在线模板；公式包角色固定为 `RANK` / `BACKTEST` / `KLINE_*`，`RANK` 必须首屏优先渲染，`BACKTEST` 和 `KLINE_*` 允许局部降级。
> 硬规则：复用公共模板时，模板 HTML 里的 `package_id + signature` 属于模板原作者；必须按当前用户目标重新验证公式、注册自己的公式包，并替换页面里的凭证后再发布。不要把公共模板原凭证直接当成用户页面的数据来源。
> 硬规则：单标的画像页的 `subtitle` 和“阅读摘要”只能使用 `build_dashboard` 构建期实时取数结果（最终 outputs）对应的数值。若脚本返回“文案与实时取数结果不一致”，按返回的 `facts` 重写文案后再生成/上传，不要沿用旧查询结果或手工估算。
> 硬规则：所有落地页必须接入 `assets/share-shell/` 公共组件。页头、页尾、刷新按钮、分享海报弹层、复制链接、复制/下载 PNG 和海报固定页头页尾的唯一来源是 `assets/share-shell/shell.html`、`shell.css`、`shell.js`、`poster.js`；模板只负责主体内容和 `getPosterData()`，不要在单个模板里私自复制或改造旧二维码块、旧页头页尾、旧刷新按钮或旧分享弹层。
> 硬规则：分享海报由公共 `poster.js` 默认前端截图页面主体生成，宁缺毋滥；模板可用 `data-qb-poster-target` 标记核心截图区域，`getPosterData()` 只提供标题/摘要和结构化兜底候选，不要依赖 Agent 手写海报版式，也不要把整页内容塞进 `sections`。
> 硬规则：用户要“改造已经生成的 HTML / 去掉二维码 / 去掉当前页头页尾 / 适配固定页头页尾”时，优先用 `scripts/retrofit_share_shell.py`。不要靠长提示词让 Agent 手工删 DOM；默认保留旧页面主体 hero 区域，只移除其中的二维码卡片和旧页尾，然后在 `body` 顶部/底部直接插入公共页头页尾；先生成本地迁移版验证，再用 `update:true` 覆盖同一个 `page_id`。

1. **注册公式任务包**（`scripts/formula_package.py register`）
   - `formulas`：一组 `"变量名 = 表达式"`（沿用 quant-buddy-skill 探索时验证过的公式）。
   - `reads`：对外产出清单，每条声明 `output`（产出名）+ `read_mode`（读取模式）。
   - 成功返回 `package_id` + `signature`，并自动落盘到 `output/formula_packages/<package_id>.json`。
   - ⚠️ `signature` 只在注册时明文返回一次，本地凭证丢失即不可恢复（可 `refresh` 轮换）。

2. **生成看板**（`scripts/build_dashboard.py`）
   - 写一份 spec：`title` + `panels[]`，每个 panel 把某个 `output` 渲染为 `line`/`bar`/`table`/`number`/`text`/`raw`。
   - 固定页面形态先用 `static_page.py templates` / `template` 查在线模板详情并下载 HTML；没有合适模板时，才自行构建满足契约的 spec 或 bespoke 主体。
   - 页面是实时取数的（见下「取数：实时取数」），spec 里不用写 `mode`。
   - 产物默认写到 `output/pages/<slug>.html`；传 `"upload": true` 可一步生成并发布。

3. **发布 / 管理**（`scripts/static_page.py`）
   - `upload`：上传 HTML → 返回 `page_id` + 公开 `url`；可带 `title`（缺省取 `<title>`）和 `description`（页面说明，≤1000 字，列表/详情展示用）。
   - `update`：替换已发布页面的内容，**URL / page_id 不变**（页面已分享后想补充/调整时用，访问者刷新即见新内容，不占新配额）。也可只改 `title` / `description`（`description` 传空串 `""` 清空，不传保留原值）。
   - `download`：取回已发布页面的 HTML 再编辑（鉴权拿 url → 直连 OSS 下载，不占服务端带宽），改完 `update` 覆盖。
   - `list` / `revoke`：列出 / 撤销我的页面（活跃页上限 200，单页 ≤ 2MB）。
   - `thumbnail`：给某个已发布页面设置 / 替换一张**纯展示封面图**（直传 PNG/JPG，≤2MB）。只用于列表/详情/模板墙的 `<img>` 预览，**不进入 HTML、不影响取数、不占活跃页配额**；按 page_id 命名存 OSS，转模板后仍有效。`upload` / `update` 可带 `thumbnail_file`，HTML 成功后再自动上传封面；缩略图失败只返回 warning，不回滚 HTML。
   - `templates` / `template`：**浏览 / 复用公共模板**——`templates` 列模板（普通用户只见 published），`template` 看某模板详情拿 `download_url`，直连 OSS 取回 HTML，换成自己的标的/文案/公式包后再 `upload` 成自己的页。
   - `upload` / `update` 发布前会强制检查公共 share shell；缺公共页头/页尾会自动插入并编译，主题色只能通过 `theme` / `--qb-shell-*` 变量覆盖，仍有占位符或旧二维码残留则拒绝发布。
   - 如果一个公开 URL 明明可访问，但 `download` / `update` 返回 `PAGE_NOT_FOUND`，先用 `template --page_id <page_id>` 检查是否已转成公共模板；若 `template_status=published`，本 skill 默认只读取和复用该模板，不要擅自新建 URL 或走普通 `update` 覆盖。若用户明确要求保留原模板链接更新，停下说明需要后台/admin `updateTemplate` 路径，不能用新 URL 代替。
   - 权限 / 权责：自己的页面默认仅本人；`is_test` 用户可跨 download / update / thumbnail 其他 is_test 用户页面、`list` 传 `scope=test_all` 看全部 test 用户（普通用户页面一律 `FORBIDDEN`）。**公共模板浏览/复用对全员开放**（普通用户只读 published）；模板的提交/改写/上下线仅 is_test，把已有页转公共模板是后台（growthX）动作——本 skill 侧只「读取 + 复用」模板，不做这些写操作。

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
| `scripts/static_page.py` | `upload` / `update` / `download` / `list` / `revoke` / `thumbnail` / `templates` / `template` | 发布/替换/下载/管理静态页，得到公开链接（`update` 替换内容不换链接；`download` 取回 HTML 再编辑；`thumbnail` 设展示封面；`templates`/`template` 浏览复用公共模板；is_test 可跨用户） | [tools/static_page.md](tools/static_page.md) |
| `scripts/verify_page.mjs` | （单命令） | 发布前/发布后页面验收：1440px、390px、320px 视口，h1、占位符、横向溢出、控制台核心错误；发布前可加 `--require-browser` 强制浏览器验收 | — |
| `scripts/render_cover.py` | （被 `build_dashboard` 调用） | 封面栅格化与合成兜底：`capture_page_cover` 用系统 Edge/Chrome 无头截"封面模式页"为整页 PNG；合成封面（全幅裸图/品牌海报）走 浏览器 → 纯 Python(cairosvg/svglib) → SVG 三层兜底。跨平台、零强依赖，不影响 HTML 发布 | — |
| `scripts/render_existing_page_thumbnail.py` | （单命令） | 给已发布/公共模板 HTML 补封面：下载或读取 HTML → 解析内嵌公式包凭证 → 先取真实 outputs 并临时替换 `QB.query` → 再用系统 Edge/Chrome 截 1200×675 PNG；可带 `upload:true` 直接设置 `thumbnail_url` | [tools/static_page.md](tools/static_page.md) |
| `assets/data-kernel.js` | （前端内核，非脚本） | 手搓 bespoke 页共用的「取数 + 清洗 + 容错」一份；内联进页面 `<script>` 用 | [guides/bespoke-page.md](guides/bespoke-page.md) |
| `assets/share-shell/` | （公共组件） | 所有落地页共用的页头、页尾、刷新按钮、分享海报弹层、海报 canvas、复制链接与复制/下载行为 | [guides/share-shell.md](guides/share-shell.md) |

> **三条生产路**：固定页面先复用在线模板；标准看板走 `build_dashboard`（声明式快路）；要自定义版式/SVG 的设计页才写 bespoke 主体 HTML。
> 数据层统一调 `assets/data-kernel.js`（`QB.query` 取数、`QB.series/lastValue/topValues` 解包清洗），别再每页各抄 `fetch`/解包、各踩"假 0/缺口"的坑。见 [guides/bespoke-page.md](guides/bespoke-page.md)。
> 发布前用 `scripts/verify_page.mjs <html_file> --require-browser` 检查桌面与 390px/320px 移动端，确保无 `QB_SHARED_` / `replace_with_signature` / `pkg_replace` 残留、存在 `<h1>`、无关键横向溢出和核心取数脚本错误。若机器没有 Playwright/Chrome/Edge，脚本会明确标记为 `static-only`，不能当完整浏览器验收。

## 配置

`config.json`：填入 `api_key`（从 https://www.quantbuddy.cn/login 获取），或设环境变量 `QUANT_BUDDY_API_KEY`。可建 `config.local.json` 覆盖 `endpoint` / `api_key` 等（不入库）。`formula_package.py`、`build_dashboard.py`、`static_page.py` 共用同一个 `endpoint`。
