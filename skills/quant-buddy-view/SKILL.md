---
name: quant-buddy-view
slug: quant-buddy-view
author: guanzhao
version: 0.6.27
description: |
  QBV / quant-buddy-view（用户可能写成 /quant-buddy-view、/qbv、qbv 或 QBV）用于把量化数据做成「公开可分享、实时取数」的网页看板/落地页。
  Use this skill when the user asks to create, update, publish, verify, retrofit, or reuse a Quant Buddy dashboard/static page/template, including shareable pages, public URLs, formula packages, share shell, cover/essence cards, poster/share behavior, single-stock profile pages, valuation/financial profile pages, index-anomaly boards, multi-factor screeners, and commodity daily pages.
  配合 quant-buddy-skill 使用：固定页面请求先用 static_page.py templates/template 选择带 recommend:官方精选 标签的在线精选页；实时取数页必须先在 quant-buddy-skill 验证公式并确认其 api_key 可用，再用本技能注册自有公式包、替换凭证/文案、浏览器验收，并通过 static_page.py upload/update 发布或更新 pages.quantbuddy.cn 链接。默认不从本地历史样板目录或低质 HTML 骨架起步。
  用户显式唤起 /quant-buddy-view、/qbv、qbv 或 QBV，且请求不是纯咨询/代码维护/文档解释时，默认视为可分享活页任务：读完本技能约束后先查官方精选+社区范式卡判定 direct/fork/unmatched；默认 direct 先交付现成链接、fork/unmatched 用 new_page 返回首链；当 config.json._channel=feishu-group 时，所有分支都禁止提前发送链接，只在终态交付 playground 链接。
  Do not use this skill for one-off 行情查询、普通股票涨跌幅/估值问答、选股/回测探索；those belong to quant-buddy-skill unless the user explicitly wants a reusable/shareable page.
runtime: python
primaryCredential: quant-buddy API Key
metadata:
  version: 0.6.27
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
    description: quant-buddy 平台 API Key。默认存储于 skill 目录下 config.json 的 `api_key` 字段。优先级（高到低）：① 调用方在工具调用参数里显式传入的 `api_key`（如 Playground 场景，仅当次调用生效，不落盘）；② 环境变量 QBV_API_KEY（同一档的显式覆盖通道，专给"这次调用要用哪个 key"、但不方便/不想改现有 @file 参数去塞 api_key 的场景，比如 `publish_workflow.py @publish-plan.json`——该 plan 文件按设计不含凭证）；③ config.json / config.local.json 的 `api_key`；④ 环境变量 QUANT_BUDDY_API_KEY（仅①②③都为空时才兜底，不是常规覆盖手段，语义与 QBV_API_KEY 完全不同，不要混用）。仅作为 HTTP `Authorization` 头发送给 networkEndpoints 中声明的 quantbuddy 域名用于鉴权；公式包「取数」和看板内实时取数凭 signature，不需要 api_key。
    how_to_get: "https://www.quantbuddy.cn/login"
requiredConfigPaths:
  - path: config.json
    required: true
    description: 仅包含 quant-buddy api_key 与公开端点配置，由本地脚本读取。
requiredEnvVars:
  - name: QBV_API_KEY
    required: false
    sensitive: true
    description: 可选，本次调用的显式 api_key 覆盖（与工具调用参数里的 `api_key` 字段同一优先级），仅本进程生效、不落盘。适用于"手上是一份现成的 @file 参数（如 publish-plan.json），不想现改这份文件去塞 api_key"的场景；不要和 QUANT_BUDDY_API_KEY 混用，两者优先级和用途完全不同（见上面 api_key 字段的优先级说明）。
  - name: QUANT_BUDDY_API_KEY
    required: false
    sensitive: true
    description: 可选。仅在 config.json / config.local.json 都没有 api_key、且没有更高优先级的 api_key/QBV_API_KEY 覆盖时才兜底生效，不是常规覆盖手段。多步任务里想让某次调用用别的 key，请用 api_key 参数或 QBV_API_KEY，不要指望设置这个环境变量会覆盖 config.json 已有的默认 key。
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

