---
name: quant-buddy-view
slug: quant-buddy-view
author: guanzhao
version: 0.6.20
description: |
  QBV / quant-buddy-view（用户可能写成 /quant-buddy-view、/qbv、qbv 或 QBV）用于把量化数据做成「公开可分享、实时取数」的网页看板/落地页。
  Use this skill when the user asks to create, update, publish, verify, retrofit, or reuse a Quant Buddy dashboard/static page/template, including shareable pages, public URLs, formula packages, thumbnails, share shell, cover/essence cards, poster/share behavior, single-stock profile pages, valuation/financial profile pages, index-anomaly boards, multi-factor screeners, and commodity daily pages.
  配合 quant-buddy-skill 使用：固定页面请求先用 static_page.py templates/template 选择带 recommend:官方精选 标签的在线精选页；实时取数页必须先在 quant-buddy-skill 验证公式并确认其 api_key 可用，再用本技能注册自有公式包、替换凭证/文案、浏览器验收，并通过 static_page.py upload/update 发布或更新 pages.quantbuddy.cn 链接。默认不从本地历史样板目录或低质 HTML 骨架起步。
  用户显式唤起 /quant-buddy-view、/qbv、qbv 或 QBV，且请求不是纯咨询/代码维护/文档解释时，默认视为可分享活页任务：读完本技能约束后先查官方精选+社区范式卡判定 direct/fork/unmatched；默认 direct 先交付现成链接、fork/unmatched 用 new_page 返回首链；当 config.json._channel=feishu-group 时，所有分支都禁止提前发送链接，只在终态交付 playground 链接。
  Do not use this skill for one-off 行情查询、普通股票涨跌幅/估值问答、选股/回测探索；those belong to quant-buddy-skill unless the user explicitly wants a reusable/shareable page.
runtime: python
primaryCredential: quant-buddy API Key
metadata:
  version: 0.6.20
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
    - https://pages.quantbuddy.cn
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
  - https://pages.quantbuddy.cn
runtimeRequirements:
  python: "3.8+"
  packages: []
---

# quant-buddy-view · 量化看板发布

把「已验证的量化数据与公式」沉淀成一个**公开可分享、实时取数**的网页看板/落地页。本技能不做一次性行情查询或回测探索；默认执行路线是：

> **0.6.20 变更**：分享海报预览新增 `data-qb-runtime-src` 合同，允许用户点击分享前保持空 `src`；静态预检与浏览器图片门禁只豁免显式声明且尚未赋值的运行时图片，普通正文图片仍必须提供非空 `src`，不再要求每个任务临时塞透明占位图。Card Runtime 完整重建同时改为显式视觉合同并 fail-closed：未命中页面专属视觉、也未传 `visual_contract` 时返回 `CARD_VISUAL_REQUIRED`，不再自动挑前三个 outputs 生成三行指标卡；新建 artifact 必须声明 `data-qb-card-visual-kind` / manifest `visual_kind` 并通过 `--require-card-visual-contract`。`numeric-focus` 只在显式选择时可用，且必须是“一个主数字 + 最多两个解释项”，不能退化为三个等权矩形；新增 `basis-structure` 基差轴视觉作为首个合同化示例。
>
> **0.6.19 变更**：已发布范式卡的 Card Runtime 协议升级新增 `preserve_visual` 路径，只更新 manifest/runtime 与 ready 契约，逐字节保留原 template/style；`retrofit_card_runtime` 的独立验收固定使用 `--card-runtime-only`。禁止用通用三指标重建路径覆盖已有视觉 artifact；只有 artifact 缺失且明确选择 numeric-focus 时才允许生成数字主导卡片。
>
> **0.6.18 变更**：`publish_workflow.py` 在 QBS 验证、注册和上传等网络写入前，先以假凭证运行 Card Runtime 结构预检，提前拦截空 manifest 凭证、缺少/空 `src` 的图片等结构错误；package/grant 的 `markers.package_id`、`markers.grant_id`、`markers.signature` 现在兼容单个字符串或非空字符串数组，同一次注册可扇出替换页面正文与 Card Runtime 中的多个唯一 marker，避免为同一数据合同重复注册公式包。
>
> **0.6.17 变更**：`templates` 不再把完整候选池原样打到 stdout——响应改为 `item_count` + 覆盖全部候选的 `items_summary`（不是 top-N）+ 完整结果落盘产生的 `full_result_file`/`full_result_sha256`；完整候选（含 `agent_reply_hint`/`page_context`）落盘到系统临时目录，交由既有 `cleanup_task_temp_files` 自动回收。落盘失败（`TEMPLATES_PERSIST_FAILED`）或响应结构异常（`TEMPLATES_RESPONSE_SHAPE_UNEXPECTED`）时直接返回错误，不再退化为把完整结果打印到 stdout——这是为了修复"候选池被外层工具输出预算截断、又没有另存一份，导致误判 unmatched 走自建"的事故根因。`templates` 现在也需要 Trace Context（task_id）。
>
> **0.6.16 变更**：`getStaticPage`/`getTemplate` 现在都会带回来源公式包的 `formulas` 原文（公式不是隐私内容）；`fork_prepare` 据此在 `fork_manifest.source_runtime_contract.packages[]` 里整理出每个包的 `formulas/outputs`，并用 `cross_asset_formula_refs` 标出引用了非主资产标的的公式（同业对比、行业分组一类）。fork 改公式时改为对照原文改写，不再凭 `required_outputs` 的变量名反推语法；跨资产公式必须先重新判断目标资产自己的同业/行业范围，不能直接照抄原资产的同业列表。

