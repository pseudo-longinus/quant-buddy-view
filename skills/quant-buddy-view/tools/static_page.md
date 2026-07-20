# static_page — 静态页托管（上传 / 替换 HTML → 公开可分享链接）

## 正文图片命令（0.6.15）

先有目标 `page_id`，再上传图片：

```bash
python scripts/static_page.py image_upload @params.json
python scripts/static_page.py image_list '{"page_id":"page_xxx"}'
```

`image_upload` 参数为 `task_id/page_id/image_file/logical_name`。本地只预检文件存在、扩展名为 PNG/JPEG/WebP 和 5MB 上限；真实 magic bytes、尺寸、转码和配额以服务端为准。成功响应的 `url` 是同页、同域、immutable WebP，必须用该绝对 URL 写入 HTML。

`image_list` 用于确认目标页资产为 active。Agent 不提供删除命令；发布失败遗留的 unused 图片由 growthX 后台两段式安全删除。公共 multipart helper 从 `common.headers()` 继承 `x-task-id/x-skill-version/x-skill-name/x-skill-channel` 后只覆盖 `Content-Type`，缩略图和正文图片的审计上下文一致。

> 把一份自包含 HTML 看板上传到对象存储，返回 `https://pages.quantbuddy.cn/...` 公开链接，任何人凭链接即可在浏览器打开。之后凭 `page_id` 管理（替换内容 / 列表 / 撤销）。
> **替换（`update`）只换内容、不换链接**：页面已经分享出去后想再补充/调整，重建 HTML 后 `update` 同一个 `page_id` 即可，URL 不变、访问者刷新就看到新内容，也不占用新的活跃页配额。
> **首链进度页**：新会话先查官方精选+社区范式卡；direct 命中后下一条用户可见消息立即发现成链接，再用 `direct_deliver` 确定性取数和 finalize。fork/unmatched 用 `new_page`、`update_progress`、`publish_verified` 维护同一首链。
> 通过本地脚本 `scripts/static_page.py` 调用，页面管理命令凭 `config.json` 的 API Key 认身份（归属由 api_key 推定）；每次用户任务先用 `scripts/trace_context.py begin` 建立 `task_id`，后续命令通过参数复用并自动透传 `x-task-id`；`verify_card_runtime` 直连 URL 模式只做公开 HTML 验收。

## 端点

| 操作 | 方法 + 路径 |
|------|-------------|
| 首链进度页 | 脚本包装：`new_page` 调 `uploadStaticPage`，`update_progress` 调 `updateStaticPage` |
| 首链最终发布 | 脚本包装：`publish_final` 先调 `update_progress` 进入 `final_publish`，再调 `updateStaticPage` 写正式活页；失败时回写失败进度页 |
| 分级验收发布 | 脚本包装：`publish_verified` 固定执行 `fork_validate → fork-local 浏览器门禁 → publish_final → public-smoke` |
| 上传 | `POST /skill/uploadStaticPage` |
| 替换 | `POST /skill/updateStaticPage` |
| 下载 | `GET /skill/getStaticPage?page_id=&url=` （返回公开链接 + 元信息，不含字节） |
| 列表 | `GET /skill/listStaticPages?page=&page_size=&scope=` |
| 撤销 | `POST /skill/revokeStaticPage` |
| 缩略图 | `POST /skill/setPageThumbnail` （multipart：`file`=PNG/JPG + `page_id`） |
| 标签列表 | `GET /skill/listPageTags?tag_type=`（`scene` / `paradigm`；不传返回两类） |
| 自动打标 | `POST /skill/autoTagStaticPage`（LLM 识别场景/范式标签并落库；`dry_run` 只读预览、`force` 忽略缓存重打） |
| 发布到社区 | `POST /skill/publishStaticPageToCommunity` |
| 取消社区发布 | `POST /skill/unpublishStaticPageFromCommunity` |
| 模板列表 | `GET /skill/listTemplates?category=&status=&scene_tag_id=&paradigm_tag_id=&recommend_tag_id=&page=&page_size=` |
| 模板详情 | `GET /skill/getTemplate?template_id=`（或 `page_id=`） |
| direct 确定性交付 | 脚本包装：`direct_deliver` 调一次模板详情、下载公开 HTML、每数据源查询一次，再调 `finalizeDirectPage` |
| direct 终态 | `POST /skill/finalizeDirectPage`（API Key；校验 task、模板 revision 与同 task 实时查询证据） |
| 模板改写 | `POST /skill/updateTemplate`（is_test/admin；脚本命令 `update_template` 带并发复查） |

## 调用方式

