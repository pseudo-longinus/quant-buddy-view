# Workflow · 新会话：查范式卡 → 命中 / fork / 自建（三分支）

新会话被判定为可分享活页任务后的**第一步分诊**：先查范式卡（`templates` 活页列表）判命中，再决定走哪条路。范式卡 = 后台 `recommend:官方精选` 或 `recommend:社区` 标签的现成活页列表。若 `config.json._channel=feishu-group`，所有非终态 hint 都按 `delivery_policy.emit_intermediate_url=false` 处理：内部流程照常创建/维护页面，但用户只在终态收到 playground 链接。

> 场景：用户说「宁德时代现在估值贵不贵，帮我做个能发出去的页」/「沪深300今天哪些成分股异动」。

## -1. 建立 Trace Context

在任何模板、公式、数据或发布请求前，先记录用户原始问题：

```bash
python scripts/trace_context.py begin '{"user_query":"用户原始问题"}'
```

保存返回的 `task_id`。本工作流后续每个 `static_page.py`、`formula_package.py`、`data_grant.py` 命令都必须在参数中复用它；调用 quant-buddy-skill 验证公式时，使用 `qbs_bridge.py` 并显式传该 `task_id + user_query`，由 task-scoped session 防止并发拆链。

## 0. 查范式卡判命中

```bash
# 查官方精选 + 社区的范式卡列表（命中池，官方优先）
python scripts/static_page.py templates '{"task_id":"task_xxx","recommend":"all","page":1,"page_size":20}'
```

调用返回后，先做一次一致性核对，再进入分支判断：

- `item_count == len(items_summary)` 且存在 `full_result_file`/`full_result_sha256`（说明完整候选已成功落盘）——满足才能继续往下判断 ①/②/③；
- 任一条件不满足，或返回 `error` 为 `TEMPLATES_PERSIST_FAILED` / `TEMPLATES_RESPONSE_SHAPE_UNEXPECTED`，必须停下来告诉用户「范式候选核对失败，暂无法确认是否命中」，**禁止**据此判定为③未命中直接自建，也**不允许**重复调用 `templates` 来重试（每个任务只能调用一次）。

按用户请求判断落到哪个分支：

- **范式匹配 + 标的/股票池一致** → ① 直接命中
- **范式匹配但标的不符 / 用户要改内容** → ② fork
- **无匹配范式** → ③ 自建

> 判据边界：单标的范式要求标的一致；固定指数/股票池范式要求指数或股票池一致；资产无关的全市场范式要求市场范围与分析场景一致。范式相同但具体范围不同一律 fork。

## ① 直接命中：返回现成链接（不建页、不注册）

1. `templates` 一旦精确命中：普通渠道的下一条用户可见消息立即返回列表项的 `download_url/public_url`，且**命中与这条消息之间禁止任何工具调用**；`feishu-group` 禁止发送该链接，直接进入下一步。不 `new_page`、不注册、不 fork。
2. 普通渠道发出链接后、`feishu-group` 不发链接而是立即运行一次 `direct_deliver`；不要单独读取模板详情、解析 HTML、查询数据或调用 finalize：
   ```bash
   python scripts/static_page.py direct_deliver '{"task_id":"task_xxx","page_id":"page_xxx","template_revision":"sha256"}'
   ```
3. `direct_deliver` 内部读取一次模板、下载一次 HTML、按当前 package/grant 各查询一次并调用一次 finalize；公式结果固定为 summary，grant 完整结果只写系统临时目录。失败时不 finalize。
4. 只有 `agent_reply_contract.terminal=true` 且 `operation=direct_finalize` 才允许收口。回复模板和 `page_context` 沿用原页。
5. `direct_deliver` 返回 `agent_reply_contract_file`、`reply_draft_file`、`reply_validation_params_file` 和 `reply_validation_command`。按 contract 的 `reply_render_policy` 与 `reply_data_availability` 删除结构性不存在的字段、整列、整行和空可选章节，再把 Markdown 草稿写入返回的 draft 路径，只执行返回的校验命令一次；成功会清理本任务 contract、draft、params 和 grant 临时结果。
6. 用户之后说「要改这个页面内容」→ 转 ② fork。

## ② fork：范式命中但要改 → 换标的注册自己的公式包

