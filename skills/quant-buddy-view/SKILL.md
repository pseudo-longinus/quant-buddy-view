---
name: quant-buddy-view
slug: quant-buddy-view
author: guanzhao
version: 0.6.9
description: |
  QBV / quant-buddy-view（用户可能写成 /quant-buddy-view、/qbv、qbv 或 QBV）用于把量化数据做成「公开可分享、实时取数」的网页看板/落地页。
  Use this skill when the user asks to create, update, publish, verify, retrofit, or reuse a Quant Buddy dashboard/static page/template, including shareable pages, public URLs, formula packages, thumbnails, share shell, cover/essence cards, poster/share behavior, single-stock profile pages, valuation/financial profile pages, index-anomaly boards, multi-factor screeners, and commodity daily pages.
  配合 quant-buddy-skill 使用：固定页面请求先用 static_page.py templates/template 选择带 recommend:官方精选 标签的在线精选页；实时取数页必须先在 quant-buddy-skill 验证公式并确认其 api_key 可用，再用本技能注册自有公式包、替换凭证/文案、浏览器验收，并通过 static_page.py upload/update 发布或更新 pages.quantbuddy.cn 链接。默认不从本地历史样板目录或低质 HTML 骨架起步。
  用户显式唤起 /quant-buddy-view、/qbv、qbv 或 QBV，且请求不是纯咨询/代码维护/文档解释时，默认视为可分享活页任务：读完本技能约束后先查官方精选+社区范式卡判定 direct/fork/unmatched；direct 直接交付现成页，fork/unmatched 才 new_page 返回首链并继续推进。
  Do not use this skill for one-off 行情查询、普通股票涨跌幅/估值问答、选股/回测探索；those belong to quant-buddy-skill unless the user explicitly wants a reusable/shareable page.
runtime: python
primaryCredential: quant-buddy API Key
metadata:
  version: 0.6.9
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

0. 在任何后端请求前运行 `scripts/trace_context.py begin`，保存唯一 `task_id` 并在后续命令中复用。
1. 运行一次 `scripts/static_page.py templates`，传 `recommend:"all"`，查询官方精选+社区命中池。
2. direct 命中后先把列表返回的现成 URL 发给用户，再运行一次 `static_page.py direct_deliver` 完成模板详情、单次取数和终态确认。
3. fork/unmatched 才创建 `new_page` 首链；验证目标公式后注册当前用户凭证、替换页面内容、浏览器验收并用 `publish_final` 更新同一链接。
4. 所有分支最终按 `agent_reply_contract` 和回复模板生成草稿，再运行 `validate_agent_reply.py`。

## 何时用本技能 vs quant-buddy-skill

- **探索/一次性查询**（"茅台今天涨跌幅"、"跑个均线金叉回测看看"）→ 用 **quant-buddy-skill**。
- **要一个能反复看、能发给别人、数据会自动更新的页面** → 探索清楚后切到 **quant-buddy-view**。

## 新会话路由：先查范式卡（templates）判命中

先建立 Trace Context，再查询范式卡：

```bash
python scripts/trace_context.py begin '{"user_query":"用户原始问题"}'
```

保存返回的 `task_id`，并把它加入本次任务后续每个 `static_page.py`、`formula_package.py`、`data_grant.py` 参数。脚本会通过 `x-task-id` 请求头透传，使后台能从提问一直聚合到最终活页链接。`upload` / `update` / `publish_final` / `update_template` 缺少 Trace Context 时必须停止发布。若中途使用 quant-buddy-skill 验证公式，其业务调用也显式传同一个 `task_id`，不要让另一个 session id 把链路拆开。

新会话被判定为可分享活页任务时，**第一步只运行一次 `scripts/static_page.py templates`，参数传 `recommend:"all"`**。它会分别读取官方精选与社区并按 `page_id` 去重；这两次后端 `list_templates` 属于一次范式池查询，不要再手工重复调用。

- **① 直接命中**（范式匹配，且标的/股票池/指数/市场范围一致）：
  - `templates` 一旦给出精确命中，**下一条用户可见消息必须立即发送现成 `download_url/public_url`，中间不允许任何工具调用**。推荐文案：`已直接命中现成活页：[标题](URL)。我继续核对实时数据并补充分析。`
  - 发出链接后只运行一次：`python scripts/static_page.py direct_deliver '{"task_id":"task_xxx","page_id":"page_xxx","template_revision":"sha256"}'`。该命令内部固定完成一次模板详情读取、一次 HTML 下载、每个当前 package/grant 一次查询和一次 `direct_finalize`；不要再单独调用 `template`、query 或 `direct_finalize`。
  - 不 `new_page`、不注册、不 fork、不研究脚本源码、不先跑 `--help`。`direct_deliver` 的公式结果固定为 summary；grant 完整结果只写 `%TEMP%`，最终回复不得暴露本地路径或凭证。
  - 只有返回 `agent_reply_contract.terminal=true` 且 `operation=direct_finalize` 才允许最终收口；失败时说明具体错误，不得用已发送的链接绕过终态门禁。回复模板和 `page_context` 沿用原页。
  - 用户之后说"要改这个页面内容" → 转 ② fork（官方/社区链接不能直接改，只能新建自己的链接后改）。
  - 边界：范式匹配但**标的/股票池/指数/市场范围不一致**（如命中的是茅台估值页、用户问的是宁德时代；命中沪深300异动页、用户问中证500）不算直接命中，落到 ②。只有资产无关且市场范围一致的全市场范式，才可不依赖具体标的直接命中。