```bash
# 首次会话先拿活页进度链接（返回 page_id + url + steps）
python scripts/static_page.py new_page '{"title":"贵州茅台估值质量分析","message":"正在确认活页方案"}'

# 阶段推进时只更新同一个 page_id 的进度 HTML；脚本会按 current_step 自动推导步骤状态
python scripts/static_page.py update_progress '{"page_id":"page_xxx","current_step":"formula_validation","message":"正在验证实时数据"}'

# 必须等待用户决定时，把同一首链切为可恢复等待状态
python scripts/static_page.py update_progress '{"task_id":"task_xxx","page_id":"page_xxx","current_step":"formula_validation","page_status":"waiting_input","message":"等待确认市场口径","required_input":{"id":"market_scope","prompt":"请选择本页市场口径","options":[{"value":"a_share","label":"A股"},{"value":"hk","label":"港股"}],"resume_step":"formula_validation"}}'

# 用户回复后复用同一 task_id/page_id，从原步骤恢复
python scripts/static_page.py update_progress '{"task_id":"task_xxx","page_id":"page_xxx","current_step":"formula_validation","page_status":"running","message":"已确认市场口径，继续验证实时数据"}'

# fork 来源准备：下载来源 HTML 并生成 fork_manifest_v1
python scripts/static_page.py fork_prepare '{"task_id":"task_xxx","source_template_id":"page_template_xxx","source_markers":["原标的名","原代码"],"target_asset":"新代码","asset_replacements":{"原标的名":"新标的名","原代码":"新代码"}}'

# fork 首链分级验收并发布：仍是同一个 page_id / URL
python scripts/static_page.py publish_verified '{"task_id":"task_xxx","page_id":"page_xxx","html_file":"output/pages/final.html","title":"贵州茅台估值质量分析","source_template_id":"page_template_xxx","fork_manifest_file":"output/forks/page_template_xxx/page_template_xxx.fork-manifest.json","validation_receipt_files":["receipt.json"]}'

# 上传（推荐用 build_dashboard 产物文件）
python scripts/static_page.py upload '{"html_file":"output/pages/dash.html","title":"沪深300异动看板"}'

# 上传 HTML 成功后顺带设置缩略图（缩略图失败只返回 warning，不回滚 HTML）
python scripts/static_page.py upload '{"html_file":"output/pages/dash.html","title":"沪深300异动看板","thumbnail_file":"output/thumbnails/dash.png"}'

# 也可直接传 HTML 全文（中文走 @file/SP_PARAMS 防 GBK 截断）
SP_PARAMS='{"html":"<!doctype html>...","title":"..."}' python scripts/static_page.py upload

# 替换已发布页面内容（链接不变；page_id 来自上次 upload/list）
python scripts/static_page.py update '{"page_id":"page_xxx","html_file":"output/pages/dash.html"}'

# 替换 HTML 成功后顺带替换缩略图
python scripts/static_page.py update '{"page_id":"page_xxx","html_file":"output/pages/dash.html","thumbnail_file":"output/thumbnails/dash.png"}'

# 下载已发布页面的 HTML 再编辑（落盘到本地）
python scripts/static_page.py download '{"page_id":"page_xxx","save":"output/pages/back.html"}'

# 管理
python scripts/static_page.py list   '{"page":1,"page_size":20}'
python scripts/static_page.py revoke '{"page_id":"page_xxx"}'

# 给页面设置/替换缩略图（纯展示封面，直传 PNG/JPG）
python scripts/static_page.py thumbnail '{"page_id":"page_xxx","image_file":"output/pages/cover.png"}'

# 如需打标签，可查询当前可用标签（场景/范式）
python scripts/static_page.py tags '{}'
python scripts/static_page.py tags '{"tag_type":"scene"}'

# LLM 自动打标（上传后给页面识别场景/范式标签并落库）
python scripts/static_page.py autotag '{"page_id":"page_xxx"}'
python scripts/static_page.py autotag '{"page_id":"page_xxx","dry_run":true}'   # 只读预览，不写库
python scripts/static_page.py autotag '{"html_file":"output/pages/dash.html"}'  # 上传前预打标（自动 dry_run）

# 发布到社区 / 取消社区发布（仅 owner 可操作自己的 active 普通页）
python scripts/static_page.py publish_community '{"page_id":"page_xxx"}'
python scripts/static_page.py unpublish_community '{"page_id":"page_xxx"}'

# 浏览官方精选+社区命中池 / 看某个范式详情
python scripts/static_page.py templates '{"recommend":"all","page":1,"page_size":20}'
python scripts/static_page.py template  '{"template_id":"tpl_xxx"}'

# direct：先把 templates 返回的 URL 发给用户，再只调用一次本命令
python scripts/static_page.py direct_deliver '{"task_id":"task_xxx","page_id":"page_xxx","template_revision":"sha256"}'

# 兼容底层入口：仅在已经单独完成全部实时查询证据时使用
python scripts/static_page.py direct_finalize '{"task_id":"task_xxx","page_id":"page_xxx","template_revision":"sha256"}'

# 已转 published template 的页面：保持原 page_id/public_url 安全改写
python scripts/static_page.py update_template '{"page_id":"page_xxx","html_file":"output/pages/x.html","verify_card_runtime":true,"expected_metadata":{"download_url":"https://..."}}'

# 批量快速验收范式卡 card runtime artifact，不跑整页多视口
python scripts/static_page.py verify_card_runtime '{"page_ids":["page_xxx","page_yyy"],"require_browser":true}'
```

## 首链进度页（new_page / update_progress / publish_final）

`new_page` / `update_progress` / `publish_final` 是脚本侧的轻封装，不需要新增后端接口：`new_page` 上传一份“活页生成中”的 HTML，`update_progress` 用同一个 `page_id` 调 `update` 更新进度内容，`publish_final` 用同一个 `page_id` 完成最终正式活页发布。它适合被承接页面放进 iframe：承接页面定时刷新 iframe URL，进度页本身只负责展示当前进度。

进度页约束：

- 不包含 `setTimeout` / `setInterval` / `location.replace` / `meta refresh` / `postMessage`；
- 默认接入 QuantBuddy 公共页头页尾，并套浅色 share shell theme；如内部调试确实不要页头页尾，可显式传 `ensure_share_shell:false`；
- 首链流程的最终正式活页默认走 `publish_final`，保留普通 `update` 的 share shell 门禁。
- `publish_final` 会先把进度推进到 `final_publish`；若正式 HTML 更新失败，它会把同一个 `page_id` 回写成 `failed` 进度页，避免用户刷新后长期停在上一阶段。
- 复用在线模板时，用同一 `task_id` 调 `fork_prepare` 生成 `fork_manifest_v1` 和任务级 `fork_task_binding_v1`，`publish_final` 仍应同时传 `source_template_id + fork_manifest_file`。若 Agent 漏传，脚本会按 task 自动恢复；若显式值与绑定冲突则 fail-closed。脚本继承来源模板的 `agent_reply_template`，但不会复制来源 `page_context`；manifest 负责校验来源 HTML SHA、来源凭证残留、核心栏目、必需输出与 Card Runtime。
- 个股估值、宏观事件、行业主题、多资产比较、资金量化、基金产品、海外资产会按高置信 metadata 匹配专业骨架；无法匹配的新活页使用 `generic_live_page_delivery_v1`，不再退化成一句发布摘要。
- `reply_template_v2 + hybrid` 必须同时具备当前活页 `page_context` 和 `hybrid_composition`，缺一项正式发布直接失败；旧 v1 hybrid 兼容。
- `update_progress` 优先只传 `current_step + message`，脚本会自动把前序阶段标为 `done`、当前阶段标为 `running`、后序阶段标为 `pending`；不要在每次更新里复制一份可能过期的完整 `steps`。
- 带 `task_id` 推进到 `package_register` 或更后阶段时，必须传 quant-buddy-skill 成功返回的 `validation_receipt_files`；`failed/deferred` 收据不能作为完成证据。无需实时验证的静态页必须传非空 `validation_not_required_reason`。
- 必须由用户决定口径时传 `page_status=waiting_input` 和 `required_input`；当前步骤标为 `waiting`，返回 `agent_reply_hint.interaction_required=true`。用户回复后必须复用原 `task_id/page_id`，以 `page_status=running` 恢复 `resume_step`。
- 进度快照默认显式上传空 `scene_tags/paradigm_tags`，防止临时文案触发自动打标；正式 `publish_final` 不继承该抑制策略。
- `message` 会直接展示给用户，应使用“活页内容 / 准备实时数据 / 检查展示效果”这类产品文案，避免 `HTML`、`公式包`、`本地浏览器验收`、`page_id`、`URL` 等工程词。

参数：