> **Fork 数据通道继承硬规则**：fork 的目标是替换标的并保持来源范式运行合同，不是重新设计数据层。来源模板某一角色使用公式包，目标页同一角色继续使用公式包；来源使用 `fast_query` / `stock_profile` / `composition_select` 数据授权，目标页继续使用同 kind、同 query_type、同响应形状的数据授权。禁止仅因“财务数据通常可走 fast_query(report)”就在 fork 中把来源财务公式包改成 grant，也禁止反向把来源 grant 改成公式包。只有 `unmatched` / 明确从零重建时才重新做通道选择；此时平台白名单报告期财务优先 `fast_query(query_type="report")`。
>
> **0.6.15 变更**：新增活页正文图片上传/列表、可在当前页面点击放大的声明式 image panel、publish_workflow 图片 marker、fork 同页复制和浏览器图片门禁；PNG/JPEG/WebP 由服务端统一转为同域 WebP，发布必须保持图片与目标 `page_id` 同属。
>
> **0.6.14 变更**：`data-kernel` 可在浏览器实时下载并解析 FastQuery `mode:"csv"`，自动 hydrate 为兼容的 `results[].fields[].series`；标准看板和构建期体检共用同口径，发布门禁等待 `QB_DATA_RUNTIME` 完成后再验收。
>
> **feishu-group 渠道**：打包渠道为 `feishu-group` 时，direct/fork/unmatched/update 等所有分支禁止发送非终态链接；终态 contract 统一把 `pages.quantbuddy.cn/pages/<owner>/<page_id>.html` 转成 `www.quantbuddy.cn/playground/<owner>/<page_id>`，内部发布与验收仍使用原始托管 URL。

0. 在任何后端请求前运行 `scripts/trace_context.py begin`，保存唯一 `task_id` 并在后续命令中复用。
1. 运行一次 `scripts/static_page.py templates`，传 `recommend:"all"`，查询官方精选+社区命中池。
2. direct 命中后，普通渠道先把列表返回的现成 URL 发给用户；`feishu-group` 不发链接，直接运行一次 `static_page.py direct_deliver` 完成模板详情、单次取数和终态确认。
3. fork/unmatched 创建 `new_page` 并保留同一 `page_id`；普通渠道立即发送首链，`feishu-group` 仅内部持有该链接，验证目标公式后继续注册、替换与 `publish_verified`。
4. 所有分支最终按 `agent_reply_contract` 和回复模板生成草稿，再运行一次 `validate_agent_reply.py`。

## 何时用本技能 vs quant-buddy-skill

- **探索/一次性查询**（"茅台今天涨跌幅"、"跑个均线金叉回测看看"）→ 用 **quant-buddy-skill**。
- **要一个能反复看、能发给别人、数据会自动更新的页面** → 探索清楚后切到 **quant-buddy-view**。

## 新会话路由：先查范式卡（templates）判命中

先建立 Trace Context，再查询范式卡：

```bash
python scripts/trace_context.py begin '{"user_query":"用户原始问题"}'
```

保存返回的 `task_id`，并把它加入本次任务后续每个 `static_page.py`、`formula_package.py`、`data_grant.py` 参数。脚本会通过 `x-task-id` 请求头透传，使后台能从提问一直聚合到最终活页链接。`templates` / `upload` / `update` / `publish_final` / `publish_verified` / `update_template` 缺少 Trace Context 时必须停止执行。QBV 编排中的 quant-buddy-skill 工具统一通过 `scripts/qbs_bridge.py <tool> @params.json` 调用，并显式传同一 `task_id + user_query`；bridge 会用 task-scoped session 继承 task_id，禁止生成第二个 session id。

新会话被判定为可分享活页任务时，**第一步只运行一次 `scripts/static_page.py templates`，参数传 `recommend:"all"`**。它会分别读取官方精选与社区并按 `page_id` 去重；这两次后端 `list_templates` 属于一次范式池查询，不要再手工重复调用。返回值是 `item_count` + 覆盖全部候选的 `items_summary`（不再是原始 items 全量打印），完整候选落盘在 `full_result_file`；正常路由判断只需要读 `items_summary`，不需要也不应该去读 `full_result_file`。

