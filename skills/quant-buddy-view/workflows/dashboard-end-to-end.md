# Workflow · 需求 → 看板分享链接（端到端）

把 quant-buddy-skill 里探索好的指标，做成一个公开可分享、数据自动更新的网页看板。

> 场景：用户说「帮我做个沪深300指数最近一年走势 + 最新涨跌幅的监控页，要能发给同事」。

## 0. 前置：在 quant-buddy-skill 里探索（本技能之外）

先在 **quant-buddy-skill** 里把公式验证跑通（确认资产、口径、公式能出数），记下验证过的公式表达式。

> 本技能不维护会话 / task_id：register 与发布都凭 `config.json` 的 api_key 认身份，直接开干。
> 调用 `runMultiFormulaBatchStream` 做验证时，`user_query` 要写当前用户的真实请求和当前资产；复制旧示例时不要留下旧股票名、旧测试说明或旧 `task_id`。

## 1. 注册公式任务包

`params.json`（UTF-8，中文务必走 @file）：

```json
{
  "formulas": [
    "hs300_close = \"全市场每日收盘价\"*取出(沪深300)",
    "hs300_chg   = \"全市场每日回报率\"*取出(沪深300)"
  ],
  "reads": [
    { "output": "hs300_close", "read_mode": "range_data",
      "mode_params": { "lookback_days": 365 } },
    { "output": "hs300_chg", "read_mode": "last_day_stats" }
  ],
  "ttl_days": 365
}
```

```bash
python scripts/formula_package.py register @params.json
```

成功返回 `package_id` + `signature`，并落盘到 `output/formula_packages/<package_id>.json`（后续步骤可自动补全 signature）。

## 2. 生成看板 HTML

`spec.json`：

```json
{
  "title": "沪深300监控",
  "subtitle": "近一年走势 · 最新涨跌幅",
  "package_id": "pkg_xxx",
  "panels": [
    { "title": "近一年收盘价", "output": "hs300_close", "type": "line" },
    { "title": "最新涨跌幅",   "output": "hs300_chg",   "type": "number", "unit": "%" }
  ]
}
```

```bash
# 仅生成
python scripts/build_dashboard.py @spec.json
# 或生成 + 直接发布（用户要可分享页面时优先这样做）
python scripts/build_dashboard.py @<(jq '. + {upload:true}' spec.json)   # bash
```

> Windows 下把 `"upload": true` 直接写进 spec.json 即可，无需 jq。

## 3. 发布（若第 2 步未带 upload）

```bash
python scripts/static_page.py upload '{"html_file":"output/pages/沪深300监控-xxxx.html","title":"沪深300监控"}'
```

返回 `url` 即对外分享链接：`https://pages.quantbuddy.cn/pages/<user>/page_xxx.html`。

## 4. 后续维护

- **页面已分享、想改内容但保留原链接**（最常见）：重跑第 2 步生成新 HTML，再用 `update` 替换同一个 `page_id`——URL 不变，访问者刷新即见新内容，也不占新的活跃页配额：
  ```bash
  python scripts/static_page.py update '{"page_id":"page_xxx","html_file":"output/pages/沪深300监控-xxxx.html"}'
  ```
  重建并替换也可一步完成：在 spec.json 里加 `"update_page_id": "page_xxx"`（优先于新上传），跑 `build_dashboard.py @spec.json` 即重建 + 替换。
- **数据更新了想刷新页面**：无需重建——页面是 live 实时取数，访问者打开即见最新；只有改版式/文案时才重跑第 2 步并按上一条 `update` 覆盖同一页面。
- **下线页面**：`python scripts/static_page.py revoke '{"page_id":"page_xxx"}'`。
- **轮换公式包签名**：`python scripts/formula_package.py refresh '{"package_id":"pkg_xxx","rotate_signature":true}'`，再用新签名重建页面（页面内嵌的旧签名才会更新）。

> 页面是实时取数的（HTML 内嵌 `package_id + signature`，打开时调 `queryFormulaPackage` 取最新数据）。前置：端点对页面域名放开 CORS、协议与页面一致、且接受 signature 公开在 HTML 里——当前 `https://test.quantbuddy.cn/skill` 均满足。