| 字段 | 命令 | 必填 | 说明 |
|---|---|---|---|
| `page_id` | `update_progress` | ✅ | 要覆盖的进度页 ID |
| `title` | `new_page` / `update_progress` | ❌ | 页面标题，默认 `活页生成中` |
| `message` | `new_page` / `update_progress` | ❌ | 当前状态文案 |
| `current_step` | `new_page` / `update_progress` | ❌ | 当前阶段 ID，默认 `plan` |
| `page_status` | `new_page` / `update_progress` | ❌ | `running` / `waiting_input` / `done` / `failed`，默认 `running` |
| `required_input` | `new_page` / `update_progress` | `waiting_input` 时必填 | `{id,prompt,options?,resume_step}`；`options` 为可选 `{value,label}` 数组 |
| `steps` | `new_page` / `update_progress` | ❌ | 步骤数组；每项含 `id`、`title`、`status`、可选 `message`。默认不必传，脚本会按 `current_step` 自动推导状态 |

`publish_final` 接收普通 `update` 的参数，并额外支持：

| 字段 | 必填 | 说明 |
|---|---|---|
| `progress_message` / `final_publish_message` / `publish_message` | ❌ | 进入 `final_publish` 时的用户可见文案，默认 `正在完成活页生成` |
| `failure_message` / `progress_failure_message` | ❌ | 正式发布失败时回写到进度页的用户可见文案，默认 `活页生成遇到问题，请稍后重试。` |
| `source_template_id` | ❌ | 本页复用的在线模板 `template_id/page_id`；继承回复骨架，不复制来源 `page_context` |
| `fork_manifest_file` / `fork_manifest` | `source_template_id` 存在时必填 | `fork_prepare` 生成的 `fork_manifest_v1` 文件或内联对象；发布前 fail-closed 校验来源 HTML、package/grant/signature、栏目、输出和 Card Runtime |
| `require_agent_reply_template` | ❌ | `true` 时启用 fail-closed 门禁；无法解析 Agent 回复模板则不发布正式页 |

默认步骤固定为：

`init` → `plan` → `template` → `formula_validation` → `package_register` → `html_build` → `verify` → `final_publish`。

典型流程：

```bash
python scripts/static_page.py new_page '{"title":"中证500异动监控","message":"正在选择活页方案"}'
python scripts/static_page.py update_progress '{"page_id":"page_xxx","current_step":"template","message":"已选择中证500异动监控活页"}'
python scripts/static_page.py update_progress '{"page_id":"page_xxx","current_step":"verify","message":"活页内容已生成，正在检查展示效果"}'
python scripts/static_page.py fork_prepare '{"task_id":"task_xxx","source_template_id":"page_template_xxx","source_markers":["贵州茅台","SH600519"],"target_asset":"SZ300209"}'
python scripts/static_page.py publish_final '{"page_id":"page_xxx","html_file":"output/pages/final.html","title":"目标标的估值质量分析","source_template_id":"page_template_xxx","fork_manifest_file":"output/forks/page_template_xxx/page_template_xxx.fork-manifest.json","require_agent_reply_template":true}'
```

新 fork 默认改用 `publish_verified`，由脚本一次完成发布前后验收。它在启动浏览器前完成 fork 来源、凭证 tuple、最终公式包输出和分位语义预检。manifest 的 `required_outputs` 必须真实存在于最终 HTML 所绑定公式包的输出 union 中；仅在 HTML 中声明 `QB_REQUIRED_OUTPUTS` 或其他同名字符串不能通过。若同一 `package_id` 对应多个 signature，则以 `credential_ambiguity` 拒绝发布。

成功结果会返回 `agent_reply_contract_file + agent_reply_contract_sha256`、`reply_draft_file`、`reply_validation_params_file` 和 `reply_validation_command`。只把最终 Markdown 写入 draft 并执行返回的命令一次；validator 不接受手工重建的 contract。CLI stdout 只保留阶段摘要，完整结果写入返回的 `full_report_file`。

浏览器 profile：

- `full`：1440 / 390 / 320，结构或 CSS 大改时单独运行。
- `fork-local`：发布前 1440 / 320，检查布局、占位符、控制台和可选 Card Runtime。
- `public-smoke`：发布后单视口检查公网可达、核心内容、控制台和实时 hydrate，不重复完整布局验收。
- `live-only`：direct/certified 页面只检查 Card Runtime hydrate。

发布前失败返回 `published:false` 且不会调用 `publish_final`；发布成功后公网冒烟失败返回 `published:true, verified:false` 并保留最终公开 URL。

包含多个公式包和数据授权时，使用 [publish_workflow.md](publish_workflow.md) 的单命令编排，把 package-set 验证、注册、marker 替换和 `publish_verified` 串联起来，避免 Agent 分步拼接。

## 公共页头页尾门禁

`upload` / `update` 在真正请求服务端前会做一次本地 preflight：

- 检查最终 HTML 是否有公共页头 `<header ... data-qb-share-shell>`；
- 检查最终 HTML 是否有公共页尾 `<footer ... data-qb-share-shell-footer>`；
- 缺公共页头 / 页尾时，直接在 `<body>` 顶部 / 底部插入 `assets/share-shell/`；
- 自动内联 share shell CSS、JS、分享弹层、QR runtime；
- `theme` 参数或 HTML 里已有的 `--qb-shell-*` 变量会被放到公共 CSS 之后，只改颜色不改布局；
- 已内联旧版公共运行时的页面，会在发布前升级到新版截图优先分享海报和复制链接按钮；
- 清理旧正文二维码、旧 `setupShareShell()`、旧 QRCode CDN、旧 `site-footer`；
- 如果仍残留 `QB_SHARED_`、`__QB_LOGO_SRC__`、`shareQrCanvas`、`手机扫码查看`，拒绝上传/替换。

返回 JSON 会带 `share_shell` 字段，说明是否检查以及自动补了哪些内容。默认必须开启；仅内部调试可传 `"ensure_share_shell": false` 跳过。

## 范式卡 artifact 快速门禁

`upload` / `update` / `update_template` 可传 `verify_card_runtime:true`。脚本会把最终 HTML 写入临时文件，执行：

```bash
node scripts/verify_page.mjs <html> --card-runtime-only --require-browser
```

这条路径只验收嵌入的 card artifact，不跑整页多视口，因此适合模板库批量回归。检查项包括：

- `template[data-qb-card-template]`、`style[data-qb-card-style]`、`script[data-qb-card-manifest]`、`script[data-qb-card-runtime]` 齐全；
- runtime 不主动 `fetch` / `XMLHttpRequest` / `EventSource`，不依赖完整页面 DOM；
- manifest 的 `required_outputs` 能通过 `queryFormulaPackage` 返回；
- 独立空白宿主中调用 `QBCardRuntimeV1.mount/hydrate(root, outputs)` 后不空白、不残留长期占位态。

已发布/官方精选页可批量跑：

```bash
python scripts/static_page.py verify_card_runtime '{"page_ids":["page_xxx","page_yyy"],"timeout_sec":180}'
```