- **① 直接命中**（范式匹配，且标的/股票池/指数/市场范围一致）：
  - `templates` 一旦给出精确命中，普通渠道的**下一条用户可见消息必须立即发送现成 `download_url/public_url`，中间不允许任何工具调用**。推荐文案：`已直接命中现成活页：[标题](URL)。我继续核对实时数据并补充分析。`；若 `agent_reply_hint.delivery_policy.emit_intermediate_url=false`（即 `feishu-group`），禁止发送该 URL，直接继续。
  - 普通渠道发出链接后、`feishu-group` 不发链接而是立即运行一次：`python scripts/static_page.py direct_deliver '{"task_id":"task_xxx","page_id":"page_xxx","template_revision":"sha256"}'`。该命令内部固定完成一次模板详情读取、一次 HTML 下载、每个当前 package/grant 一次查询和一次 `direct_finalize`；不要再单独调用 `template`、query 或 `direct_finalize`。
  - 不 `new_page`、不注册、不 fork、不研究脚本源码、不先跑 `--help`。`direct_deliver` 的公式结果固定为 summary；grant 完整结果只写 `%TEMP%`，最终回复不得暴露本地路径或凭证。
  - 只有返回 `agent_reply_contract.terminal=true` 且 `operation=direct_finalize` 才允许最终收口；失败时说明具体错误，不得用已发送的链接绕过终态门禁。回复模板和 `page_context` 沿用原页。
  - `direct_deliver` 会返回真实 contract、草稿、校验参数的 `%TEMP%\qbv_<完整 task_id>_*` 文件路径及 `reply_validation_command`。只把 Markdown 写入返回的 `reply_draft_file`，执行返回的命令一次；`valid=true` 后立即最终回复，禁止再次校验、运行 `--help`、扫描临时目录或继续搜索 memory。成功校验会统一清理 contract、draft、params 和 grant 临时结果。
  - 用户之后说"要改这个页面内容" → 转 ② fork（官方/社区链接不能直接改，只能新建自己的链接后改）。
  - 边界：范式匹配但**标的/股票池/指数/市场范围不一致**（如命中的是茅台估值页、用户问的是宁德时代；命中沪深300异动页、用户问中证500）不算直接命中，落到 ②。只有资产无关且市场范围一致的全市场范式，才可不依赖具体标的直接命中。
- **② fork**（范式命中但标的不符，或用户要改内容）：
  - 先运行 `new_page` 创建进度页并取得 `page_id`：普通渠道立即发送首链；`feishu-group` 只内部保留 URL，不向用户发送。随后用同一 `task_id` 调 `fork_prepare` 下载该范式模板 HTML 并生成 `fork_manifest_v1`；脚本会把来源与 manifest 持久绑定到该任务，后续 `publish_final` 即使漏传来源字段也会自动恢复并强制校验。`source_template_id` 只继承回复 metadata，不会自动下载或克隆 HTML。
  - 用 `scripts/qbs_bridge.py validate_package_set @params.json` 按最终 package 边界验证**本标的**公式/输出（每包 1..20 条，保持顺序，自动处理 deferred/resume 并汇总收据）；harness 会把每包 `begin_date` 透传给 QBS，未提供时固定使用 `20150101`，避免滚动水位/长窗口公式因默认短区间出现假空值。validation 与 registration 必须使用同一个 `begin_date`。只有每包都返回 `validation_receipt_file` 才算完成。`failed` / 未完成 `deferred` 不得推进 → 注册**自己的**公式包或数据授权 → 换标的/文案/凭证 → 生成活页。
  - 估值分位输出必须名实一致：`pe_pctile=排序水位("pe_ttm",250)`、`pb_pctile=排序水位("pb",250)`，并先通过上述 QBS 验证；禁止用 `pe_pctile="pe_ttm"` / `pb_pctile="pb"` 直接别名。
  - **只要 fork 涉及至少 1 个 package/grant，就必须用 `scripts/publish_workflow.py @params.json`**（不是"较多时优先"）：按 marker 将验证、注册、HTML 凭证替换和 `publish_verified` 串成确定性短路流程；格式见 [tools/publish_workflow.md](tools/publish_workflow.md)。低于这个数量没有第二个"替换 marker/凭证"的工具，不要自己写脚本做这件事。
  - 页面正文与 Card Runtime 共用同一 package/grant 时，必须在同一注册项的 `markers` 字段中使用 marker 数组，把一个注册结果替换到多个全局唯一位置；禁止把 Card manifest 凭证留空，也禁止为了填 Card Runtime 再注册一个公式和读取合同等价的重复 package/grant。

  - 这不是建议——`publish_verified` 服务端会按 fork manifest 里的凭证数量强制核验：手工分步调用 `publish_verified(task_id, page_id, html_file, source_template_id, fork_manifest_file, validation_receipt_files)` 只有在这个页面**零凭证**（纯静态改造）时才会放行，否则直接拒绝并返回 `error:"PUBLISH_WORKFLOW_REQUIRED"`；出现该错误时改走 `publish_workflow.py`，不要绕过。
  - 回复 = 回复模板格式 + **自己的新链接**（数值同样用自己的包/grant query 填）。