- **② fork**（范式命中但标的不符，或用户要改内容）：
  - `new_page` 先发首链进度页（此时才需要首链）→ 用同一 `task_id` 调 `fork_prepare` 下载该范式模板 HTML 并生成 `fork_manifest_v1`；脚本会把来源与 manifest 持久绑定到该任务，后续 `publish_final` 即使漏传来源字段也会自动恢复并强制校验。`source_template_id` 只继承回复 metadata，不会自动下载或克隆 HTML。
  - 用 quant-buddy-skill 验证**本标的**公式/输出（硬门槛），批量公式使用 `output_mode:"summary"`；只有工具返回 `validation_receipt_file` 才算完成，`failed` / `deferred` 不得推进 → 注册**自己的**公式包或数据授权 → 换标的/文案/凭证 → 生成活页。
  - 先调用 `fork_validate(task_id, html_file)` 复用发布门禁，再执行 `verify_page.mjs --require-browser`（来源有 Card Runtime 时加 `--card-runtime`）→ `publish_final(source_template_id, fork_manifest_file, require_agent_reply_template)`。
  - 回复 = 回复模板格式 + **自己的新链接**（数值同样用自己的包/grant query 填）。
- **③ 未命中**（无匹配范式）：`new_page` 首链 → `build_dashboard` / bespoke 自建 → 其余同 ②。

> 后续追问：自己的链接 → `update` 同 `page_id`；命中的官方/社区链接要改 → 只能转 ② fork 成自己的链接后再改。

## 默认路由

- **固定页面形态**（个股速览、估值体检、成分股异动榜、多因子选股看板、商品日报等）：先 `templates` 查询官方精选+社区命中池；direct 直接用列表 URL + revision，fork 才读取和改写模板详情。
- **宽宝活卡 / 精华卡 / 封面卡（范式卡 artifact）**：把页面精华做成独立 **card runtime artifact**（`embedded-card-v1`：页面内嵌 `<template data-qb-card-template>` + `data-qb-card-manifest` + `QBCardRuntimeV1` runtime），供官网卡片流 / 缩略图 / 封面在空白宿主中**独立 hydrate**。按 [guides/essence-cover-card.md](guides/essence-cover-card.md) 生成；已发布页可用 `static_page.py retrofit_card_runtime` 补 artifact，用 `verify_card_runtime` / `verify_page.mjs --card-runtime-only` 验收。卡片必须官网浅色系、固定信息骨架、可变核心可视化；不再用旧的 `?cover=1` URL 模式。
- **没有合适在线模板**：再走 `workflows/dashboard-end-to-end.md`，用 `build_dashboard` 生成声明式实时看板。
- **声明式看板也不够**：才走 `guides/bespoke-page.md` 写 bespoke 主体 HTML，并用公共 shell 编译成自包含页面。
- **改造已发布/已生成页面**：优先 `scripts/retrofit_share_shell.py`，再 `static_page.py update` 保持同一个 `page_id` / URL。
- **用户可见首链**：direct 在 `templates` 命中后、下一次工具调用前发现成 URL；fork/unmatched 在 `new_page` 返回后立即发首链。不要等公式验证、长文档读取、记忆搜索或实现研究完成才给链接。进度页后续用 `update_progress` 和 `publish_final` 更新同一 `page_id`。
- **Agent 回复模板**：活页 metadata 可带 `agent_reply_template` 指向本技能 `reply-templates/` 下的回复骨架。`reply-templates/` 是 Agent 最终回复格式，不是活页 HTML 页面模板；不要和在线 `templates` / `template` API 混用。
- 本 skill 不再内置本地页面样板，不能从本地历史样板目录或低质 HTML 骨架起步。

## Agent 回复模板（`agent_reply_template`）

活页用同级 `page_context` 描述用途/模块/输出，用 `agent_reply_template.template_ref` 指向 [reply-templates/](reply-templates/) 的 Markdown 骨架。字段契约、hybrid 规则和发布继承见 [tools/static_page.md](tools/static_page.md)。