返回会包含每张卡的 `artifact_text`、`required_outputs`、`problems`，并把逐项 HTML/JSON 和 `summary.json` 保存到 `output/card-runtime-verify/<timestamp>/`。长任务中途失败时，已完成项仍会留在该目录。

## 自动打标（`autotag`）

上传/更新后，用 LLM 识别页面涉及的**场景标签**（从后台维护的固定场景里选，选不中留空）和**范式标签**（命中已有或按需新增），写入页面。独立旁路命令，**与上传本身互不影响**。

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `page_id` | string | 二选一 | 给已上传页打标（服务端读回该页 HTML） |
| `html` / `html_file` | string | 二选一 | 上传前预打标（自动 `dry_run`，只返回建议、不落库；`html_file` 相对路径基于 skill 根） |
| `dry_run` | bool | ❌ | 只读预览：只返回建议标签、不写库（安全看效果） |
| `force` | bool | ❌ | 忽略内容缓存强制重打（默认内容未变直接返回上次结果） |

- 正式打标返回 `scene_tags` / `paradigm_tags`；`dry_run` 返回 `suggested_scene_tags` / `suggested_paradigms`。
- 均附带 `primitives`（原语证据）、`confidence`、`new_paradigm_candidates`、`reasoning`。
- 场景标签是后台维护的固定集，模型只能选不能新建；范式标签可命中已有或由模型新增。

```bash
python scripts/static_page.py autotag '{"page_id":"page_xxx"}'                  # 正式打标
python scripts/static_page.py autotag '{"page_id":"page_xxx","dry_run":true}'   # 只读预览
python scripts/static_page.py autotag '{"page_id":"page_xxx","force":true}'     # 忽略缓存重打
python scripts/static_page.py autotag '{"html_file":"output/pages/dash.html"}'  # 上传前预打标
```

> 范式库需先由后台一次性初始化（`POST /skill/seedParadigmTags`）；该初始化为一次性运维动作，不在本 skill 暴露。

## 下载 / 取回 HTML 再编辑（`download`）

把一份**已发布**的页面拉回本地再编辑，然后 `update` 同一个 `page_id` 覆盖。
取数链路：脚本先调 `getStaticPage` 鉴权拿到公开 `url`，再**直连 OSS** 下载 HTML
（OSS 对象 public-read）——字节**不经服务端**，因此不占服务端带宽。下载后会本地算一遍
`sha256` 与服务端记录比对（`sha256_match`）。

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `page_id` | string | 二选一 | 要下载的页面（来自上次 upload / list） |
| `url` | string | 二选一 | 页面公开链接（会自动从中解析 page_id） |
| `save` | string | ❌ | 落盘路径（相对则相对 skill 根）；不传则把 `html` 放进返回 JSON |
| `final_response` | boolean | ❌ | 默认 `false`。仅保留给普通自有页面只读兼容；published template direct 禁止使用 |

返回（save 时）：`{ code:0, page_id, owner, title, description, url, agent_reply_template, size, sha256, sha256_match, saved_to }`

默认返回 `agent_reply_hint`（`terminal:false`、`resource_role:existing_page`），即使页面带有 `agent_reply_template` 也不能据此最终收口。普通自有页面显式传 `final_response:true` 时仍可返回兼容只读终态；published template direct 必须走 `direct_deliver`（兼容底层入口为 `direct_finalize`）。

## Agent 回复协议：hint 与 terminal contract

- `templates` / `template`：只返回 `agent_reply_hint`，`resource_role=source_template`。direct 精确命中时，列表 URL 必须在下一次工具调用前先发给用户；fork 的 `download_url` 只是来源输入。
- direct 命中：运行一次 `direct_deliver`，由脚本读取一次模板、按当前 package/grant 各 query 一次并调用一次 `direct_finalize`；成功返回 `agent_reply_contract.terminal=true` 和 `delivery_trace_id`，且不改模板生成 Trace 字段。
- `fork_prepare`：返回来源 HTML 与 `fork_manifest_v1` 文件路径，同时保持 `agent_reply_hint.terminal=false`；它是 fork 输入，不是完成证据。
- `list` / 默认 `download`：只返回 `agent_reply_hint`，`resource_role=existing_page`。
- `new_page` / `update_progress`：始终非终态；即使继承了回复 metadata，也会抑制 `agent_reply_contract`。`waiting_input` 会额外返回 `interaction_required=true`、`required_input`、原 `task_id/page_id/public_url` 和 `resume_step`，只授权一次澄清停顿，不是业务完成证据。
- 成功的 `upload` / `update` / `publish_final` / `update_template` / `direct_deliver` / `direct_finalize`：返回 `agent_reply_contract`，包含 `terminal:true`、`operation`、`page_id`、`public_url` 和 registry 中的 `reply_render_policy`。`direct_deliver` 还附加只含公式 output 名称与脱敏 grant 字段路径的 `reply_data_availability`。
- 只有终态 contract 可以触发最终回复；其中 `required=true` 时才要求读取 Markdown 回复骨架。任何 hint、来源模板 metadata 或 `terminal:false` 都表示必须继续工作。
- `publish_final` 会 fail-closed 校验同一首链 `page_id` / URL、排除来源模板 URL；fork 还要求有效 manifest、禁止任一来源 package/grant 残留，并检查核心栏目、必需输出、Card Runtime 和用户自己的实时凭证。

## 权限 / 权责（is_test 内部互通）

归属由 `api_key`（Bearer）认定。两类对象、两套口径：

**A. 自己的页面**（upload / update / download / list / revoke / **thumbnail** / publish_community / unpublish_community）

- 默认：所有操作**只针对本人页面**。
- `is_test=true` 的用户（内部）可以：
  - `download` / `update` / `thumbnail` **其他 is_test 用户**的页面（按 page_id / url）；
  - `list` 传 `scope=test_all`（或 `all=1`）列出**全部 is_test 用户**的页面（items 带 `owner`）。
- 对**普通（非 is_test）用户**的页面：跨用户访问一律 `FORBIDDEN`。
- `revoke`（撤销）**不开放**跨用户，始终仅本人。
- `publish_community` / `unpublish_community` 是用户主动公开/取消公开动作，也**不开放** is_test 跨用户互通：只能由页面 owner 操作自己的 active 普通页。

**B. 官方精选 / 公共模板**（templates / template）—— 全员可读、写操作受限

- **浏览 / 复制**对**全体登录用户**开放：`templates` 列表 + `template` 详情都凭 api_key 即可读。
  - 发现口径统一为后台推荐标签 `recommend:官方精选`：只要页面带该标签就会进入列表/详情。
  - 不再要求 `is_template=true` 或 `template_status=published`；这些字段只是历史兼容/后台管理字段，返回时用于展示真实状态。