> **0.6.27 变更**：`new_page` 在完整执行 `templates(recommend:"all")` 后还必须由 Agent 显式提交 `routing_decision`：fork 传本次 `items_summary` 中的 `source_template_id + reason_code`，unmatched 传最接近候选、实质能力缺口及原因。脚本核验候选属于当前 task、补齐候选标签快照并把决定与 `page_id` 写入既有 `routing-credential.json`。`publish_final` 在任何网络写入前复核该决定：已选 fork 但未执行 `fork_prepare` 时返回可恢复的 `ROUTING_RECONFIRM_REQUIRED`；确认模板确实不适用时可用显式 `routing_override` 改判 unmatched。`build_dashboard` 不受限制，旧任务无路由记录时保持兼容。
>
> **0.6.26 变更**：修复 `emit:"panel_block"` 嵌入 bespoke 页面时的两处真实崩溃/误判（真实任务实测复现并核实过）：① `_RENDER_JS_TEMPLATE` 整体包一层 IIFE，`fmt`/`esc`/`normalize`/`colIdx` 等不再泄漏到全局作用域，不会再跟宿主 bespoke 页面自己的同名变量（如 `const fmt=...`）撞名报 `SyntaxError`——宿主页面不需要手工包 IIFE 就能安全共存；`_BOOTSTRAP_BLOCK_RE`/`_EMBEDDED_BOOTSTRAP` 同步补上外层 IIFE 的收尾。② `cmd_panel_block` 新增可选 `host_html_file`/`include_data_kernel` 参数：给了宿主页面路径会自动探测是否已有取数内核（marker 版或历史手写等价版，复用 `data_kernel_retrofit.py` 现成判断逻辑），检测到则跳过重复内联 `data-kernel.js`，避免同页两份内核顶层变量重复声明崩溃。③ `chart_edit.py::_extract_boot` 改用 `json.JSONDecoder().raw_decode` 定位 `BOOT` 边界，不再要求 `const BOOT = {...};` 后面严格紧跟 `let LAST_OUTPUTS`，marker 区块内部多出的空白/注释不会再让 `inspect` 误判 `legacy:true`。④ 修复 fork 流程 `decisions` 契约不一致（两次真实任务复现）：`fork_prepare` 之前只在 `review_update_params_file` 里写一个空 `"decisions": {}`，而 `required_decisions` 给出的 `decision_id` 又是扁平点号字符串（如 `roles.package.package_001.target_formulas`），导致 Agent 把它当提交用的 key 直接写，被 `apply_review_decisions` 以 `FORK_REVIEW_DECISIONS_INVALID` 拒绝。现在 `fork_prepare`/`fork_review_update` 改为写入 `build_decisions_skeleton()` 生成的嵌套占位骨架（`{"roles":{"<role_id>":{...}}}`），Agent 只需要在骨架里填空；同时修掉一个连带 bug——`fork_review_update` 原来每轮无条件把 `decisions` 重置成 `{}`，多角色分轮填写时会丢掉已经确认的同业映射，现在改成按最新 review 重新生成骨架，已填值会被保留。⑤ **fork 资产替换改为由 `target_asset` 驱动**（真实任务复现：Agent 连撞三次 `未在来源 HTML 找到替换项` 后放弃 fork、退回自建）。病根是职责分配——`fork_prepare` 本来就收到了 `target_asset`，却只把它记进 manifest，反过来要求 Agent 手写 `asset_replacements`，即让 Agent 去猜一个它从没见过、且流程明令禁止读取的 HTML 里代码究竟写成 `SH600900` 还是 `600900.SH`。现在改为：Agent 负责说"换成哪只标的"，脚本负责推导来源主资产（模板公式词频 + 标题）并扫描来源 HTML 得出代码的实际书写形态，**只替换页面里真实存在的写法**，这类报错结构上不再可能发生；只给代码时先反查同级 quant-buddy-skill 资产库补名字。多资产/指数类范式推不出主资产时 fail-closed 返回 `FORK_SOURCE_ASSET_AMBIGUOUS`，报错自带候选资产名、来源 HTML 中真实存在的代码写法和可照抄的调用示例，由 Agent 传 `source_asset` 指定。替换后主资产若仍残留，在写出工作 HTML **之前**就返回 `FORK_SOURCE_ASSET_RESIDUAL`（同业资产不在检查范围内，它们本就该由 `target_slots` 决策替换），不再等到发布成功后才发现文案还是源模板原样。`asset_replacements` 降级为可选覆盖，老调用零改动。
>
> **0.6.25 变更**：`build_dashboard.py` 新增 `emit:"panel_block"` 局部产出模式——只生成带 `QBV_RENDER_JS_START/END` marker 的图表 `<script>` 片段（不生成整页 HTML），供 bespoke（手写）页面把折线/柱状/双轴/雷达图这类图表交给标准声明式引擎画：panel 加 `target_selector` 指向 bespoke 布局里已有的容器，渲染进去不包卡片外壳。`renderChart` 新增双轴（`dual_axis`+`right_series`）与迷你走势图（`sparkline`），新增 `renderRadarChart`（`type:"radar"`）。`_render_js_for_boot()` 统一了「整页启动 / 嵌入式启动」的选择逻辑，`_render_html` 与 `chart_edit.py::_patch_page` 共用，避免嵌入式图表被编辑后误换成会二次初始化 `QBShareShell` 的整页启动代码。`chart_edit.py::add_series` 新增 `axis:"right"` 参数。目的：终结「bespoke 页面里的图表只能整页手工补丁」——用这套局部产出模式重建模板后，图表可直接用 `chart_edit.py` 现成的定点编辑操作维护，不需要为 bespoke 页面另造一套编辑机制。`compile_bespoke_page.py` 新增非阻塞 lint，检测把行数据硬编码进 JS 调用参数（如 `setBar($("..."),[...])`）的写法，提示改用 `data-qb-bar-row` 属性驱动。详见 `guides/bespoke-page.md`「统一原则」一节。
>
> **0.6.24 变更**：`single_stock_deep_dive_v1` 启用数据驱动柔性回复：公式验证成功后复用 `data_id`，按兼容 `readData` 模式每批最多10个补读模板所需值；Grant直接复用验证响应。整个过程不重算公式、不重查已注册 package/grant。终态 contract 绑定 `reply_data_evidence_v1` 文件与 SHA256；七节标题必须完整保留，有数据的模板字段必须输出，无数据整节使用标准说明。`feishu-group` 终态 contract 同时声明最多 5 张 Markdown 表格，模板用列表或行内文本承载其余数据；validator 成功后必须原样发送 `validated_markdown`。
>
> **0.6.23 变更**：所有正式任务产物统一进入 `trace_context begin` 返回的跨平台 `task_temp_dir`；新 fork 固定执行 `fork_prepare → fork_review_update → publish_workflow`。Agent 只填写生成的 review-update 参数文件中声明的业务决策，不直接编辑标准 fork HTML/review，也不创建一次性辅助脚本。`fork_review_update` 生成绑定 task/page/manifest/review/HTML 哈希的 receipt；缺失、不完整或过期时，发布器在首次网络调用前 fail-closed。所有返回命令使用当前 `sys.executable`，不硬编码 `python`/`python3`。
>