- `page_context` 不得包含实时数值、api_key、signature、Bearer token 或本地路径；fork 后必须按最终页面重建，direct 才沿用原页。
- 读取型命令返回 `agent_reply_hint.terminal=false`；`new_page/update_progress` 也不是终态。成功的 `direct_deliver/direct_finalize/upload/update/publish_final/update_template` 才可返回 `agent_reply_contract.terminal=true`。
- fork/unmatched 遇到必须由用户决定的口径时，用同一 `task_id/page_id` 进入 `waiting_input`，用户回答后继续原任务；不要重新建 Trace 或首链。
- fork 必须使用 `fork_prepare` 绑定来源和 manifest，最终 `publish_final` 保持首链 URL、移除来源凭证并保留必需栏目/输出/Card Runtime；详细门禁见 [workflows/new-session-paradigm-routing.md](workflows/new-session-paradigm-routing.md)。
- prepared fork task 禁止 `build_dashboard`；脚本返回 `FORK_TASK_BOUND` 后只能继续编辑绑定的 `working_html_file` 并调用 `fork_validate`。
- 带 `task_id` 的进度从 `package_register` 起必须传同任务的 `validation_receipt_files`，收据必须为 `completed + success=true + failures=[]`；静态页可传明确的 `validation_not_required_reason`。
- 最终回复必须按回复模板输出并包含 contract 的公开 URL；缺字段写 `--` 或“本轮未返回”，不得暴露本地路径、凭证或内部日志。
- 最终回复前运行 `scripts/validate_agent_reply.py`；参数只放 `%TEMP%/qbv_<task_id>_*.json`，成功后传 `cleanup_task_id` 清理。
- 没有 terminal contract 禁止完成任务。唯一例外是成功的 `waiting_input` checkpoint。
- 用户可见进度间隔不超过 60 秒；逐指标声明最新可得日期和实际覆盖范围。未做浏览器验收时，只能声明公开 URL 和实时接口可访问。

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
2. **公式必须先验证再注册（硬门槛）**：提交注册的每一组公式，**必须先在 quant-buddy-skill 里用 `runMultiFormulaBatchStream` 跑一遍并确认出数**（公式语法两边一致，可原样验证），跑成功才允许 `register`。不要凭空发明未验证的表达式，也不要"直接注册、错了再说"——注册时的服务端试读只是兜底，不替代这一步。
3. **验证参数也要换干净**：调用 `runMultiFormulaBatchStream` 时，`user_query` 必须反映当前用户请求和当前资产；若传 `task_id` 必须为本次新任务。复制示例时不能只替换 `formulas`，却留下“贵州茅台 factsheet”等旧 `user_query`，否则后台审计和回放会被污染。
4. **signature 是凭证**：不要打印到面向最终用户的对话里；看板会把它写进公开 HTML 供实时取数，发布前确认可接受。
5. **标签来源不要写 Agent**：显式传 `scene_tags` / `paradigm_tags` 时，`tagging_method` 用 `manual` / `migration` / `unknown`；需要 LLM 自动识别就调用 `scripts/static_page.py autotag`。不要再传 `tagging_method:"agent"`，也不要在 `tagging_meta.method` 里写 `agent`。
6. **失败要说清**：脚本返回 `code != 0` 时，向用户复述「卡在哪一步（命令名）+ 错误摘要」，不要以空白或纯日志结束。

## 工具一览

> 参数约定：所有脚本参数是**一个 JSON 字符串**位置参数（或 `@params.json` / 环境变量），如 `list '{"scope":"test_all"}'`。命令行也兼容 `--scope test_all` / `--key=value` 直觉写法（仅简单参数；公式、spec 等复杂结构仍走 `@file`/环境变量以免 GBK 截断）。