- **写操作本脚本不暴露**，按权责分两类，记住边界即可：
  - 官方精选标签、旧模板元数据、上下线、删除等由后台管理端（growthX）维护；本 skill 不开放任意 `recommend` 标签写入。
  - 把**某个已有用户页面**转成旧公共模板（就地翻 `is_template`，**page_id 与分享链接均不变**）：仍是后台管理端动作，不在 skill 侧。
- 本 skill 对官方精选只做 **「读取 + 复用」**：浏览 → 看详情拿 `download_url` → 直连 OSS 取 HTML →
  改成自己的内容 → 用 `upload` 发布成自己的页面（见下「官方精选：读取 / 复用」）。

```bash
# 仅 is_test：列出全部 test 用户的页面
python scripts/static_page.py list '{"scope":"test_all"}'

# 仅 is_test：下载并覆盖另一位 test 用户的页面
python scripts/static_page.py download '{"page_id":"page_other","save":"output/pages/x.html"}'
python scripts/static_page.py update   '{"page_id":"page_other","html_file":"output/pages/x.html"}'
```

## 缩略图（`thumbnail` → setPageThumbnail）

给一个**已发布**页面设置 / 替换一张**纯展示用的封面图**。缩略图只用于列表 / 详情 / 模板墙的
`<img>` 预览，**不进入页面 HTML、不影响实时取数、不占活跃页配额**。

- 直传图片文件（`image_file` 本地路径，PNG/JPG，≤2MB）；脚本按扩展名定 `Content-Type`，走
  multipart `file` 字段上传。
- 对象固定存 OSS `pages/thumbnails/{page_id}.png`（public-read），库里只回写页面的 `thumbnail_url`。
- 因为按 `page_id` 命名：页面被转成公共模板后 page_id 不变 → 缩略图**天然继续有效**。
- 鉴权同「自己的页面」B 类规则：本人 / 同为 is_test 可设；已转公共模板的页**仅 is_test** 可改。
- 计费：固定 1 RU。

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `page_id` | string | ✅ | 要设缩略图的页面 |
| `image_file` | string | ✅ | 本地图片路径（PNG/JPG，相对则相对 skill 根，≤2MB） |

返回：`{ "code": 0, "page_id": "page_...", "thumbnail_url": "https://pages.quantbuddy.cn/pages/thumbnails/page_....png" }`

错误码：`PAGE_ID_REQUIRED` / `IMAGE_REQUIRED`（没带文件）/ `PAGE_NOT_FOUND` / `FORBIDDEN`（无权改他人页或非 is_test 改模板）/ `IMAGE_TOO_LARGE` / `BAD_IMAGE_TYPE`。

> 这张图什么时候用：页面已经发布、想在后台/模板墙有个像样的封面时再补一张即可，是**可选**的额外信息，不影响页面本身能否打开或取数。

### 给已发布公共模板生成封面

对已经上线的公共模板，不要直接用浏览器打开公开 HTML 后立刻截图：实时取数页面的初始 DOM 往往还停在
“等待取数”。应先用 `render_existing_page_thumbnail.py` 取公式包真实 outputs，并临时替换封面页里的
`QB.query`，让页面离线渲染完成后再截图。

```bash
python scripts/render_existing_page_thumbnail.py "{\"url\":\"https://pages.quantbuddy.cn/pages/page_xxx.html\",\"page_id\":\"page_xxx\",\"out_file\":\"output/thumbnails/page_xxx.png\",\"upload\":true}"
```

返回会包含 `query.status`、`query.outputs_count`、`capture.rasterizer`、`width/height/bytes` 和
`thumbnail_url`。脚本不会在返回里输出 `signature`；如果页面没有公式包凭证或取数失败，会退化为普通等待截图并把原因写进 `query`。

### 随 upload / update 自动设置缩略图

`upload` / `update` 也可以带 `thumbnail_file`（或 `thumbnail_image` / `thumbnail_path`）。脚本会先发布 HTML，
拿到或复用 `page_id` 后再调用同一个 `thumbnail` 上传封面。

- HTML 发布/替换成功是主结果；缩略图上传失败**不回滚 HTML**，返回 JSON 仍保持 `code:0`，并附带
  `thumbnail_warning` / `warnings[]`。
- 成功时会把 `thumbnail_url` 合并回 upload/update 的返回值。
- `thumbnail_file` 仍是 PNG/JPG、≤2MB，相对路径按 skill 根目录解析。

## 官方精选：读取 / 复用（`templates` / `template`）

官方精选 = 后台打了推荐标签 `recommend:官方精选` 的优质页面。接口沿用 `templates` / `template` 的历史命名，但发现口径已经是纯标签：不再要求 `is_template:true` 或 `template_status:published`。
本 skill 侧的用法是「照着现成精选页做一份自己的页」。

**1) 浏览**：`templates` 列出范式卡活页（官方精选，可选并入社区）

```bash
python scripts/static_page.py templates '{"page":1,"page_size":20}'
python scripts/static_page.py templates '{"category":"个股画像"}'
# 也可按标签筛选（id 来自后台标签表 / 详情回显）
python scripts/static_page.py templates '{"scene_tag_id":"tag_xxx"}'
# 范式卡命中池：合并官方精选 + 社区（按 page_id 去重）
python scripts/static_page.py templates '{"recommend":"all"}'
python scripts/static_page.py templates '{"include_community":true}'
# 只看社区
python scripts/static_page.py templates '{"recommend":"社区"}'
```

返回 items 每条含：`template_id`（兼容字段，等同 `page_id`）/ `page_id` / `title` / `description` / `thumbnail_url` / `category` /
`is_template` / `template_status` / `download_url` /
`scene_tags` / `paradigm_tags` / `recommend_tags` 等（具体以服务端为准）。
不传 `recommend`/`include_community` 时仍限定 `recommend:官方精选`；`recommend:"all"` 或 `include_community:true` 合并官方精选 + 社区，
`recommend:"社区"` 只看社区。`scene_tag_id` / `paradigm_tag_id` / `recommend_tag_id` 仍作叠加标签过滤。
> 说明：社区命中池依赖服务端接受 `recommend=社区` 的列表口径；若后台尚未放开，该项会退回官方精选并被去重，不影响官方精选命中。

**2) 看详情 / 拿下载链接**：`template`

```bash
python scripts/static_page.py template '{"template_id":"tpl_xxx"}'
```

返回：`{ code:0, template_id, page_id, title, description, thumbnail_url, category, is_template, template_status,
download_url, is_live, package_ids, packages,
scene_tags, paradigm_tags, recommend_tags }`。其中：