- **③ 未命中**（无匹配范式）：`new_page` 创建进度页 → `build_dashboard` / bespoke 自建 → 其余同 ②；`feishu-group` 同样不发送进度链接。

> 后续追问：自己的链接 → `update` 同 `page_id`；命中的官方/社区链接要改 → 只能转 ② fork 成自己的链接后再改。

## 默认路由

- **固定页面形态**（个股速览、估值体检、成分股异动榜、多因子选股看板、商品日报等）：先 `templates` 查询官方精选+社区命中池；direct 直接用列表 URL + revision，fork 才读取和改写模板详情。
- **宽宝活卡 / 精华卡 / 封面卡（范式卡 artifact）**：把页面精华做成独立 **card runtime artifact**（`embedded-card-v1`：页面内嵌 `<template data-qb-card-template>` + `data-qb-card-manifest` + `QBCardRuntimeV1` runtime），供官网卡片流在空白宿主中**独立 hydrate**。静态首帧 `card_snapshot_url` 由 `skill_server` 按 artifact hash 生成，整页 `thumbnail_url` 与本契约独立。按 [guides/essence-cover-card.md](guides/essence-cover-card.md) 生成；已发布页优先用 `preserve_visual:true` 只升级协议。完整重建必须命中页面专属视觉或显式传 `visual_contract`，否则 `CARD_VISUAL_REQUIRED` 停止；用 `verify_page.mjs --card-runtime-only --require-card-visual-contract` 验收新 artifact。卡片必须官网浅色系、固定信息骨架、可变核心可视化；不再用旧的 `?cover=1` URL 模式。
- **没有合适在线模板**：再走 `workflows/dashboard-end-to-end.md`，用 `build_dashboard` 生成声明式实时看板。
- **声明式看板也不够**：才走 `guides/bespoke-page.md` 写 bespoke 主体 HTML，并用公共 shell 编译成自包含页面。
- **改造已发布/已生成页面**：优先 `scripts/retrofit_share_shell.py`，再 `static_page.py update` 保持同一个 `page_id` / URL。
- **用户可见链接策略**：普通渠道 direct 在 `templates` 命中后、下一次工具调用前发现成 URL，fork/unmatched 在 `new_page` 返回后立即发首链；`feishu-group` 看到 `delivery_policy.emit_intermediate_url=false` 后禁止发送任何非终态 URL，只在 validator 通过后发送 terminal contract 的 playground `public_url`。进度页仍用 `update_progress` 和 `publish_final` 更新同一 `page_id`。
- **Agent 回复模板**：活页 metadata 可带 `agent_reply_template` 指向本技能 `reply-templates/` 下的回复骨架。`reply-templates/` 是 Agent 最终回复格式，不是活页 HTML 页面模板；不要和在线 `templates` / `template` API 混用。
- 本 skill 不再内置本地页面样板，不能从本地历史样板目录或低质 HTML 骨架起步。

## Agent 回复模板（`agent_reply_template`）

活页用同级 `page_context` 描述用途/模块/输出，用 `agent_reply_template.template_ref` 指向 [reply-templates/](reply-templates/) 的 Markdown 骨架。字段契约、hybrid 规则和发布继承见 [tools/static_page.md](tools/static_page.md)。

