# Workflow · 新会话：查范式卡 → 命中 / fork / 自建（三分支）

新会话被判定为可分享活页任务后的**第一步分诊**：先查范式卡（`templates` 活页列表）判命中，再决定走哪条路。范式卡 = 后台 `recommend:官方精选` 或 `recommend:社区` 标签的现成活页列表。

> 场景：用户说「宁德时代现在估值贵不贵，帮我做个能发出去的页」/「沪深300今天哪些成分股异动」。

## -1. 建立 Trace Context

在任何模板、公式、数据或发布请求前，先记录用户原始问题：

```bash
python scripts/trace_context.py begin '{"user_query":"用户原始问题"}'
```

保存返回的 `task_id`。本工作流后续每个 `static_page.py`、`formula_package.py`、`data_grant.py` 命令都必须在参数中复用它；调用 quant-buddy-skill 验证公式时，业务请求也显式传该 `task_id`。

## 0. 查范式卡判命中

```bash
# 查官方精选 + 社区的范式卡列表（命中池，官方优先）
python scripts/static_page.py templates '{"task_id":"task_xxx","recommend":"all","page":1,"page_size":20}'
```

按用户请求判断落到哪个分支：

- **范式匹配 + 标的/股票池一致** → ① 直接命中
- **范式匹配但标的不符 / 用户要改内容** → ② fork
- **无匹配范式** → ③ 自建

> 判据边界：单标的范式要求标的一致；固定指数/股票池范式要求指数或股票池一致；资产无关的全市场范式要求市场范围与分析场景一致。范式相同但具体范围不同一律 fork。

## ① 直接命中：返回现成链接（不建页、不注册）

1. `templates` 一旦精确命中，下一条用户可见消息立即返回列表项的 `download_url/public_url`。**命中与这条消息之间禁止任何工具调用**；不 `new_page`、不注册、不 fork。
2. 发出链接后只运行一次 `direct_deliver`；不要单独读取模板详情、解析 HTML、查询数据或调用 finalize：
   ```bash
   python scripts/static_page.py direct_deliver '{"task_id":"task_xxx","page_id":"page_xxx","template_revision":"sha256"}'
   ```
3. `direct_deliver` 内部读取一次模板、下载一次 HTML、按当前 package/grant 各查询一次并调用一次 finalize；公式结果固定为 summary，grant 完整结果只写系统临时目录。失败时不 finalize。
4. 只有 `agent_reply_contract.terminal=true` 且 `operation=direct_finalize` 才允许收口。回复模板和 `page_context` 沿用原页。
5. 按回复模板生成 Markdown 草稿，用 `validate_agent_reply.py` 校验后再回复；参数文件放 `%TEMP%`，成功时用 `cleanup_task_id` 清理。
6. 用户之后说「要改这个页面内容」→ 转 ② fork。

## ② fork：范式命中但要改 → 换标的注册自己的公式包

1. `new_page` 先发首链进度页（此时才需要首链），拿到 `page_id + url` 立刻发给用户/承接方。
2. 用同一 `task_id` 调 `fork_prepare`：下载命中的范式 HTML，生成记录来源 SHA、凭证、核心栏目、必需输出和 Card Runtime 要求的 `fork_manifest_v1`，同时写入 `fork_task_binding_v1`。后续发布不能通过省略来源字段绕过该绑定。
3. 用 quant-buddy-skill 验证**本标的**公式/输出（硬门槛，见 `dashboard-end-to-end.md` 第 0 步）。
4. 注册**自己的**公式包或数据授权 → 换标的/文案/凭证 → 生成活页。
5. `verify_page.mjs <html_or_url> --require-browser` 浏览器验收（来源带 Card Runtime 时加 `--card-runtime`；`static-only` 不算通过）。
6. quant-buddy-skill 验证成功后保存 `validation_receipt_file`；用它更新 `package_register` 及以后进度。`failed/deferred` 没有完成收据，禁止推进。
7. 编辑完成后先 `fork_validate(task_id, html_file)`，再做浏览器验收。
8. `publish_final`：仍应显式传 `source_template_id`（命中的 `template_id/page_id`）和 `fork_manifest_file`；个股估值/财务质量类再传 `require_agent_reply_template:true`。即使 Agent 漏传，脚本也会按 `task_id` 自动恢复绑定并执行门禁；显式来源与绑定冲突时直接拒绝。门禁会拒绝来源 package/grant/signature 残留、核心栏目/必需输出缺失、Card Runtime 丢失或无理由的凭证数量缩水；确需整合时在 `fork_prepare` 显式填写 `credential_count_reduction_reason`。
7. 回复 = 回复模板格式 + **自己的新链接**（数值用自己的包/grant query 填）。

## ③ 未命中：自建

无匹配范式时走 [dashboard-end-to-end.md](dashboard-end-to-end.md)：`new_page` 首链 → `build_dashboard` / bespoke 自建 → 验证 → 注册 → 生成 → verify → `publish_final`。其余收口同 ②。

## 后续追问

- 自己的链接 → `update` 同 `page_id`（内容变、URL 不变）。
- 命中的官方/社区链接要改 → 只能转 ② fork 成自己的链接后再改。

## 必要消歧：首链等待并同页恢复

fork/unmatched 创建首链后，如果资产库证明存在 A/H、同名代码或其他不能安全默认的口径：

1. 先用原 `task_id/page_id` 调 `update_progress`，传 `page_status:"waiting_input"` 与 `required_input:{id,prompt,options?,resume_step}`。
2. 只有响应含 `agent_reply_hint.interaction_required:true` 才允许在对话中询问用户；此轮不得声称页面完成。
3. 用户回复后禁止重新建 Trace 或首链；用相同 `task_id/page_id` 调 `update_progress(page_status:"running", current_step:<resume_step>)`，随后继续原分支。
4. 最终仍必须 `publish_final` 并取得 `agent_reply_contract.terminal:true`。

## 运行质量门禁

- 没有 terminal contract 禁止完成业务任务；唯一可暂停例外是成功的 `waiting_input` checkpoint，且用户回复后必须同任务续跑。
- 每个 package/grant 最多查询一次，仅明确瞬时网络失败允许重试一次。
- direct 命中后禁止研究脚本实现、运行子命令 `--help` 或重复调用 `template/query/finalize`；使用 `direct_deliver` 的紧凑结果继续生成回复。
- 用户可见进度间隔不超过 60 秒。
- 未跑浏览器验收时，只能声明公开 URL 和实时接口可访问。