- `download_url` 是模板 HTML 的**公开下载链接**（OSS public-read），直接 GET 即得整页 HTML。
- `is_live` / `package_ids` / `packages` 说明该模板是否实时取数页、关联了哪些公式包（克隆后通常要
  换成你自己注册的公式包 signature 才能取你关心的标的数据）。

**3) direct 命中**：范围一致时先发现成链接 → 一次性查询原页凭证并校验交付证据

```bash
python scripts/static_page.py direct_deliver '{"task_id":"task_xxx","page_id":"page_xxx","template_revision":"sha256"}'
```

命中后不要先单独查询公式包或数据授权；`direct_deliver` 内部负责一次模板详情、每个数据源一次查询和一次 finalize。成功响应还会返回完整 task ID 命名的 `agent_reply_contract_file`、`reply_draft_file`、`reply_validation_params_file` 与 `reply_validation_command`。Agent 根据 contract 的字段可用性和裁剪策略删除结构性空内容，只写入返回的草稿路径并执行校验命令一次；`valid=true` 后临时文件已清理，应立即最终回复，不再运行工具。

**4) fork 成自己的页**：`fork_prepare` → 改资产/文案/凭证 → `publish_final`

```bash
python scripts/static_page.py fork_prepare '{"task_id":"task_xxx","source_template_id":"page_xxx","source_markers":["原标的名","原代码"],"target_asset":"新代码","asset_replacements":{"原标的名":"新标的名","原代码":"新代码"}}'
python scripts/static_page.py publish_final '{"page_id":"page_first","html_file":"output/pages/final.html","source_template_id":"page_xxx","fork_manifest_file":"output/forks/page_xxx/page_xxx.fork-manifest.json"}'
```

> fork 要点：模板里内嵌的是原作者凭证。必须用 quant-buddy-skill 验证目标公式/输出，注册自己的 package/grant 并替换；`publish_final` 会拒绝来源 package/grant/signature 残留、manifest 声明的核心栏目/必需输出缺失或 Card Runtime 丢失。

`fork_prepare` 会写两份 HTML：`*.source.html` 是只读来源基线，用 SHA256 锁定；`*.fork.html` 是工作副本。传入 `task_id` 时，还会在 `output/fork_task_bindings/` 写入按 task 哈希命名的原子绑定文件；`build_dashboard` 读取到 prepared binding 会立即返回 `FORK_TASK_BOUND`，`publish_final` 则自动补齐来源与 manifest。`asset_replacements` 会自动扩展常见交易所代码写法（如 `SH600000`、`600000.SH`），并记录实际替换计数；公式包和数据授权凭证仍必须在验证/注册后由调用方替换。编辑完成后先用 `fork_validate` 复用完整 manifest 门禁，成功后再进入浏览器验收。manifest 默认要求目标页的 package/grant 数量不少于来源页；只有确实把多个来源凭证整合成更少目标凭证时，才可下调 `minimum_target_package_count` / `minimum_target_grant_count`，并必须同时填写非空 `credential_count_reduction_reason` 供审计。确需放弃已绑定范式时，新建 Trace Context 后重新判定路由，不要复用原 task。

### 公共模板：安全改写（`update_template`）

当一个原页面已被转成 published template，普通 `download/update` 可能返回 `PAGE_NOT_FOUND`。此时如果必须保持原模板链接，只能走 `update_template`，不要创建新页面顶替。

`update_template` 的安全流程：

1. 先调用 `template` 读取当前 metadata。
2. 如传入 `expected_metadata`，脚本比较 `download_url/title/description/category/size/sha256/updated_at` 等字段；发现变化就停止。
3. 编译公共 share shell；如传 `verify_card_runtime:true`，先跑 card artifact 快速门禁。
4. 调 `POST /skill/updateTemplate` 写回同一个 `template_id/page_id`。
5. 写后再次 `template` 回查，并把 `preflight_template/postflight_template` 放进返回 JSON。

常用参数：`template_id` 或 `page_id`、`html/html_file`、`title`、`description`、`category`、`verify_card_runtime`、`expected_metadata`。

写回后必须以 `template` / `templates` 回查为准。

## 配置

`static_page.py` 读取 `config.json` / `config.local.json` 里的 `endpoint`，并在该地址后调用上面的 `/skill/...` 静态页托管路径。

## upload 参数

| 字段 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `html` | string | 二选一 | — | HTML 全文 |
| `html_file` | string | 二选一 | — | 本地 HTML 路径（相对则相对 skill 根） |
| `title` | string | ❌ | 取 `<title>` | 页面标题 |
| `description` | string | ❌ | 空 | 页面说明（≤1000 字，列表/详情展示用） |
| `ttl_days` | number | ❌ | 365 | 有效期，到期链接失效、记录与对象清理 |
| `thumbnail_file` | string | ❌ | 无 | HTML 上传成功后再设置封面图；失败只返回 warning，不影响 upload 成功 |
| `scene_tags` | string[] / 逗号串 / 单值 | ❌ | 无 | 场景标签，**只能选已有**；任一项查无即整体报 `SCENE_TAG_NOT_FOUND`。详见下「标签」 |
| `paradigm_tags` | string[] / 逗号串 / 单值 | ❌ | 无 | 范式标签，可选已有、也可现写新名（自动以 `source=user` 进共享池）。详见下「标签」 |
| `user_query` | string | ❌ | 无 | 用户原始问题，用于 LLM 打标或显式标签来源溯源 |
| `tagging_method` | string | ❌ | `manual` | 标签决策方式：`manual` / `llm` / `migration` / `unknown`；不要传 `agent`。LLM 自动识别统一使用 `autotag` |
| `tagging_source` | string | ❌ | `unknown` | 标签来源系统：`quant-buddy-view` / `growthX` / `skill_server` / `script` / `unknown` |
| `tagging_meta` | object | ❌ | 无 | 高级来源审计；可传 `method/source/note`，服务端会写入 `static_pages.tagging_meta` |
| `page_context` | object | ❌ | 自动生成 | 当前活页稳定语义：`version/summary/core_sections/primary_outputs/reply_focus/limitations`；不得含实时值、凭证或本地路径 |
| `agent_reply_template` | object | ❌ | 专业匹配或通用兜底 | v1/v2 回复协议；`template_ref` 指向 `reply-templates/` 下稳定 id |
| `reply_contract_binding` | object | ❌ | 无 | 官方/运营维护标记：`version/profile_ref/revision/managed_by`；普通用户活页通常不传 |
| `verify_card_runtime` | bool | ❌ | false | 发布前只验收 card runtime artifact；失败不上传 |
| `verify_card_runtime_timeout_sec` | number | ❌ | 180 | 单次 artifact 门禁超时时间 |
| `ensure_share_shell` | bool | ❌ | true | 发布前强制检查/自动补公共页头页尾；生产路径不要关闭 |
| `theme` | object | ❌ | 无 | 公共页头/页尾颜色变量，支持 `chrome_bg`、`header_bg`、`footer_bg`、`accent`、`accent_strong`、`line`、`ink`、`muted` |