| 脚本 | 命令 | 作用 | 文档 |
|---|---|---|---|
| `scripts/formula_package.py` | `register` / `query` / `list` / `revoke` / `refresh` | 公式任务包：注册取数能力；query 支持 `outputs` 与 `result_mode=full|summary|last_values`，direct 使用 summary | [tools/formula_package.md](tools/formula_package.md) |
| `scripts/data_grant.py` | `register` / `query` / `list` / `revoke` / `refresh` | 数据授权：把一次 fastQuery/stockProfile/selectByComposition 请求钉死成 `grant_id`+`signature`，页面免 key 直取有界数据（取舍见「数据授权 vs 公式包」） | [tools/data_grant.md](tools/data_grant.md) |
| `scripts/build_dashboard.py` | （单命令） | spec → live 实时取数看板 HTML | [tools/build_dashboard.md](tools/build_dashboard.md) |
| `scripts/compile_bespoke_page.py` | （单命令） | **【shell 处理脚本】** bespoke 主体 HTML → 内联公共 share shell / logo / qr-mini / data-kernel 的自包含 HTML | [guides/share-shell.md](guides/share-shell.md) |
| `scripts/retrofit_share_shell.py` | （单命令） | **【shell 处理脚本】** 旧 HTML/已发布页面 → 删除旧二维码/旧页头/旧页尾，套入公共 share shell（`assets/share-shell/`），可原链接 update | [tools/retrofit_share_shell.md](tools/retrofit_share_shell.md) |
| `scripts/static_page.py` | `templates` / `direct_deliver` / `new_page` / `update_progress` / `publish_final` / `upload` / `update` / `download` / `fork_prepare` / `fork_validate` / `update_template` / 其他管理命令 | 范式路由、direct 确定性交付、首链进度、fork 发布前门禁和页面发布管理 | [tools/static_page.md](tools/static_page.md) |
| `scripts/validate_agent_reply.py` | （单命令） | 读取终态 contract 与 Markdown 草稿，校验公开 URL、模板章节顺序、缺失字段占位和敏感信息；可在成功后清理任务临时参数文件 | — |
| `scripts/verify_page.mjs` | （单命令） | 发布前/发布后页面验收：1440px、390px、320px 视口，h1、占位符、横向溢出、控制台核心错误；发布前可加 `--require-browser` 强制浏览器验收；范式卡加 `--card-runtime` 连同整页验收 artifact，或 `--card-runtime-only` 跳过整页视口、只验收 artifact/manifest/required_outputs/独立 hydrate | — |
| `scripts/render_cover.py` | （被 `build_dashboard` 调用） | 封面栅格化与合成兜底：`capture_page_cover` 用系统 Edge/Chrome 无头截"封面模式页"为整页 PNG；合成封面（全幅裸图/品牌海报）走 浏览器 → 纯 Python(cairosvg/svglib) → SVG 三层兜底。跨平台、零强依赖，不影响 HTML 发布 | — |
| `scripts/render_existing_page_thumbnail.py` | （单命令） | 给已发布/官方精选 HTML 补封面：下载或读取 HTML → 解析内嵌公式包凭证 → 先取真实 outputs 并临时替换 `QB.query` → 再用系统 Edge/Chrome 截 1200×675 PNG；可带 `upload:true` 直接设置 `thumbnail_url` | [tools/static_page.md](tools/static_page.md) |
| `assets/data-kernel.js` | （前端内核，非脚本） | 手搓 bespoke 页共用的「取数 + 清洗 + 容错」一份；内联进页面 `<script>` 用 | [guides/bespoke-page.md](guides/bespoke-page.md) |
| `assets/share-shell/` | （公共组件） | 所有落地页共用的页头、页尾、刷新按钮、分享海报弹层、海报 canvas、复制链接与复制/下载行为 | [guides/share-shell.md](guides/share-shell.md) |
| `assets/live-card.css` | （公共组件） | 范式卡 artifact 的浅色卡片样式源；由 `build_dashboard.py` 作为 `data-qb-card-style` 内嵌进 card runtime artifact | [guides/essence-cover-card.md](guides/essence-cover-card.md) |
| `scripts/card_runtime_retrofit.py` | （被 static_page 调用） | 为已发布/官方精选页重建独立 card runtime artifact（`embedded-card-v1`），可原链接写回 | [tools/static_page.md](tools/static_page.md) |
| `guides/essence-cover-card.md` | （开发指南） | 页面精华浓缩为独立 4:3 card runtime artifact（`embedded-card-v1`，空白宿主独立 hydrate），适合作为官网卡片流、缩略图或封面源 | — |

> **三条生产路**：固定页面先复用在线模板；标准看板走 `build_dashboard`（声明式快路）；要自定义版式/SVG 的设计页才写 bespoke 主体 HTML。
> 数据层统一调 `assets/data-kernel.js`（`QB.query` 取数、`QB.series/lastValue/topValues` 解包清洗），别再每页各抄 `fetch`/解包、各踩"假 0/缺口"的坑。见 [guides/bespoke-page.md](guides/bespoke-page.md)。
> 发布前用 `scripts/verify_page.mjs <html_file> --require-browser` 检查桌面与 390px/320px 移动端，确保无 `QB_SHARED_` / `replace_with_signature` / `pkg_replace` 残留、存在 `<h1>`、无关键横向溢出和核心取数脚本错误。含范式卡 artifact 的页面加 `--card-runtime`（或 `--card-runtime-only`）验收 artifact/manifest/独立 hydrate。若机器没有 Playwright/Chrome/Edge，脚本会明确标记为 `static-only`，不能当完整浏览器验收。

## 配置

`config.json`：填入 `api_key`（从 https://www.quantbuddy.cn/login 获取），或设环境变量 `QUANT_BUDDY_API_KEY`。可建 `config.local.json` 覆盖 `endpoint` / `api_key` 等（不入库）。`formula_package.py`、`build_dashboard.py`、`static_page.py` 共用同一个 `endpoint`。