- `page_context` 不得包含实时数值、api_key、signature、Bearer token 或本地路径；fork 后必须按最终页面重建，direct 才沿用原页。
- 读取型命令返回 `agent_reply_hint.terminal=false`；`new_page/update_progress` 也不是终态。成功的 `direct_deliver/direct_finalize/upload/update/publish_final/publish_verified/update_template` 才可返回 `agent_reply_contract.terminal=true`。
- fork/unmatched 遇到必须由用户决定的口径时，用同一 `task_id/page_id` 进入 `waiting_input`，用户回答后继续原任务；不要重新建 Trace 或首链。`feishu-group` 的 waiting hint 不含 `public_url`，提问时也不得附带进度链接。
- fork 必须使用 `fork_prepare` 绑定来源和 manifest，最终 `publish_final` 保持首链 URL、移除来源凭证并保留必需栏目/输出/Card Runtime；详细门禁见 [workflows/new-session-paradigm-routing.md](workflows/new-session-paradigm-routing.md)。
- prepared fork task 禁止 `build_dashboard`；脚本返回 `FORK_TASK_BOUND` 后只能继续编辑绑定的 `working_html_file` 并调用 `fork_validate`。
- 带 `task_id` 的进度从 `package_register` 起必须传同任务的 `validation_receipt_files`，收据必须为 `completed + success=true + failures=[]`；静态页可传明确的 `validation_not_required_reason`。
- 最终回复必须按回复模板输出并且只能使用 contract 的 `public_url`；`feishu-group` 下该字段必须是 `https://www.quantbuddy.cn/playground/<owner>/<page_id>`。依据 `reply_render_policy` 与 `reply_data_availability` 删除结构性不存在的字段、整列、整行和空可选章节，只有有效结构中的偶发缺值才写 `--`，不得暴露原始托管 URL、本地路径、凭证或内部日志。
- 最终回复前只运行一次发布器返回的 `reply_validation_command`；validator 必须读取发布器生成的 `contract_file + contract_sha256`，不得手工重建精简 contract。direct 使用 `direct_deliver` 返回的完整 task ID 路径和命令，成功后自动清理。`valid=true` 后不再执行任何工具调用。
- 没有 terminal contract 禁止完成任务。唯一例外是成功的 `waiting_input` checkpoint。
- 性能门槛：普通渠道模板命中到首链不超过 5 秒；所有渠道 terminal 到最终回复不超过 45 秒、端到端不超过 120 秒、用户可见消息间隔不超过 60 秒。
- 逐指标声明最新可得日期和实际覆盖范围。未做浏览器验收时，只能声明公开 URL 和实时接口可访问。

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

固定页面先查在线范式卡；direct 用 `direct_deliver`，fork 才下载和改写来源 HTML。不要从本地历史样板或低质骨架起步。

| 类型 | 展示名 | 入口 | 什么时候用 |
|---|---|---|---|
| 页面模板 | 官方精选 + 社区 | `scripts/static_page.py templates` | 固定页面形态；direct 直接交付，范围不一致才 fork |
| 回复模板 | Agent 回复骨架 | [reply-templates/](reply-templates/) | 活页 metadata 的 `agent_reply_template.template_ref`；用于约束 Agent 最终 Markdown 回复格式，不生成 HTML |
| 封面组件 | 宽宝活卡 / 精华卡 | [guides/essence-cover-card.md](guides/essence-cover-card.md) | 独立 4:3 `embedded-card-v1` artifact；按指南实现和验收 |
| 通用流程 | 标准实时看板 | [workflows/dashboard-end-to-end.md](workflows/dashboard-end-to-end.md) | 用户要“做成可分享看板/链接”，但没有指定固定页面模板 |
| 开发指南 | 自定义页面 | [guides/bespoke-page.md](guides/bespoke-page.md) | `build_dashboard` 做不出的自定义 HTML/CSS/SVG 页面，或迁移已有 HTML |
| 迁移工具 | 旧页套公共外壳 | [tools/retrofit_share_shell.md](tools/retrofit_share_shell.md) | 已发布/已生成 HTML 需要去掉旧二维码、旧页头、旧页尾，并保留同一个 `page_id` 更新 |

- 单标的画像、估值财务、指数成分异动、多因子工作台都先匹配对应在线范式；范围不一致才 fork。详细页面契约由模板和构建脚本门禁，不在此重复。
- fork 后禁止沿用来源 `package_id/grant_id/signature`；必须验证并注册当前用户凭证。
- 所有页面复用 `assets/share-shell/`；分享壳、海报、Card Runtime 和迁移细则分别读取对应 `guides/`，不要手写重复组件。
- 公式注册与读取模式见 [tools/formula_package.md](tools/formula_package.md)，数据授权见 [tools/data_grant.md](tools/data_grant.md)，静态页命令和 metadata 见 [tools/static_page.md](tools/static_page.md)。
- 普通自有页面用 `update` 保持 URL；published template 用 `template` 判定，除非用户明确维护原模板，否则只读复用或 fork。

## 取数：实时取数

看板是实时取数的：HTML 内嵌 `package_id + signature`，访问者打开页面时即时调用 `queryFormulaPackage` 拉取最新数据并渲染——底层数据更新即自动重算，**页面打开就是最新**，这正是公式任务包的设计目的。spec 不需要写 `mode` 字段。