> **推荐标签（recommend）由后台运营维护，本接口不接受**；传了也会被忽略。

## update 参数

| 字段 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `page_id` | string | ✅ | — | 要替换的页面（来自上次 upload / list） |
| `html` | string | 二选一 | — | 新的 HTML 全文 |
| `html_file` | string | 二选一 | — | 本地 HTML 路径（相对则相对 skill 根） |
| `title` | string | ❌ | 沿用原标题 | 新标题；不传保留原标题 |
| `description` | string | ❌ | 沿用原说明 | 新说明；不传保留原说明，传空串 `""` 则清空 |
| `ttl_days` | number | ❌ | 不变 | 传了才从此刻顺延有效期；不传保持原到期时间 |
| `thumbnail_file` | string | ❌ | 无 | HTML 替换成功后再替换封面图；失败只返回 warning，不影响 update 成功 |
| `scene_tags` | string[] / 逗号串 / 单值 | ❌ | 沿用原标签 | **仅传入时更新**：传值=覆盖、传 `[]`=清空、不传=保留原标签；只能选已有，查无报 `SCENE_TAG_NOT_FOUND` |
| `paradigm_tags` | string[] / 逗号串 / 单值 | ❌ | 沿用原标签 | **仅传入时更新**：传值=覆盖、传 `[]`=清空、不传=保留；可选已有或现写新名自动入池 |
| `user_query` | string | ❌ | 无 | 用户原始问题，用于 LLM 打标或显式标签来源溯源 |
| `tagging_method` | string | ❌ | `manual` | 仅在传入标签时写来源审计；不要传 `agent`，LLM 自动识别统一使用 `autotag` |
| `tagging_source` | string | ❌ | `unknown` | 标签来源系统 |
| `tagging_meta` | object | ❌ | 无 | 高级来源审计；可传 `method/source/note` |
| `page_context` | object | ❌ | 沿用原值 | 仅显式传入时更新；`null`/空对象清空。若最终模板是 v2 hybrid，清空会被拒绝 |
| `agent_reply_template` | object | ❌ | 沿用原值 | Agent 回复格式 metadata；传 `null` / 空对象表示清空（服务端支持时生效） |
| `reply_contract_binding` | object | ❌ | 沿用原值 | 人工维护分组和 revision；传 `null`/空对象清空，省略则保留 |
| `verify_card_runtime` | bool | ❌ | false | 替换前只验收 card runtime artifact；失败不覆盖 |
| `verify_card_runtime_timeout_sec` | number | ❌ | 180 | 单次 artifact 门禁超时时间 |
| `ensure_share_shell` | bool | ❌ | true | 替换前强制检查/自动补公共页头页尾；生产路径不要关闭 |
| `theme` | object | ❌ | 无 | 公共页头/页尾颜色变量，支持 `chrome_bg`、`header_bg`、`footer_bg`、`accent`、`accent_strong`、`line`、`ink`、`muted` |

替换成功后 `url` / `page_id` 与替换前完全一致；仅本人、且未撤销的页面可改（已撤销返回 `NOT_ACTIVE`）。
## 响应（upload）

```json
{ "code": 0, "page_id": "page_...", "url": "https://pages.quantbuddy.cn/pages/<user>/page_....html",
  "title": "...", "description": "...",
  "size": 13429, "uploaded_size": 12880, "served_size": 13429, "tracker_injected": true,
  "sha256": "...",
  "is_live": true,
  "package_ids": ["pkg_fa4d477b4c57c2f584a2dbdf", "pkg_2a200c46cf1eecfaec7596a2"],
  "packages": [{ "package_id": "pkg_fa4d...", "found": true, "status": "active" }],
  "notice": "实时取数页面：已关联 2 个公式任务包，平台数据更新时页面自动刷新。",
  "scene_tags": [{ "tag_id": "tag_...", "name": "盘前", "source": "system" }],
  "paradigm_tags": [{ "tag_id": "tag_...", "name": "量价背离", "source": "user" }],
  "tagging_meta": { "method": "manual", "trigger": "upload", "source": "quant-buddy-view", "tagged_at": "2026-..." },
  "page_context": {
    "version": "page_context_v1",
    "summary": "用于观察单只股票的估值水位与财务质量。",
    "core_sections": ["估值水位", "盈利质量", "现金流质量"],
    "primary_outputs": ["PE/PB 历史分位", "ROE", "经营现金流"],
    "reply_focus": "先判断估值，再判断盈利和现金流是否支撑。",
    "limitations": "不提供目标价或明日涨跌预测。"
  },
  "agent_reply_template": {
    "version": "reply_template_v2",
    "template_ref": "single_stock_valuation_quality_v1",
    "reply_scope": "full_answer",
    "output_format": "markdown"
  },
  "agent_reply_contract": {
    "terminal": true,
    "operation": "upload",
    "page_id": "page_...",
    "required": true,
    "template_ref": "single_stock_valuation_quality_v1",
    "template_file": "<skill_root>/reply-templates/single_stock_valuation_quality_v1.md",
    "template_exists": true,
    "public_url": "https://pages.quantbuddy.cn/pages/<user>/page_....html",
    "final_response_required": "read_template_file_and_reply_in_template_format_plus_links"
  },
  "expires_at": "2027-..." }
```

`url` 即对外分享链接，浏览器直接可开（自定义域名内联渲染，不触发下载）。

> `scene_tags` / `paradigm_tags` 回显解析后的 `{tag_id,name,source}`；范式里现写的新名 `source=user`。`update` 响应同结构。读接口（`getStaticPage` / `list` / `templates` / `template`）也透出 `page_context`、完整 v1/v2 `agent_reply_template` 与后台维护的只读 `recommend_tags`。Agent/skill 侧按 `template_ref` 读取本地回复骨架。
> `agent_reply_contract.terminal=true` 是完成门禁；只有它允许最终收口。若同时 `required=true`，最终答复前必须读取 `agent_reply_template_file`，按模板 Markdown 骨架输出，并包含 `public_url`。`agent_reply_hint` 永远不能作为完成证据。

> 尺寸字段：`uploaded_size` = 你上传的原始 HTML 字节数；`served_size` = 服务端注入访问统计脚本后实际托管的字节数（即 `sha256` 对应的内容）；`tracker_injected=true` 表示已注入统计脚本。`size` 为兼容旧字段，等于 `served_size`。`update` 响应同此结构。

### 页面认知：is_live / 公式包关联（upload / update 自动解析）

服务端在上传/替换时**解析 HTML**，把结果随响应返回（`update` 按新 HTML 重新解析；`list` / `download` 也透出 `is_live`、`package_ids`）：

