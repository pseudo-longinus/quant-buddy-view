# publish_workflow — 验证、注册、凭证替换与发布的一次性编排

`scripts/publish_workflow.py` 用于 fork/unmatched 的多公式包页面。它按固定顺序执行：

1. 在任何网络写入前检查模板文件和全部 marker；每个 marker 必须非空、互不重复，并且在 HTML 中恰好出现一次。
2. 用同一 `task_id` 调 `qbs_bridge.py validate_package_set`，按 package 顺序验证，每包 1..20 条公式，自动完成 deferred/resume 并汇总收据。
3. 顺序注册公式包和数据授权，取得真实 ID/signature 后替换 marker。
4. 把结果写到新的 `prepared_html_file`，不覆盖来源模板。
5. 只调用一次 `publish_verified`；任一步失败立即短路。

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
        "package_id": "__PKG_VALUATION_ID__",
        "signature": "__PKG_VALUATION_SIGNATURE__"
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
- marker、QBS 验证、注册或发布前门禁失败时，不继续后续步骤。
- 发布成功但公网 `public-smoke` 失败时，沿用 `publish_verified` 契约：`published:true, verified:false`，并保留公开 URL。
- 最终回复必须使用发布器返回的 `reply_validation_command`；contract 文件的 SHA256 不匹配时 validator 会拒绝。
