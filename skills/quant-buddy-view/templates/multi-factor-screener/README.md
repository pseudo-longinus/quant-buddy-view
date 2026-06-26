# Template · 多因子选股看板

> 场景：用户要「主题股票池 + 多因子评分 + TopN 榜单 + 回测/rankIC + K 线 + 公式审计」的可分享页面。
> 这是 bespoke 页面模板，适合 `build_dashboard` 普通 panel 装不下的高密度选股工作台。

## 固定公式包角色

| role | 用途 | 加载策略 |
|---|---|---|
| `RANK` | 股票池、综合分、因子分解、TopN 榜单 | 首屏优先加载，成功后立即渲染榜单 |
| `BACKTEST` | 策略净值、等权基准、指数基准、rankIC/分组表现 | 第二阶段加载，可局部失败 |
| `KLINE_*` | TopN 或当前选中股票的 K 线/价格序列 | 第二阶段加载，可按需延迟 |

`RANK` 包必须先在 `quant-buddy-skill` 真实跑通，再用 `scripts/formula_package.py register` 注册。`BACKTEST` 和 `KLINE_*` 可以拆成独立包，避免首屏被长任务拖住。

## 页面要求

- 页面必须保留 `<h1>`，标签页标题用 `<h2>`。
- 桌面端使用高密度表格；390px/320px 移动端使用卡片布局。
- 所有页面都要先用 `scripts/compile_bespoke_page.py` 内联公共 share shell、`qr-mini.js` 和 `assets/data-kernel.js`。
- 不要把 `signature` 打印到最终聊天回复；它只存在于页面 HTML 内作为只读取数凭证。

## output 契约建议

| role | output | read_mode | 模板读取 |
|---|---|---|---|
| `RANK` | `RANK_TOP` | `last_day_stats` | `QB.topValues(rank,'RANK_TOP')` |
| `RANK` | `FACTOR_SCORE` | `last_valid_per_asset` | `QB.perAsset(rank,'FACTOR_SCORE')` |
| `BACKTEST` | `NAV` | `range_data` | `QB.series(backtest,'NAV')` |
| `BACKTEST` | `BENCH_NAV` | `range_data` | `QB.series(backtest,'BENCH_NAV')` |
| `BACKTEST` | `RANK_IC` | `range_data` | `QB.series(backtest,'RANK_IC')` |
| `KLINE_*` | `PX` | `range_data` | `QB.series(kline,'PX',{dropZero:true})` |

## 生成流程

1. 在 `quant-buddy-skill` 验证公式真实出数。
2. 在 `quant-buddy-view` 分角色注册公式包，`RANK` 优先保证轻量。
3. 复制 [page.template.html](page.template.html)，用 `compile_bespoke_page.py` 替换 endpoint、package_id、signature、标题和主题名。
4. 本地验收 1440px、390px、320px 后，用 `static_page.py upload/update` 发布。

## 编译示例

```json
{
  "template": "templates/multi-factor-screener/page.template.html",
  "out_file": "output/pages/multi-factor-screener.html",
  "replacements": {
    "__PAGE_TITLE__": "AI 概念股多因子筛选",
    "__THEME_NAME__": "AI 概念股",
    "__ENDPOINT__": "https://test.quantbuddy.cn/skill",
    "pkg_rank_xxxxxxxx": "pkg_xxx",
    "sig_rank_xxxxxxxx": "只写入 HTML，不在回复里展示",
    "pkg_backtest_xxxxxxxx": "pkg_xxx",
    "sig_backtest_xxxxxxxx": "只写入 HTML，不在回复里展示"
  }
}
```