> **0.6.22 变更**：补强 Card Runtime retrofit 的日期与视觉保真：模板不再内置历史日期，hydrate 从嵌套输出中选择最新可用日期；已识别页面继续生成与内容语义匹配的专属视觉，不回退为通用三指标布局。详细契约见 `guides/essence-cover-card.md`。

> **0.6.21 变更**：新增活页 UI/UX 系统指南，以“稳定体验骨架 + 可变内容表达”组织字体、主题 token、页面原型、模式库、响应式转换、实时状态和验收矩阵；`SKILL.md` 只保留按需路由，浏览器批注细节继续由 `ui-refinement` profile 与维护指南承载。
>
> **0.6.20 变更**：分享海报预览新增 `data-qb-runtime-src` 合同，允许用户点击分享前保持空 `src`；静态预检与浏览器图片门禁只豁免显式声明且尚未赋值的运行时图片，普通正文图片仍必须提供非空 `src`。`fork_prepare` 会为旧版 `sharePosterImage` 自动补充该合同，不再要求任务临时塞透明占位图。fork 的 PE/PB 水位输出允许继承来源模板的明确算法与正整数窗口（如 `排序水位(...,250)` 或 `数值水位(...,750)`），不再强制统一改成250日，但仍必须通过 QBS 验证且禁止直接别名原始指标。Card Runtime 完整重建同时改为显式视觉合同并 fail-closed：未命中页面专属视觉、也未传 `visual_contract` 时返回 `CARD_VISUAL_REQUIRED`，不再自动挑前三个 outputs 生成三行指标卡；新建 artifact 必须声明 `data-qb-card-visual-kind` / manifest `visual_kind` 并通过 `--require-card-visual-contract`。`numeric-focus` 只在显式选择时可用，且必须是“一个主数字 + 最多两个解释项”，不能退化为三个等权矩形；新增 `basis-structure` 基差轴视觉作为首个合同化示例。
>
> **0.6.19 变更**：新 fork 默认由 `fork_prepare` 生成 `fork_manifest_v2`、脱敏 HTML、credential-free review 和 publish plan；自动识别页面/Card Runtime 凭证、聚合相同合同并生成唯一 Marker。package role 明确区分模板接口原始 `source_contract.formulas/nodes` 与新包请求 `target_registration_contract.formulas/reads/begin_date`，来源 `nodes[].data_id` 不进入目标注册合同。Agent 只填写目标同业槽位、复杂跨资产公式及业务文案，`publish_workflow.py` 从目标注册合同派生验证与注册，并在第一次网络写入前检查 review、required outputs/reads、估值分位语义、Grant 合同差异和 Card Runtime 结构；v1 任务继续兼容，本版不修改图片门禁，不实现注册幂等。已发布范式卡的 Card Runtime 协议同时新增 `preserve_visual` 路径，只更新 manifest/runtime 与 ready 契约，逐字节保留原 template/style；`retrofit_card_runtime` 的独立验收固定使用 `--card-runtime-only`。禁止用通用三指标重建路径覆盖已有视觉 artifact；只有 artifact 缺失且明确选择 `numeric-focus` 时才允许生成数字主导卡片。
>
> **0.6.18 变更**：`publish_workflow.py` 在 QBS 验证、注册和上传等网络写入前，先以假凭证运行 Card Runtime 结构预检，提前拦截空 manifest 凭证、缺少/空 `src` 的图片等结构错误；package/grant 的 `markers.package_id`、`markers.grant_id`、`markers.signature` 现在兼容单个字符串或非空字符串数组，同一次注册可扇出替换页面正文与 Card Runtime 中的多个唯一 marker，避免为同一数据合同重复注册公式包。
>
> **0.6.17 变更**：`templates` 不再把完整候选池原样打到 stdout——响应改为 `item_count` + 覆盖全部候选的 `items_summary`（不是 top-N）+ 完整结果落盘产生的 `full_result_file`/`full_result_sha256`；完整候选（含 `agent_reply_hint`/`page_context`）落盘到系统临时目录，交由既有 `cleanup_task_temp_files` 自动回收。落盘失败（`TEMPLATES_PERSIST_FAILED`）或响应结构异常（`TEMPLATES_RESPONSE_SHAPE_UNEXPECTED`）时直接返回错误，不再退化为把完整结果打印到 stdout——这是为了修复"候选池被外层工具输出预算截断、又没有另存一份，导致误判 unmatched 走自建"的事故根因。`templates` 现在也需要 Trace Context（task_id）。
>
> **0.6.16 历史变更**：模板接口开始返回来源公式原文。0.6.19 起这些语义只投影到 credential-free `fork-review.json`：主资产自动替换、同业矩阵生成槽位、复杂跨资产公式要求完整审核；Agent不再读取带来源 ID/Marker 的底层 runtime contract。