1. 运行 `new_page` 创建进度页并取得 `page_id + url`。普通渠道立刻把首链发给用户/承接方；`feishu-group` 只内部保留 `page_id/url`，不得向用户发送。
2. 用同一 `task_id` 调 `fork_prepare`：下载命中的范式 HTML，生成记录来源 SHA、凭证、核心栏目、必需输出和 Card Runtime 要求的 `fork_manifest_v1`，同时写入 `fork_task_binding_v1`。后续发布不能通过省略来源字段绕过该绑定。
3. **先继承通道，再改通道内参数**：来源模板某个角色是公式包，fork 后同一角色仍是公式包；来源是 `fast_query` / `stock_profile` / `composition_select` grant，fork 后仍使用同 kind、同 query_type、同响应形状的 grant。fork 不是重新评估“财务走公式还是 report grant”的时机，禁止 package↔grant 擅自迁移。只有 unmatched/从零重建才重新选通道，白名单报告期财务此时优先 `fast_query(report)`。改公式前再读 `source_runtime_contract`，不要凭 `required_outputs` 的变量名反推：`fork_prepare` 会把来源 package 的 `formulas` 原文整理进 `manifest.source_runtime_contract.packages[]`（公式不是隐私内容，`getStaticPage`/`getTemplate` 都会带回）。对着每个产出名对应的原公式，把资产名/代码替换成目标资产改写，语法和函数调用照抄原文，不要自己猜。若返回的 `cross_asset_formula_refs` 非空，说明有公式引用了非主资产标的（同业对比、行业分组一类，如公式里出现的其他公司名/代码）——这类公式**不能**用字符串替换直接套到目标资产上，要先判断目标资产自己的同业/行业范围（拿不准就用 `search_similar_cases` 或直接问用户），再按对应产出名重写。
4. 按最终 package 边界调用一次 `python scripts/qbs_bridge.py validate_package_set @params.json` 验证**本标的**公式/输出；每包 1..20 条、顺序执行，bridge 自动处理 deferred/resume 并汇总 `validation_receipt_files`。`failed` 或没有完成收据时禁止推进。
5. 历史分位必须使用真实排序水位：`pe_pctile=排序水位("pe_ttm",250)`、`pb_pctile=排序水位("pb",250)`；禁止把 pctile 输出直接别名到原始 PE/PB。
6. 注册**自己的**公式包或数据授权 → 换标的/文案/凭证 → 生成活页。manifest 的 `required_outputs` 会查询最终页面真实公式包，并在输出 union 上检查；HTML 中未使用的同名字符串数组无效。
7. 准备 `publish_verified` 参数；它会自动选择 `fork-local` 发布前门禁和 `public-smoke` 发布后冒烟。
8. 调用一次 `publish_verified`，显式传 `source_template_id`、`fork_manifest_file` 和 `validation_receipt_files`。脚本会执行 fork 门禁、分级浏览器检查、同链接发布和公网冒烟；来源绑定冲突时直接拒绝。**manifest 里 source package+grant 总数 ≥1 时，直接手工调用 `publish_verified` 会被拒绝**（`error:"PUBLISH_WORKFLOW_REQUIRED"`），必须走第 9 步；只有零凭证的纯静态改造才能直接调这一步。
9. 只要 package/grant 总数 ≥1 就**必须**改用一次 `python scripts/publish_workflow.py @params.json`。它先以假凭证执行 Card Runtime structure-only 预检，再按 marker 串联第 4、6、8 步（验证/注册/凭证替换/发布一次完成），详见 [publish_workflow.md](../tools/publish_workflow.md)。正文与 Card Runtime 共用同一凭证时，把同一注册项的 marker 字段写成数组，由一次注册扇出到多个全局唯一 marker；禁止空置 Card manifest，也禁止为等价公式/读取合同重复注册 package/grant。不要为了"只有一两个凭证"就自己写替换脚本。
10. 发布器返回 SHA256 绑定的完整 contract、draft 路径和唯一校验命令；禁止手工重建精简 contract。校验成功后，回复 = 回复模板格式 + contract 的 `public_url`（数值用自己的包/grant query 填）；`feishu-group` 只允许发送该 playground 链接。

## ③ 未命中：自建

无匹配范式时走 [dashboard-end-to-end.md](dashboard-end-to-end.md)：`new_page` 创建进度页 → `build_dashboard` / bespoke 自建 → 验证 → 注册 → 生成 → verify → `publish_final`。普通渠道发送首链，`feishu-group` 不发送；其余收口同 ②。

## 后续追问

- 自己的链接 → `update` 同 `page_id`（内容变、URL 不变）。
- 命中的官方/社区链接要改 → 只能转 ② fork 成自己的链接后再改。

## 必要消歧：首链等待并同页恢复

fork/unmatched 创建首链后，如果资产库证明存在 A/H、同名代码或其他不能安全默认的口径：

1. 先用原 `task_id/page_id` 调 `update_progress`，传 `page_status:"waiting_input"` 与 `required_input:{id,prompt,options?,resume_step}`。
2. 只有响应含 `agent_reply_hint.interaction_required:true` 才允许在对话中询问用户；此轮不得声称页面完成。`feishu-group` 只提出问题，不附带进度链接。
3. 用户回复后禁止重新建 Trace 或首链；用相同 `task_id/page_id` 调 `update_progress(page_status:"running", current_step:<resume_step>)`，随后继续原分支。
4. 最终仍必须 `publish_final` 并取得 `agent_reply_contract.terminal:true`。

## 运行质量门禁

- 没有 terminal contract 禁止完成业务任务；唯一可暂停例外是成功的 `waiting_input` checkpoint，且用户回复后必须同任务续跑。
- 每个 package/grant 最多查询一次，仅明确瞬时网络失败允许重试一次。
- direct 命中后禁止研究脚本实现、运行子命令 `--help` 或重复调用 `template/query/finalize`；使用 `direct_deliver` 的紧凑结果继续生成回复。
- validator 返回 `valid=true` 后立即最终回复；禁止再次校验、运行 `--help`、扫描临时目录或继续 memory 搜索。
- 性能门槛：普通渠道模板命中到首链 ≤5 秒；所有渠道 terminal 到最终回复 ≤45 秒、端到端 ≤120 秒、用户可见消息间隔 ≤60 秒。
- 未跑浏览器验收时，只能声明公开 URL 和实时接口可访问。