- **页面是"活"的**：数据不焊进 HTML，运行时实时取；构建期只取一次数做质量体检（数据健康 + 单标的文案一致性），不内联。
- **两个前提（均已满足）**：① `queryFormulaPackage` 端点对页面域名 `pages.quantbuddy.cn` 放开 **CORS**（当前 https 端点已放开 `*`）；② `signature` 随页面公开（公式包 query 本就以 signature 作能力令牌、设计上允许嵌入页面）。
- ⚠️ **协议必须一致**：页面发布在 `https://`，`config.json` 的 `endpoint` 也必须是 `https://`，否则浏览器会以 mixed-content 拦截取数。当前 endpoint 已是 `https://www.quantbuddy.cn/skill`。

## 数据授权（Data Grant）vs 公式包 —— 页面免 key 取数的第二条通道

> 脚本 [scripts/data_grant.py](scripts/data_grant.py) 已可用，`build_dashboard` 与 `assets/data-kernel.js` 已支持 grant 面板，与公式包同页混用。契约见 [tools/data_grant.md](tools/data_grant.md)、服务端设计见 `skill_server/docs/dataGrant相关文档/数据授权-技术设计文档.md`。选凭证类型时按下面取舍表对照。

数据授权与公式包**共用同一套签名免 key 心智**：页面 HTML 内嵌一个凭证（公式包是 `package_id + signature`，数据授权是 `grant_id + signature`），访问者打开页面时免 key 实时取数。区别在钉死的是什么——公式包钉死"一组公式 + 读取模式"（会重算，走 SSE）；数据授权钉死"一次平台直取数请求"（无重算，普通 JSON）。

**取舍规则（选凭证类型时对照）**：

| 页面要展示的数据 | 用哪条通道 | 凭证 |
|---|---|---|
| 算出来的指标 / 回测净值 / IC / rankIC / 时序 / 自定义公式口径 | **公式包** | `package_id` |
| 平台白名单直取的行情 / 估值 / 财务 / 资金流（收盘价、涨跌幅、PE/PB…） | 数据授权 `fast_query` | `grant_id` |
| 个股预计算画像卡（估值/财务质量等维度画像） | 数据授权 `stock_profile` | `grant_id` |
| 已上线维度分的 TopN / 榜单 / 异动名单（动量反转、趋势结构…） | 数据授权 `composition_select` | `grant_id` |

- 一句话：**要"算"的用公式包；平台"直取/直选"的有界数据用数据授权**。原公式包 RANK 角色仍保留给"算指标"型多因子选股，不被 composition_select grant 取代。
- **两套并存**：探索/验证仍在 quant-buddy-skill 用 api-key 跑三接口（fastQuery / stockProfile / selectByComposition）；本技能只负责把验证过的请求注册成 grant 嵌页。api-key 那套一行不改。
- **硬门槛同公式包**：注册任何 grant 前，先在 quant-buddy-skill 用 api-key 跑通对应接口、确认命中/出数，再回本技能注册。
- **同源约束**：`access_dunhe=false`（页面绝不返回付费/敦和数据）、CORS/https 协议一致、signature 是公开凭证不打印给用户——与公式包完全一致。

## 硬规则