> **Fork 数据通道继承硬规则**：fork 的目标是替换标的并保持来源范式运行合同，不是重新设计数据层。来源模板某一角色使用公式包，目标页同一角色继续使用公式包；来源使用 `fast_query` / `stock_profile` / `composition_select` 数据授权，目标页继续使用同 kind、同 query_type、同响应形状的数据授权。禁止仅因“财务数据通常可走 fast_query(report)”就在 fork 中把来源财务公式包改成 grant，也禁止反向把来源 grant 改成公式包。只有 `unmatched` / 明确从零重建时才重新做通道选择；此时平台白名单报告期财务优先 `fast_query(query_type="report")`。
>
> **0.6.15 变更**：新增活页正文图片上传/列表、可在当前页面点击放大的声明式 image panel、publish_workflow 图片 marker、fork 同页复制和浏览器图片门禁；PNG/JPEG/WebP 由服务端统一转为同域 WebP，发布必须保持图片与目标 `page_id` 同属。
>
> **0.6.14 变更**：`data-kernel` 可在浏览器实时下载并解析 FastQuery `mode:"csv"`，自动 hydrate 为兼容的 `results[].fields[].series`；标准看板和构建期体检共用同口径，发布门禁等待 `QB_DATA_RUNTIME` 完成后再验收。
>
> **feishu-group 渠道**：打包渠道为 `feishu-group` 时，direct/fork/unmatched/update 等所有分支禁止发送非终态链接；终态 contract 统一把 `pages.quantbuddy.cn/pages/<owner>/<page_id>.html` 转成 `www.quantbuddy.cn/playground/<owner>/<page_id>`，内部发布与验收仍使用原始托管 URL。

0. 在任何后端请求前运行 `scripts/trace_context.py begin`，保存唯一 `task_id` 并在后续命令中复用。这步本身就是后端写入调用，必须和后续命令带同一个身份（`QBV_API_KEY` 环境变量或参数里的 `api_key`），不带会被记成 skill 默认账号。
1. 运行一次 `scripts/static_page.py templates`，传 `recommend:"all"`，查询官方精选+社区命中池。
2. direct 命中后，普通渠道先把列表返回的现成 URL 发给用户；`feishu-group` 不发链接，直接运行一次 `static_page.py direct_deliver` 完成模板详情、单次取数和终态确认。
3. fork/unmatched 调用 `new_page` 时由 Agent 根据 `items_summary` 显式传 `routing_decision`，脚本校验并与同一 `page_id` 绑定；普通渠道立即发送首链，`feishu-group` 仅内部持有该链接，验证目标公式后继续注册、替换与 `publish_verified`。
4. 所有分支最终按 `agent_reply_contract` 和回复模板生成草稿，再运行一次 `validate_agent_reply.py`。

## 何时用本技能 vs quant-buddy-skill

- **探索/一次性查询**（"茅台今天涨跌幅"、"跑个均线金叉回测看看"）→ 用 **quant-buddy-skill**。
- **要一个能反复看、能发给别人、数据会自动更新的页面** → 探索清楚后切到 **quant-buddy-view**。

## 新会话路由：先查范式卡（templates）判命中

先建立 Trace Context，再查询范式卡。`begin` 是**真实的后端写入调用**（落审计表），和后续命令一样需要本次任务的身份——必须与后续命令用同一个 key，否则这一步会被记到 skill 默认账号名下，任务链路从第一条记录起就归错人：