| 字段 | 说明 |
|---|---|
| `is_live` | 是否实时取数页：页面含 `queryFormulaPackage` 调用 **且** 引用 ≥1 个公式包；否则是静态页 |
| `package_ids` | 从 HTML 抓到的公式任务包 id（关联标记） |
| `packages` | 每个包回查 `formula_packages` 的 `{ package_id, found, status }`（`found=false`=平台查无此包） |
| `notice` | 人话提示：静态页会提示"平台数据更新不会刷新此页面"；实时页有失联包会提示"实时取数可能失败" |

> ⚠️ 拿到 `is_live=false` 时，多半是把数据焊死进了 HTML（没走 `queryFormulaPackage` 实时取数）。若本意是 live 看板，应改回实时取数再 `update`；如确为一次性静态报告，可忽略提示。发布前把 `notice` 转告用户。

## 标签（场景 / 范式 / 推荐）

页面标签维度独立于旧模板/官方精选发现口径。三类标签都多选，落库存 tag_id、读时回查名字。

上传/替换前先查当前可用标签：

```bash
# 同时返回 scene_tags / paradigm_tags
python scripts/static_page.py tags '{}'

# 只查场景或范式
python scripts/static_page.py tags '{"tag_type":"scene"}'
python scripts/static_page.py tags '{"tag_type":"paradigm"}'
```

`tags` 调 `/skill/listPageTags`，不计费；不传 `tag_type` 返回 `{code:0, scene_tags:[...], paradigm_tags:[...]}`，传 `tag_type` 返回 `{code:0, tag_type, list:[...]}`。

| 标签类型 | 入参 | 取值规则 | 来源 |
|---|---|---|---|
| 场景 `scene` | `scene_tags` | **只能选已有**（按 name 或 tag_id 匹配）；任一项查无→整体报 `SCENE_TAG_NOT_FOUND`，不落库 | 后台维护（`source=system`） |
| 范式 `paradigm` | `paradigm_tags` | 可选已有，也可**现写新名**：未命中的名字按 `source=user` 自动建并立刻进共享池，之后别人也能选 | 后台建(`system`) + 用户现写(`user`) |
| 推荐 `recommend` | —（本接口不接受） | 仅后台运营给页面打；读接口里 `recommend_tags` 只读透出 | 后台维护 |

- 三种入参都接受 **数组 / 逗号分隔串 / 单值字符串**，内部统一去空白去重。
- `upload` 不传标签=不打；`update` 不传=保留原标签、传 `[]`=清空、传值=整体覆盖。
- 现写范式标签先**确认名字规范**再发：一旦入池即全员可见，错别字也会留痕。

## 发布到社区（publish_community / unpublish_community）

社区发布是用户把自己的页面提交到社区入口、让全部用户可发现的动作。当前服务端内部实现是给页面追加固定的 `recommend:社区` 标签；这不是开放任意推荐标签写入，`recommend_tags` 的自由维护仍只在后台。

```bash
# 发布到社区：成功后页面进入社区聚合入口
python scripts/static_page.py publish_community '{"page_id":"page_xxx"}'

# 取消社区发布：从社区聚合入口移除
python scripts/static_page.py unpublish_community '{"page_id":"page_xxx"}'
```

入参：

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `page_id` | string | ✅ | 要发布/取消发布的普通静态页 ID |

权限与语义：

- 只能操作**自己的 active 普通页**，不支持 is_test 跨用户代发。
- 公共模板不走这个用户侧接口；模板仍按模板/后台流程管理。
- 发布是幂等的：已发布到社区的页面重复调用仍返回成功，不重复写标签。
- 取消也是幂等的：未发布到社区时取消仍返回成功。
- 返回会包含 `community_status`、`community_tag`、`recommend_tags` 等字段。后续若接入审核，`community_status` 可能从当前的 `published` 调整为 `pending`。

示例响应：

```json
{
  "code": 0,
  "page_id": "page_xxx",
  "community_status": "published",
  "community_tag": { "tag_id": "tag_xxx", "tag_type": "recommend", "name": "社区", "source": "system" },
  "recommend_tags": [{ "tag_id": "tag_xxx", "name": "社区", "source": "system" }]
}
```

## 限制

| 项 | 限制 |
|---|---|
| 单页体积 | ≤ 2 MB（脚本本地先早检一次） |
| 单用户活跃页 | ≤ 200（超限报 `PAGE_LIMIT`，先 revoke 旧页） |
| 内容类型 | 必须以 `<!doctype html>` / `<html>` 开头 |

## 错误码（节选）

| code | 场景 |
|---|---|
| `HTML_REQUIRED` / `EMPTY` / `NOT_HTML` / `TOO_LARGE` | 内容缺失 / 为空 / 非 HTML / 超 2MB |
| `PAGE_LIMIT` | 活跃页达上限 |
| `STORAGE_FAILED` / `DB_FAILED` | 写对象存储 / 落库失败 |
| `PAGE_ID_REQUIRED` | 下载：page_id / url 都没传 |
| `PAGE_NOT_FOUND` / `FORBIDDEN` | 下载/替换/撤销：页面不存在 / 无权（非本人且非 is_test 互通） |
| `NOT_ACTIVE` | 替换/下载：页面已撤销（替换需重新 upload；下载链接已失效） |
| `BAD_TAG_TYPE` | tags：`tag_type` 不是 `scene` / `paradigm` |
| `SCENE_TAG_NOT_FOUND` | upload/update：`scene_tags` 里有未登记的场景标签（场景只能选已有） |
| `TEMPLATE_NOT_ALLOWED` | publish_community/unpublish_community：公共模板不走用户侧社区发布接口 |
| `COMMUNITY_TAG_FAILED` | publish_community/unpublish_community：固定 `社区` 标签读取或创建失败 |

> 若公开 URL 明明可访问，但 `download` / `update` 返回 `PAGE_NOT_FOUND`，先用 `template --page_id <page_id>` 检查是否已转成公共模板。若 `template_status=published`，普通静态页维护路径不再适用；需要保留原模板链接更新时，应走后台/admin `updateTemplate` 路径，不能用新 URL 代替。

## 安全与隔离

- 页面托管在自定义域名 `pages.quantbuddy.cn`，与主站不同源 → 页面内脚本读不到主站 `localStorage` 里的 API Key。
- 看板会把公式包 `signature` 写进公开 HTML 供实时取数（query 本以 signature 作能力令牌、设计上允许嵌入），发布前确认可接受。

## 计费

上传 / 替换 / 设置缩略图各固定 1 RU；下载 / 列表 / 撤销 / 查标签（tags）/ 发布到社区 / 取消社区发布 / 浏览模板（templates、template）不计费
（下载字节直连 OSS，不经服务端）。替换、设缩略图都不占新的活跃页配额。