1. **中文参数走 @file 或环境变量**：Windows PowerShell 命令行直接传中文会被 GBK 截断。注册公式、写 spec 一律用 `@params.json`（UTF-8）或 `FP_PARAMS/BD_PARAMS/SP_PARAMS` 环境变量。
2. **公式必须先验证再注册（硬门槛）**：提交注册的每一组公式，**必须先在 quant-buddy-skill 里用 `runMultiFormulaBatchStream` 跑一遍并确认出数**（公式语法两边一致，可原样验证），跑成功才允许 `register`。不要凭空发明未验证的表达式，也不要"直接注册、错了再说"——注册时的服务端试读只是兜底，不替代这一步。fork 场景下同样适用：`fork_prepare` 会把来源公式包的 `formulas` 原文带回 `source_runtime_contract`（公式不是隐私），改写目标资产公式时照着原文替换，**不要只凭 `required_outputs` 的变量名反推语法**；公式里引用了非主资产标的的部分（`cross_asset_formula_refs` 标出的同业/行业对比类），要先判断目标资产自己的同业/行业范围再改写，不能把原资产的同业列表直接照抄——改完仍必须过 `runMultiFormulaBatchStream` 这一步，不因为"抄了模板"就可以跳过验证。
3. **验证参数也要换干净**：调用 `runMultiFormulaBatchStream` 时，`user_query` 必须反映当前用户请求和当前资产；若传 `task_id` 必须为本次新任务。复制示例时不能只替换 `formulas`，却留下“贵州茅台 factsheet”等旧 `user_query`，否则后台审计和回放会被污染。
4. **signature 是凭证**：不要打印到面向最终用户的对话里；看板会把它写进公开 HTML 供实时取数，发布前确认可接受。
5. **标签来源不要写 Agent**：显式传 `scene_tags` / `paradigm_tags` 时，`tagging_method` 用 `manual` / `migration` / `unknown`；需要 LLM 自动识别就调用 `scripts/static_page.py autotag`。不要再传 `tagging_method:"agent"`，也不要在 `tagging_meta.method` 里写 `agent`。
6. **失败要说清**：脚本返回 `code != 0` 时，向用户复述「卡在哪一步（命令名）+ 错误摘要」，不要以空白或纯日志结束。
7. **正文图片先上传后引用**：先用 `static_page.py image_upload` 获得目标 `page_id` 下的绝对 `https://pages.quantbuddy.cn/pages/assets/...webp` URL，再写入 HTML；禁止跨页复用托管 URL。图片必须带明确 `alt` 与 `width/height`；首屏和海报目标内不得 lazy，正文下方才可 `loading="lazy"`。标准 image panel 默认启用当前页大图预览，装饰图才设 `zoomable:false`；不要用新窗口打开图片 URL。fork 必须按 manifest 的 `images[]` 上传到目标页并替换 marker，不能保留来源图片 URL。
8. **`templates` 摘要必须覆盖全部候选，落盘失败不能裸奔**：`items_summary` 的条目数量必须等于 `item_count`（完整候选去重后的真实数量，不是服务端可能未重算的 `total`），不允许只看其中一部分候选就判定 `unmatched`；一旦返回 `error:"TEMPLATES_PERSIST_FAILED"` 或 `error:"TEMPLATES_RESPONSE_SHAPE_UNEXPECTED"`（落盘失败或响应结构异常），必须先向用户说明「范式候选未能完整确认，暂缓路由判断」，禁止在这种不完整信息下判定为 `unmatched` 走自建，也**不得通过重复调用 `templates` 来补救**（每个任务仍然只能调用一次这条硬规则不变）；确需重试仅限明确的瞬时网络失败，且只重试一次。
9. **Card Runtime 先做零副作用结构预检**：含 Card Runtime artifact 的 HTML 必须由 `publish_workflow.py` 在 QBS 验证、注册、图片上传和发布前用假凭证执行 `verify_page.mjs --card-runtime-structure-only`。正文与 Card 共用凭证时用 marker 数组扇出；每个数组元素仍须全局唯一并在 HTML 中恰好出现一次。禁止空 manifest 凭证、缺少/空 `src` 的 `<img>`，也禁止注册等价的重复 Card package/grant。


## 工具一览

> 参数约定：所有脚本参数是**一个 JSON 字符串**位置参数（或 `@params.json` / 环境变量），如 `list '{"scope":"test_all"}'`。命令行也兼容 `--scope test_all` / `--key=value` 直觉写法（仅简单参数；公式、spec 等复杂结构仍走 `@file`/环境变量以免 GBK 截断）。