```bash
# 身份走环境变量（exec 日志里会脱敏）；不要把 key 拼进命令串，命令是原样记录的
QBV_API_KEY=<本次任务的 key> python scripts/trace_context.py begin '{"user_query":"用户原始问题"}'
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
  - 先运行 `new_page`，并由 Agent 根据本次 `items_summary` 传 `routing_decision:{"mode":"fork","source_template_id":"page_xxx","reason_code":"same_paradigm_different_asset"}`。脚本只校验候选归属与规则并记录决定，不替 Agent 做语义匹配。取得目标 `page_id` 后，以同一 `task_id` 调 `fork_prepare`，同时传 `source_template_id + target_page_id + target_asset`（推荐 `{"name":"中国中车","code":"601766"}`）。新 fork 自动生成 `fork_manifest_v2`、脱敏 `*.fork.html`、credential-free `*.fork-review.json` 与 `*.publish-plan.json`；来源 HTML 仅内部校验，不在普通结果中主动暴露。
  - **资产替换的职责分工**：Agent 说清楚"换成哪只标的"，脚本负责"这只标的在页面里写成什么样"。来源主资产由脚本从模板公式词频 + 标题推导，代码的实际写法（`SH600900` / `600900.SH` / 裸 `600900`）由脚本扫描来源 HTML 得出，只替换真实存在的写法——不要去猜来源 HTML 里代码写成什么样，你看不到那个文件。多资产/指数类范式推不出主资产时返回 `FORK_SOURCE_ASSET_AMBIGUOUS`（报错自带候选名与可照抄的调用），用 `source_asset` 显式指明后重试。`asset_replacements` 仅作可选覆盖。替换后主资产若仍有残留，在写出工作 HTML 前就返回 `FORK_SOURCE_ASSET_RESIDUAL`，不会等到发布后才发现。
  - Agent只在 `fork_prepare` 生成的 `review_update_params_file.decisions` 中填写 `required_decisions` 声明的业务决策：规则性同业矩阵填 `target_slots`，复杂跨资产公式填 `target_formulas`，标签替换填 `page_label_replacements`。`decisions` 已按角色预生成嵌套占位骨架（`{"roles":{"<role_id>":{...}}}`），只需要在骨架里补全空值，不要新增/改写顶层字段，也不要把 `required_decisions` 里的扁平 `decision_id`（如 `roles.package.package_001.target_formulas`）当成提交用的 key。禁止直接编辑标准 fork HTML/review。
  - Grant按来源角色完整继承 `kind/query_type/fields/dimensions/window_days/result_mode` 与 CSV/inline 合同，只允许自动修改 manifest 声明的资产范围字段；其他变化必须填写 `contract_change_reason`。
  - 先运行 `fork_prepare` 返回的 `review_update_command`；只有 `review_state.status=complete` 且生成 review receipt 后，才运行 `publish_command`。发布器从同一 canonical package/Grant 合同派生 QBS 验证与注册，自动检查 required outputs、公式左值、reads、PE/PB 水位公式具有明确算法与正整数窗口、Grant fingerprint、Marker 唯一性与 Card Runtime 结构，并让一次注册结果扇出到页面/Card全部位置。
  - `fork_manifest_v2` 禁止手工传 packages、grants、Marker 或完整 workflow JSON，出现 `MANUAL_RUNTIME_BINDINGS_FORBIDDEN` 时回到生成的 publish plan，不要写临时替换脚本。v1 prepared task 继续按旧接口发布。

  - 这不是建议——`publish_verified` 服务端会按 fork manifest 里的凭证数量强制核验：手工分步调用 `publish_verified(task_id, page_id, html_file, source_template_id, fork_manifest_file, validation_receipt_files)` 只有在这个页面**零凭证**（纯静态改造）时才会放行，否则直接拒绝并返回 `error:"PUBLISH_WORKFLOW_REQUIRED"`；出现该错误时改走 `publish_workflow.py`，不要绕过。
  - 回复 = 回复模板格式 + **自己的新链接**（数值同样用自己的包/grant query 填）。
- **③ 未命中**（无匹配范式）：Agent 根据 `items_summary` 调 `new_page` 时传 `routing_decision:{"mode":"unmatched","closest_template_id":"page_xxx","reason_code":"required_capability_missing","reason":"候选缺少用户要求的核心能力"}`；存在候选却只因标的/范围不同而判 unmatched 会被提示改走 fork。记录成功后继续 `build_dashboard` / bespoke 自建 → 其余同 ②；`feishu-group` 同样不发送进度链接。

> 后续追问：自己的链接 → `update` 同 `page_id`；命中的官方/社区链接要改 → 只能转 ② fork 成自己的链接后再改。

## 默认路由

- **固定页面形态**（个股速览、估值体检、成分股异动榜、多因子选股看板、商品日报等）：先 `templates` 查询官方精选+社区命中池；direct 直接用列表 URL + revision，fork 才读取和改写模板详情。
- **宽宝活卡 / 精华卡 / 封面卡（范式卡 artifact）**：把页面精华做成独立 **card runtime artifact**（`embedded-card-v1`：页面内嵌 `<template data-qb-card-template>` + `data-qb-card-manifest` + `QBCardRuntimeV1` runtime），供官网卡片流在空白宿主中**独立 hydrate**。静态首帧 `card_snapshot_url` 由 `skill_server` 按 artifact hash 生成，是页面封面的唯一来源（整页缩略图能力已下线）。按 [guides/essence-cover-card.md](guides/essence-cover-card.md) 生成；已发布页优先用 `preserve_visual:true` 只升级协议。完整重建必须命中页面专属视觉或显式传 `visual_contract`，否则 `CARD_VISUAL_REQUIRED` 停止；用 `verify_page.mjs --card-runtime-only --require-card-visual-contract` 验收新 artifact。卡片必须官网浅色系、固定信息骨架、可变核心可视化；不再用旧的 `?cover=1` URL 模式。
- **没有合适在线模板**：再走 `workflows/dashboard-end-to-end.md`，用 `build_dashboard` 生成声明式实时看板。
- **声明式看板也不够**：才走 `guides/bespoke-page.md` 写 bespoke 主体 HTML，并用公共 shell 编译成自包含页面。
- **改一个已有图表**（叠加/去掉一条线、改时间窗口、查真实数据）：优先 `workflows/edit-existing-chart.md` +
  `scripts/chart_edit.py`，只动被要求的那一处、不重新验证/计算页面上其它无关系列；只有目标页面是 legacy
  （`chart_edit.py inspect` 判定，多为本次改动之前生成的老页面）或改动本质上要求整页重算/换版式，才落回
  下面的整页重建。
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
- prepared fork task 禁止 `build_dashboard`；v2只填写生成的 review-update 决策文件，依次运行 `review_update_command` 和 `publish_command`。只有旧 v1任务继续使用手工 `fork_validate` 路径。
- 带 `task_id` 的进度从 `package_register` 起必须传同任务的 `validation_receipt_files`，收据必须为 `completed + success=true + failures=[]`；静态页可传明确的 `validation_not_required_reason`。
- 最终回复必须按回复模板输出并且只能使用 contract 的 `public_url`；`feishu-group` 下该字段必须是 `https://www.quantbuddy.cn/playground/<owner>/<page_id>`。一般模板依据 `reply_render_policy` 与 `reply_data_availability` 删除结构性不存在的字段、整列、整行和空可选章节。`single_stock_deep_dive_v1` 还必须读取 SHA256 绑定的 `reply_data_evidence_file`，保留全部七节标题，有数据的模板字段全部输出，整节无数据使用标准说明；只有有效结构中的偶发缺值才写 `--`。若 `delivery_policy.max_markdown_tables` 存在，整篇不得超过该表格数，超出的结构改用列表或行内文本且不得丢数据。validator 返回 `valid=true` 后原样发送 `validated_markdown`，不得再次压缩或改写，也不得暴露原始托管 URL、本地路径、凭证或内部日志。
- 最终回复前只运行一次发布器返回的 `reply_validation_command`，并把同时返回的 `reply_validation_env`（形如 `{"QBV_API_KEY": "..."}`）原样作为该次执行的环境变量传入——validator 是独立子进程，不传会退回 `config.json` 的默认账号，任务终态被记成错误的用户。禁止把该 key 拼进命令串：命令在日志里原样记录，只有 env 会脱敏。validator 必须读取发布器生成的 `contract_file + contract_sha256`，不得手工重建精简 contract。direct 使用 `direct_deliver` 返回的完整 task ID 路径和命令，成功后自动清理。`valid=true` 后不再执行任何工具调用。
- 没有 terminal contract 禁止完成任务。唯一例外是成功的 `waiting_input` checkpoint。
- 性能门槛：普通渠道模板命中到首链不超过 5 秒；所有渠道 terminal 到最终回复不超过 45 秒，完整活页任务以 10 分钟内完成为常态目标，用户可见消息间隔不超过 60 秒。回复证据补读不设额外人工截止时间，但必须按模板字段过滤、相同模式批量读取且每批最多10个；禁止公式重算和 package/grant 重查。
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
| 增量维护 | 单图表增删改查 | [workflows/edit-existing-chart.md](workflows/edit-existing-chart.md) | 自己的已发布页面要加/删一条线、改时间窗口、查真实数据——只改一个图表，不是整页重建 |
| 开发指南 | 自定义页面 | [guides/bespoke-page.md](guides/bespoke-page.md) | `build_dashboard` 做不出的自定义 HTML/CSS/SVG 页面，或迁移已有 HTML |
| 迁移工具 | 旧页套公共外壳 | [tools/retrofit_share_shell.md](tools/retrofit_share_shell.md) | 已发布/已生成 HTML 需要去掉旧二维码、旧页头、旧页尾，并保留同一个 `page_id` 更新 |
| 设计系统 | 活页 UI/UX 系统 | [guides/live-page-ui-ux-system.md](guides/live-page-ui-ux-system.md) | 新建或整体重构活页时，选择页面原型、主题 token、字体/密度、可组合模式和响应式转换；统一体验底线但保留页面身份 |
| 维护指南 | 浏览器批注与整页 UI refinement | [guides/browser-feedback-refinement.md](guides/browser-feedback-refinement.md) | 用户针对已有自有页面的字体层级、间距、章节导航、sticky/折叠、响应式或分享交互提出修改；保持同一 `page_id`、runtime 合同和页面视觉身份 |

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
2. **公式必须先验证再注册（硬门槛）**：fork v2 由 `publish_workflow.py` 根据 review 解析出的最终 package 边界自动调用 `validate_package_set`，验证与注册从同一个 `{formulas,reads,begin_date}` 合同派生。Agent负责检查 review 中的公式语义、目标资产和同业映射，不得绕过生成的 plan 单独注册；复杂跨资产公式未审核、required outputs/reads 不一致，或 PE/PB 水位输出没有明确算法与正整数窗口时，发布器在网络调用前拒绝。fork 默认继承来源模板已经声明且能通过 QBS 的水位口径，不强制改成固定250日。
3. **验证参数也要换干净**：调用 `runMultiFormulaBatchStream` 时，`user_query` 必须反映当前用户请求和当前资产；若传 `task_id` 必须为本次新任务。复制示例时不能只替换 `formulas`，却留下“贵州茅台 factsheet”等旧 `user_query`，否则后台审计和回放会被污染。
4. **signature 是凭证**：不要打印到面向最终用户的对话里；看板会把它写进公开 HTML 供实时取数，发布前确认可接受。
5. **标签来源不要写 Agent**：显式传 `scene_tags` / `paradigm_tags` 时，`tagging_method` 用 `manual` / `migration` / `unknown`；需要 LLM 自动识别就调用 `scripts/static_page.py autotag`。不要再传 `tagging_method:"agent"`，也不要在 `tagging_meta.method` 里写 `agent`。
6. **失败要说清**：脚本返回 `code != 0` 时，向用户复述「卡在哪一步（命令名）+ 错误摘要」，不要以空白或纯日志结束。
7. **正文图片先上传后引用**：先用 `static_page.py image_upload` 获得目标 `page_id` 下的绝对 `https://pages.quantbuddy.cn/pages/assets/...webp` URL，再写入 HTML；禁止跨页复用托管 URL。图片必须带明确 `alt` 与 `width/height`；首屏和海报目标内不得 lazy，正文下方才可 `loading="lazy"`。标准 image panel 默认启用当前页大图预览，装饰图才设 `zoomable:false`；不要用新窗口打开图片 URL。fork 必须按 manifest 的 `images[]` 上传到目标页并替换 marker，不能保留来源图片 URL。
8. **`templates` 摘要必须覆盖全部候选，落盘失败不能裸奔**：`items_summary` 的条目数量必须等于 `item_count`（完整候选去重后的真实数量，不是服务端可能未重算的 `total`），不允许只看其中一部分候选就判定 `unmatched`；一旦返回 `error:"TEMPLATES_PERSIST_FAILED"` 或 `error:"TEMPLATES_RESPONSE_SHAPE_UNEXPECTED"`（落盘失败或响应结构异常），必须先向用户说明「范式候选未能完整确认，暂缓路由判断」，禁止在这种不完整信息下判定为 `unmatched` 走自建，也**不得通过重复调用 `templates` 来补救**（每个任务仍然只能调用一次这条硬规则不变）；确需重试仅限明确的瞬时网络失败，且只重试一次。
9. **Card Runtime 先做零副作用结构预检**：含 Card Runtime artifact 的 HTML 必须由 `publish_workflow.py` 在 QBS 验证、注册、图片上传和发布前用假凭证执行 `verify_page.mjs --card-runtime-structure-only`。正文与 Card 共用凭证时用 marker 数组扇出；每个数组元素仍须全局唯一并在 HTML 中恰好出现一次。禁止空 manifest 凭证；普通 `<img>` 必须有非空 `src`，仅显式声明 `data-qb-runtime-src` 且等待运行时赋值的预览图可以暂时为空；同时禁止注册等价的重复 Card package/grant。
10. **建页前必须先查范式卡并显式确认路由**：`new_page` 会校验当前任务已用 `templates(recommend="all")` 查过完整范式池，并要求 Agent 根据 `items_summary` 传 `routing_decision`。未查模板返回 `ROUTING_TEMPLATES_REQUIRED`；未提交决定返回 `ROUTING_DECISION_REQUIRED`；fork 引用的来源或 unmatched 的最接近候选必须属于本次结果。范式相同仅标的/范围不同时使用 fork reason，不得以此判 unmatched。`publish_final` 发现已选 fork 却没有 fork task binding 时，在网络写入前返回可恢复的 `ROUTING_RECONFIRM_REQUIRED`；只有确认存在实质能力缺口时才用 `routing_override` 显式改判。`build_dashboard` 不受限制，direct 不建页，也不受影响。
11. **本地验收与公网验收分责**：`fork-local` 在本地 `file://`（origin=null）下用放开同源策略的测试浏览器跑真实取数渲染（`security_mode:"disabled-web-security"`），布局/占位符/运行时错误/图片/Card Runtime 门禁照常执行；`public-smoke` 保持浏览器默认安全策略，数据接口 CORS/`Failed to fetch`/运行时失败仍严格拦截。平台注入的 `/webapi/skill/track` 分析埋点是 fire-and-forget，其 CORS/网络失败降为 `non_core_console_warnings`，不再让成功页面发布失败；数据接口（`queryDataGrant`/`queryFormulaPackage`）的失败仍是阻塞性核心错误。


