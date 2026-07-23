# publish_workflow — 验证、注册、凭证替换与发布的一次性编排

## `images[]` 正文图片绑定

图片与 package/grant marker 一起在任何网络写入前预检：文件必须存在、扩展名合法、≤5MB；所有单独 marker 字符串都必须全局唯一，并在 HTML 中恰好出现一次。

```json
{
  "images": [{
    "name": "business-model",
    "image_file": "output/images/business-model.png",
    "logical_name": "business-model",
    "marker": "__QB_IMAGE_BUSINESS_MODEL__"
  }]
}
```

顺序固定为 marker/图片静态预检 → 用假凭证执行 Card Runtime 结构预检 → package-set 验证 → package/grant 注册并向全部 marker 扇出替换 → 图片上传到 `publish_verified.page_id` 并替换 marker → 写 prepared HTML → 单次 `publish_verified`。图片上传或发布失败不会自动删除资产；重试依赖确定性 `asset_id` 复用，未引用资产在后台显示为 unused。

`scripts/publish_workflow.py` 用于 fork/unmatched 的多公式包页面。它按固定顺序执行：

> 硬门槛：fork manifest 里 source package+grant 总数 ≥1 时（即只要 fork 涉及任何一个凭证），`static_page.py publish_verified` 都会拒绝未经本脚本的手工分步调用（返回 `error:"PUBLISH_WORKFLOW_REQUIRED"`）。只有零凭证的纯静态改造允许直接调 `publish_verified`。看到这个错误码，说明该走本脚本而不是自己写脚本拼 marker 替换/多次发布——凭证数少也不例外，仓库里没有第二个专门做这件事的工具。

1. 在任何网络写入前检查模板文件、图片和全部 marker。`markers.package_id`、`markers.grant_id`、`markers.signature` 均可为单个字符串或非空字符串数组；数组中的每个 marker 仍必须非空、全局互不重复，并且在 HTML 中恰好出现一次。
2. 若 HTML 含 Card Runtime artifact，先把 marker 替换为确定性的假凭证、图片 marker 替换为 data URL，再运行 `verify_page.mjs --card-runtime-structure-only`。这一步只解析静态结构，不查询公式包、不 hydrate、不启动浏览器。
3. 用同一 `task_id` 调 `qbs_bridge.py validate_package_set`，按 package 顺序验证，每包 1..20 条公式，自动完成 deferred/resume 并汇总收据。每包 validation/registration 共用同一个 `begin_date`；可在 package 内任一侧或工作流顶层提供，缺省固定为 `20150101`，harness 会同时写入验证和注册参数。
4. 顺序注册公式包和数据授权；每个注册项只注册一次，取得真实 ID/signature 后替换到该字段声明的全部 marker。
5. 把结果写到新的 `prepared_html_file`，不覆盖来源模板。
6. 只调用一次 `publish_verified`；任一步失败立即短路。

## 调用

参数建议保存为 UTF-8 JSON，避免 PowerShell 转义和中文编码问题：

```powershell
python scripts/publish_workflow.py '@D:\temp\qbv-publish-workflow.json'
```

示例参数：

```json
{
  "task_id": "task_xxx",
  "user_query": "生成昭衍新药估值活页",
  "begin_date": 20150101,
  "html_template_file": "output/forks/page_source/working.html",
  "prepared_html_file": "output/pages/final.html",
  "packages": [
    {
      "name": "valuation",
      "validation": {
        "formulas": [
          "pe_ttm=\"A股市盈率（PE, TTM）〔估值数据〕\"*取出(昭衍新药)",
          "pe_pctile=排序水位(\"pe_ttm\",250)"
        ]
      },
      "registration": {
        "formulas": [
          "pe_ttm=\"A股市盈率（PE, TTM）〔估值数据〕\"*取出(昭衍新药)",
          "pe_pctile=排序水位(\"pe_ttm\",250)"
        ],
        "reads": [
          {"output": "pe_ttm", "read_mode": "last_day_stats"},
          {"output": "pe_pctile", "read_mode": "last_day_stats"}
        ]
      },
      "markers": {
        "package_id": [
          "__PKG_VALUATION_PAGE_ID__",
          "__PKG_VALUATION_CARD_ID__"
        ],
        "signature": [
          "__PKG_VALUATION_PAGE_SIGNATURE__",
          "__PKG_VALUATION_CARD_SIGNATURE__"
        ]
      }
    }
  ],
  "grants": [],
  "publish_verified": {
    "page_id": "page_xxx",
    "title": "昭衍新药估值活页",
    "source_template_id": "page_source",
    "fork_manifest_file": "output/forks/page_source/page_source.fork-manifest.json"
  }
}
```

## 输出与失败契约

- stdout 只包含 package/grant 数量、收据、prepared HTML 和精简后的发布阶段结果；完整 `publish_verified` 结果写入其返回的 `full_report_file`。
- 返回值只列出注册后的 package/grant ID，不回显 signature。
- 页面正文与 Card Runtime 共用同一凭证时，使用同一注册项中的 marker 数组；不要把 Card manifest 凭证留空，也不要为同一公式/读取合同额外注册重复 package。
- Card Runtime 结构预检失败返回 `error:"CARD_RUNTIME_PREFLIGHT_FAILED"`。该错误发生在 Trace Context 设置、QBS 验证、package/grant 注册、图片上传与发布之前，因此保证没有网络写副作用。
- marker、QBS 验证、注册或发布前门禁失败时，不继续后续步骤。
- validation 与 registration 的 `begin_date` 不一致时在任何网络调用前失败；不要靠 Agent 在报空值后手工补日期。
- 发布成功但公网 `public-smoke` 失败时，沿用 `publish_verified` 契约：`published:true, verified:false`，并保留公开 URL。
- 最终回复必须使用发布器返回的 `reply_validation_command`；contract 文件的 SHA256 不匹配时 validator 会拒绝。