| 脚本 | 命令 | 作用 | 文档 |
|---|---|---|---|
| `scripts/formula_package.py` | `register` / `query` / `list` / `revoke` / `refresh` | 公式任务包：注册取数能力；query 支持 `outputs` 与 `result_mode=full|summary|last_values`，direct 使用 summary | [tools/formula_package.md](tools/formula_package.md) |
| `scripts/data_grant.py` | `register` / `query` / `list` / `revoke` / `refresh` | 数据授权：把一次 fastQuery/stockProfile/selectByComposition 请求钉死成 `grant_id`+`signature`，页面免 key 直取有界数据（取舍见「数据授权 vs 公式包」） | [tools/data_grant.md](tools/data_grant.md) |
| `scripts/build_dashboard.py` | （单命令） | spec → live 实时取数看板 HTML | [tools/build_dashboard.md](tools/build_dashboard.md) |
| `scripts/compile_bespoke_page.py` | （单命令） | **【shell 处理脚本】** bespoke 主体 HTML → 内联公共 share shell / logo / qr-mini / data-kernel 的自包含 HTML | [guides/share-shell.md](guides/share-shell.md) |
| `scripts/retrofit_share_shell.py` | （单命令） | **【shell 处理脚本】** 旧 HTML/已发布页面 → 删除旧二维码/旧页头/旧页尾，套入公共 share shell（`assets/share-shell/`），可原链接 update | [tools/retrofit_share_shell.md](tools/retrofit_share_shell.md) |
| `scripts/data_kernel_retrofit.py` | （单命令） | 按 `QB_DATA_KERNEL` marker 或严格旧内核指纹，只替换页面中的 data-kernel；零个/多个命中均拒绝写回 | [tools/data_grant.md](tools/data_grant.md) |
| `scripts/static_page.py` | `templates` / `direct_deliver` / `new_page` / `update_progress` / `publish_final` / `publish_verified` / `upload` / `update` / `download` / `image_upload` / `image_list` / `fork_prepare` / `fork_validate` / `update_template` / 其他管理命令 | 范式路由、正文图片、direct 确定性交付、首链进度、分级浏览器门禁和页面发布管理 | [tools/static_page.md](tools/static_page.md) |
| `scripts/qbs_bridge.py` | `<quant-buddy-skill tool> @params.json` / `validate_package_set @params.json` | QBV→QBS task_id 继承、并发 session 隔离和按最终 package 分批验证/续传/收据汇总 | 本节“新会话路由” |
| `scripts/publish_workflow.py` | `@params.json` | 先做 Card Runtime 零副作用结构预检，再一次完成 package-set 验证、公式包/授权注册、多 marker 扇出替换和单次 `publish_verified` | [tools/publish_workflow.md](tools/publish_workflow.md) |
| `scripts/validate_agent_reply.py` | （单命令） | 校验发布器 SHA256 绑定的终态 contract 与 Markdown 草稿，并检查公开 URL、章节结构和敏感信息；可在成功后清理任务临时参数文件 | — |
| `scripts/verify_page.mjs` | （单命令） | 发布前/发布后页面验收：1440px、390px、320px 视口，h1、占位符、横向溢出、控制台核心错误；发布前可加 `--require-browser` 强制浏览器验收；范式卡加 `--card-runtime` 连同整页验收 artifact，或 `--card-runtime-only` 跳过整页视口、只验收 artifact/manifest/required_outputs/独立 hydrate | — |
| `scripts/render_cover.py` | （被 `build_dashboard` 调用） | 封面栅格化与合成兜底：`capture_page_cover` 用系统 Edge/Chrome 无头截"封面模式页"为整页 PNG；合成封面（全幅裸图/品牌海报）走 浏览器 → 纯 Python(cairosvg/svglib) → SVG 三层兜底。跨平台、零强依赖，不影响 HTML 发布 | — |
| `scripts/render_existing_page_thumbnail.py` | （单命令） | 给已发布/官方精选 HTML 补封面：下载或读取 HTML → 解析内嵌公式包凭证 → 先取真实 outputs 并临时替换 `QB.query` → 再用系统 Edge/Chrome 截 1200×675 PNG；可带 `upload:true` 直接设置 `thumbnail_url` | [tools/static_page.md](tools/static_page.md) |
| `assets/data-kernel.js` | （前端内核，非脚本） | 手搓 bespoke 页共用的「取数 + 清洗 + 容错」一份；内联进页面 `<script>` 用 | [guides/bespoke-page.md](guides/bespoke-page.md) |
| `assets/share-shell/` | （公共组件） | 所有落地页共用的页头、页尾、刷新按钮、分享海报弹层、海报 canvas、复制链接与复制/下载行为 | [guides/share-shell.md](guides/share-shell.md) |
| `assets/live-card.css` | （公共组件） | 范式卡 artifact 的浅色卡片样式源；由 `build_dashboard.py` 作为 `data-qb-card-style` 内嵌进 card runtime artifact | [guides/essence-cover-card.md](guides/essence-cover-card.md) |
| `scripts/card_runtime_retrofit.py` | （被 static_page 调用） | 为已发布/官方精选页重建独立 card runtime artifact（`embedded-card-v1`），可原链接写回 | [tools/static_page.md](tools/static_page.md) |
| `guides/essence-cover-card.md` | （开发指南） | 页面精华浓缩为独立 4:3 card runtime artifact（`embedded-card-v1`，空白宿主独立 hydrate），并明确 artifact、范式卡快照与整页封面的职责边界 | — |

> **三条生产路**：固定页面先复用在线模板；标准看板走 `build_dashboard`（声明式快路）；要自定义版式/SVG 的设计页才写 bespoke 主体 HTML。
> 数据层统一调 `assets/data-kernel.js`（`QB.query` 取数、`QB.series/lastValue/topValues` 解包清洗），别再每页各抄 `fetch`/解包、各踩"假 0/缺口"的坑。见 [guides/bespoke-page.md](guides/bespoke-page.md)。
> 发布前用 `scripts/verify_page.mjs <html_file> --require-browser` 检查桌面与 390px/320px 移动端，确保无 `QB_SHARED_` / `replace_with_signature` / `pkg_replace` 残留、存在 `<h1>`、无关键横向溢出和核心取数脚本错误。含范式卡 artifact 的页面加 `--card-runtime`（或 `--card-runtime-only`）验收 artifact/manifest/独立 hydrate。若机器没有 Playwright/Chrome/Edge，脚本会明确标记为 `static-only`，不能当完整浏览器验收。

## 配置

`config.json`：填入 `api_key`（从 https://www.quantbuddy.cn/login 获取），或设环境变量 `QUANT_BUDDY_API_KEY`。可建 `config.local.json` 覆盖 `endpoint` / `api_key` 等（不入库）。`formula_package.py`、`build_dashboard.py`、`static_page.py` 共用同一个 `endpoint`。