## 工具一览

> 参数约定：所有脚本参数是**一个 JSON 字符串**位置参数（或 `@params.json` / 环境变量），如 `list '{"scope":"test_all"}'`。命令行也兼容 `--scope test_all` / `--key=value` 直觉写法（仅简单参数；公式、spec 等复杂结构仍走 `@file`/环境变量以免 GBK 截断）。

| 脚本 | 命令 | 作用 | 文档 |
|---|---|---|---|
| `scripts/formula_package.py` | `register` / `query` / `list` / `revoke` / `refresh` | 公式任务包：注册取数能力；query 支持 `outputs` 与 `result_mode=full|summary|last_values`，direct 使用 summary | [tools/formula_package.md](tools/formula_package.md) |
| `scripts/data_grant.py` | `register` / `query` / `list` / `revoke` / `refresh` | 数据授权：把一次 fastQuery/stockProfile/selectByComposition 请求钉死成 `grant_id`+`signature`，页面免 key 直取有界数据（取舍见「数据授权 vs 公式包」） | [tools/data_grant.md](tools/data_grant.md) |
| `scripts/build_dashboard.py` | （单命令，`emit:"panel_block"` 走局部产出） | spec → live 实时取数看板 HTML；局部产出模式只生成带 marker 的图表 `<script>` 片段，供 bespoke 页面内嵌图表用 | [tools/build_dashboard.md](tools/build_dashboard.md) |
| `scripts/chart_edit.py` | `inspect` / `add_series`（支持 `axis:"right"` 双轴）/ `remove_series` / `set_window` / `query_data` | 已发布页面单个图表的增删改查：只动被要求的那一处，不重新验证/计算页面上其它无关系列 | [tools/chart_edit.md](tools/chart_edit.md) |
| `scripts/compile_bespoke_page.py` | （单命令） | **【shell 处理脚本】** bespoke 主体 HTML → 内联公共 share shell / logo / qr-mini / data-kernel 的自包含 HTML | [guides/share-shell.md](guides/share-shell.md) |
| `scripts/retrofit_share_shell.py` | （单命令） | **【shell 处理脚本】** 旧 HTML/已发布页面 → 删除旧二维码/旧页头/旧页尾，套入公共 share shell（`assets/share-shell/`），可原链接 update | [tools/retrofit_share_shell.md](tools/retrofit_share_shell.md) |
| `scripts/data_kernel_retrofit.py` | （单命令） | 按 `QB_DATA_KERNEL` marker 或严格旧内核指纹，只替换页面中的 data-kernel；零个/多个命中均拒绝写回 | [tools/data_grant.md](tools/data_grant.md) |
| `scripts/static_page.py` | `templates` / `direct_deliver` / `new_page` / `update_progress` / `publish_final` / `publish_verified` / `upload` / `update` / `download` / `image_upload` / `image_list` / `fork_prepare` / `fork_review_update` / `fork_validate` / `update_template` / 其他管理命令 | 范式路由、正文图片、direct 确定性交付、首链进度、分级浏览器门禁和页面发布管理 | [tools/static_page.md](tools/static_page.md) |
| `scripts/qbs_bridge.py` | `<quant-buddy-skill tool> @params.json` / `validate_package_set` / `validate_grant_set` | QBV→QBS task_id 继承；按最终 package/Grant 合同验证并生成 fingerprint 绑定收据 | 本节“新会话路由” |
| `scripts/publish_workflow.py` | `@publish-plan.json` | manifest v2驱动 review/合同预检、package+Grant验证、每role一次注册、多Marker扇出替换和单次 `publish_verified`；v1 JSON兼容 | [tools/publish_workflow.md](tools/publish_workflow.md) |
| `scripts/validate_agent_reply.py` | （单命令） | 校验发布器 SHA256 绑定的终态 contract 与 Markdown 草稿，并检查公开 URL、章节结构和敏感信息；可在成功后清理任务临时参数文件 | — |
| `scripts/verify_page.mjs` | （单命令） | 发布前/发布后页面验收：标准三视口、h1、占位符、横向溢出、控制台核心错误；批注迭代可用 `--profile ui-refinement`、`--extra-viewport` 与 `--min-visible-font-px`；范式卡加 `--card-runtime` 或 `--card-runtime-only` | [guides/browser-feedback-refinement.md](guides/browser-feedback-refinement.md) |
| `assets/data-kernel.js` | （前端内核，非脚本） | 手搓 bespoke 页共用的「取数 + 清洗 + 容错」一份；内联进页面 `<script>` 用 | [guides/bespoke-page.md](guides/bespoke-page.md) |
| `assets/share-shell/` | （公共组件） | 所有落地页共用的页头、页尾、刷新按钮、分享海报弹层、海报 canvas、复制链接与复制/下载行为 | [guides/share-shell.md](guides/share-shell.md) |
| `assets/live-card.css` | （公共组件） | 范式卡 artifact 的浅色卡片样式源；由 `build_dashboard.py` 作为 `data-qb-card-style` 内嵌进 card runtime artifact | [guides/essence-cover-card.md](guides/essence-cover-card.md) |
| `scripts/card_runtime_retrofit.py` | （被 static_page 调用） | 为已发布/官方精选页重建独立 card runtime artifact（`embedded-card-v1`），可原链接写回 | [tools/static_page.md](tools/static_page.md) |
| `guides/essence-cover-card.md` | （开发指南） | 页面精华浓缩为独立 4:3 card runtime artifact（`embedded-card-v1`，空白宿主独立 hydrate），并明确 artifact、范式卡快照与整页封面的职责边界 | — |

> **三条生产路**：固定页面先复用在线模板；标准看板走 `build_dashboard`（声明式快路）；要自定义版式/SVG 的设计页才写 bespoke 主体 HTML。
> 数据层统一调 `assets/data-kernel.js`（`QB.query` 取数、`QB.series/lastValue/topValues` 解包清洗），别再每页各抄 `fetch`/解包、各踩"假 0/缺口"的坑。见 [guides/bespoke-page.md](guides/bespoke-page.md)。
> 发布前用 `scripts/verify_page.mjs <html_file> --require-browser` 检查桌面与 390px/320px 移动端，确保无 `QB_SHARED_` / `replace_with_signature` / `pkg_replace` 残留、存在 `<h1>`、无关键横向溢出和核心取数脚本错误。含范式卡 artifact 的页面加 `--card-runtime`（或 `--card-runtime-only`）验收 artifact/manifest/独立 hydrate。若机器没有 Playwright/Chrome/Edge，脚本会明确标记为 `static-only`，不能当完整浏览器验收。

## 配置

`config.json`：填入 `api_key`（从 https://www.quantbuddy.cn/login 获取）。可建 `config.local.json` 覆盖 `endpoint` / `api_key` 等（不入库）。环境变量 `QUANT_BUDDY_API_KEY` 仅在 config.json / config.local.json 都没有 api_key 时兜底，不是常规配置方式。本技能所有脚本的 `main()` 都支持工具调用参数里的 `api_key` 字段临时覆盖（仅当次调用生效，优先级最高，见 `scripts/common.py::configure_trace_context`）；同一优先级还有环境变量 `QBV_API_KEY`，用于"手上是一份现成的 `@file` 参数（比如 `publish_workflow.py @publish-plan.json`，该 plan 文件按设计不含凭证）、不想现改这份文件塞 api_key"的场景——**不要**为了临时换 key 去设 `QUANT_BUDDY_API_KEY`，那个只在 config.json 为空时才生效，config.json 已有默认 key 时设它不会有任何效果。
