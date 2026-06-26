 # quant-buddy-view

<p align="center">
  <img src="assets/banner.png" alt="quant-buddy-view" width="100%" />
</p>

<p align="center">
  <a href="README.md">中文</a> ·
  <a href="README.en.md">English</a> ·
  <a href="https://www.quantbuddy.cn">官网</a> ·
  <a href="https://www.quantbuddy.cn/templates">模板市场</a> ·
  <a href="https://tcn8bvcbyokw.feishu.cn/wiki/E1zswck3oiiJjJkP07QcmSG3nle?from=from_copylink">新手教程</a>
</p>

<p align="center">
  <a href="https://github.com/pseudo-longinus/quant-buddy-view/stargazers"><img alt="GitHub stars" src="https://img.shields.io/github/stars/pseudo-longinus/quant-buddy-view?style=social"></a>
  <a href="https://github.com/pseudo-longinus/quant-buddy-view/blob/main/LICENSE"><img alt="License" src="https://img.shields.io/badge/license-MIT-green"></a>
  <img alt="Python" src="https://img.shields.io/badge/Python-3.8%2B-blue">
  <img alt="Output" src="https://img.shields.io/badge/output-live%20dashboard-orange">
</p>

## 🔥 3 秒快速安装

如果你熟悉 Agent 工具（Claude Code、Cursor、OpenClaw 等），可以直接对 AI Agent 说：

> 帮我安装这个 skill：

```bash
npx skills add pseudo-longinus/quant-buddy-view -g -a claude-code -s quant-buddy-view -y
```

如果你不懂如何使用 Agent 和 skill，可以按照[小白图文教程](https://tcn8bvcbyokw.feishu.cn/wiki/E1zswck3oiiJjJkP07QcmSG3nle?from=from_copylink)一步步展开。

---

> **把你的投资想法，变成会自动更新的网页。**  
> 说出想跟踪的投资问题，[QuantBuddy（宽宝）](https://www.quantbuddy.cn)生成可分享、可更新的研究看板。

quant-buddy-view 是 QuantBuddy 家族里的**看板发布层**。它**不查行情、不跑回测**——那是 [quant-buddy-skill](https://github.com/pseudo-longinus/quant-buddy-skills) 的职责。它把你探索、验证好的指标，沉淀成一份**公开可分享、底层数据更新即自动重算**的网页看板。

从想法到看板，只有三步：

| 1. 你出想法 | 2. 宽宝计算 | 3. 网页上线 |
|---|---|---|
| 「帮我筛选高分红且低估值的股票」 | 自动匹配数据、指标与公式，注册成公式任务包 | 生成可分享的动态看板，得到一个公开链接 |

页面是「活」的：**数据变了，网页自动跟着变**——不用手动刷新截图、反复导出表格，页面背后的公式任务包会按约定重新计算，访问者打开即当日最新，无需后端，**API Key 不进前端**。

> 本项目用于金融数据分析、量化研究、策略验证和教育用途，不构成投资建议、交易建议、收益承诺或自动交易服务。

## 看看官方精选模板

下面这些都是 [QuantBuddy 模板市场](https://www.quantbuddy.cn/templates) 里的**官方精选模板**（由平台接口实时下发）。每个都能在模板市场**预览样例 → 下载模板 HTML / 复制提示词 → 交给 Agent 复用**，换成自己的标的 / 文案 / 公式包就生成属于你的看板。它们大多是「活」页面：纯静态 HTML，无后端、无数据库，打开时 `fetch` 一个公式任务包渲染，刷新即当日最新值。

| 官方精选模板                    | 分类               | 类型         | 一句话                             | 在线打开                                                                       |
| ------------------------- | ---------------- | ---------- | ------------------------------- | -------------------------------------------------------------------------- |
| A股涨跌停结构复盘                 | 📈 看市场 / 涨跌停复盘   | 实时 · 1 公式包 | 涨跌停、炸板率、连板梯队与市场情绪，适合每日复盘 / 短线情绪 | [预览](https://pages.quantbuddy.cn/pages/page_221a3ffae084d983d1b509d4.html) |
| 股指期货基差监控终端（主连/次主连）        | 📈 看市场 / 期货与衍生品  | 实时 · 1 公式包 | IF/IH/IC/IM 贴水升水、基差历史分位与期限结构    | [预览](https://pages.quantbuddy.cn/pages/page_1256a77743fab9aa39838ce9.html) |
| 贵州茅台 · 个股估值体检             | 🔍 看标的 / 估值与财务画像 | 实时 · 1 公式包 | 这只股票贵不贵、基本面是否改善                 | [预览](https://pages.quantbuddy.cn/pages/page_d4ca42720380d1b5bc3207c0.html) |
| 科创板 AI 硬科技组合 · 多维选股动态追踪   | 📦 管组合 / 主题组合    | 实时 · 3 公式包 | 指数状态 + 候选权重 + 回测 + 信号热力 + 触发监控  | [预览](https://pages.quantbuddy.cn/pages/page_4b488204774ddb45739d39cc.html) |
| 在噪声中寻找信号 · RSRS 择时的科学复现   | 🔬 做研究 / 量化方法论   | 实时 · 1 公式包 | 从高低价回归、标准化信号到仓位控制的完整择时研究流程      | [预览](https://pages.quantbuddy.cn/pages/page_c0c1e05bdad501fbb40641a3.html) |
| RSRS 阻力支撑相对强度择时 · 沪深300复现 | 🎯 看策略 / 择时与回测   | 实时 · 1 公式包 | 标准分、右偏修正信号、策略净值、买入持有对比与最大回撤     | [预览](https://pages.quantbuddy.cn/pages/page_d5ba93c6930902fdfa8b6f98.html) |

> 👉 也可在 [模板市场](https://www.quantbuddy.cn/templates) 一站浏览、下载模板 HTML 或复制提示词。**官方模板会持续补充上线**，数量与内容以官网实时返回为准。

<table align="center">
  <tr>
    <td align="center" width="50%">
      <a href="https://pages.quantbuddy.cn/pages/page_221a3ffae084d983d1b509d4.html"><img src="assets/tpl_limit_updown.png" width="430" alt="A股涨跌停结构复盘" /></a>
      <br/><sub><b>A股涨跌停结构复盘</b> · 看市场</sub>
    </td>
    <td align="center" width="50%">
      <a href="https://pages.quantbuddy.cn/pages/page_1256a77743fab9aa39838ce9.html"><img src="assets/tpl_index_futures_basis.png" width="430" alt="股指期货基差监控终端" /></a>
      <br/><sub><b>股指期货基差监控终端</b> · 看市场</sub>
    </td>
  </tr>
  <tr>
    <td align="center" width="50%">
      <a href="https://pages.quantbuddy.cn/pages/page_4b488204774ddb45739d39cc.html"><img src="assets/tpl_star_ai_portfolio.png" width="430" alt="科创板 AI 硬科技组合 · 多维选股动态追踪" /></a>
      <br/><sub><b>科创板 AI 硬科技组合</b> · 管组合</sub>
    </td>
    <td align="center" width="50%">
      <a href="https://pages.quantbuddy.cn/pages/page_d4ca42720380d1b5bc3207c0.html"><img src="assets/tpl_moutai_valuation.png" width="430" alt="贵州茅台 · 个股估值体检" /></a>
      <br/><sub><b>贵州茅台 · 个股估值体检</b> · 看标的</sub>
    </td>
  </tr>
  <tr>
    <td align="center" width="50%">
      <a href="https://pages.quantbuddy.cn/pages/page_c0c1e05bdad501fbb40641a3.html"><img src="assets/tpl_rsrs_research.png" width="430" alt="在噪声中寻找信号 · RSRS 择时的科学复现" /></a>
      <br/><sub><b>在噪声中寻找信号 · RSRS 研究</b> · 做研究</sub>
    </td>
    <td align="center" width="50%">
      <a href="https://pages.quantbuddy.cn/pages/page_d5ba93c6930902fdfa8b6f98.html"><img src="assets/tpl_rsrs_strategy.png" width="430" alt="RSRS 阻力支撑相对强度择时 · 沪深300复现" /></a>
      <br/><sub><b>RSRS 阻力支撑相对强度择时 · 沪深300复现</b> · 看策略</sub>
    </td>
  </tr>
</table>

> ⚠️ 以上均为模板的**示例展示**，所示数字为历史 / 示例数据，**不构成任何投资或交易建议**。

## 公共模板，参考复用；也能自定义自己的页面

### 公共模板市场：官方精选，打开即用、可参考复用

真正可复用的公共模板在 [QuantBuddy 模板市场](https://www.quantbuddy.cn/templates)——由平台**接口实时下发**的官方精选模板（不是写死在本仓库里的文件），就是[上面](#看看官方精选模板)那批，按看市场 / 看标的 / 管组合 / 做研究 / 看策略分类。每个模板都能**先「预览样例」确认是否匹配你的问题，再「下载模板 HTML」或「复制提示词」交给 Agent 复用**，换成自己的标的 / 文案 / 公式包，就生成属于你的看板。

模板市场随平台持续上线，数量与内容以官网和接口实时返回为准。在 skill 里也能直接拉取 / 复用，无需打开网页：

```bash
python scripts/static_page.py templates                              # 列出官方精选模板
python scripts/static_page.py template '{"template_id":"tpl_xxx"}'    # 看详情，拿 download_url 与提示词
```

### 仓库内置示例页面（参考起点，非官方模板）

本仓库 `skills/quant-buddy-view/templates/` 放的是一组**示例页面**——用来演示各类看板长什么样、版式怎么搭，方便你照着改；它们是**示例与起点，不是模板市场里的官方模板**：

| 示例 | 展示内容 |
|---|---|
| `single-stock` | 个股速览：数字卡（最新价 / 涨跌幅 / 20日 / 60日 / PE / PB / 成交额）+ 价格主图 |
| `valuation-financial-profile` | 个股估值体检：PE/PB/PCF 历史水位、财务趋势、现金流质量、估值变动归因 |
| `index-anomaly` | 成分股异动榜：异动榜单 + 涨跌分布 + 指数 sparkline（深色盘面） |
| `multi-factor-screener` | 多因子选股：主题股票池 + 多因子评分 + TopN + 回测/rankIC + K线 + 公式审计 |
| `commodity-daily` | 商品多空日报：板块多空主导 + 今日异动 + 头部品种 sparkline |
| `bubble-watch` | 泡沫监测终端：综合「温度」仪表盘 + 多市场泡沫水位 + 宏观背景 |

### 自定义自己的页面模板

公共模板和示例都满足不了的版式，你完全可以**手搓自己的页面**：自定义 HTML / CSS / SVG，数据层统一调用共享内核 `assets/data-kernel.js`（`QB.query` 取数、`QB.series / lastValue / topValues` 解包清洗），再套上公共 share-shell（页头、页尾、刷新、分享海报）发布。详见 `skills/quant-buddy-view/guides/bespoke-page.md`。

做好的自定义页面，验证后也可以**反过来沉淀成新的公共模板**供他人复用。

## 三段式用法

核心流水线：**注册公式包 → 生成看板 → 发布链接**。

```powershell
cd skills/quant-buddy-view

# 1. 注册公式任务包（需 API Key）：params.json 写 formulas + reads，中文公式用 @file 传避免编码截断
python scripts/formula_package.py register @params.json
#    → 返回 package_id + signature，落盘到 output/formula_packages/<package_id>.json

# 2. 生成看板 HTML：spec.json 写 title + panels，引用上一步的 package_id
python scripts/build_dashboard.py @spec.json
#    → 写出 output/pages/<slug>.html（spec 里加 "upload": true 可一步发布）

# 3. 发布托管：上传 HTML，得到公开可分享链接
python scripts/static_page.py upload '{"html_file":"output/pages/<slug>.html","title":"我的看板"}'
#    → 返回 https://pages.quantbuddy.cn/...
```

注册用的 `params.json` 示例：

```json
{
  "formulas": [
    "hs300_close = \"全市场每日收盘价\"*取出(沪深300)",
    "hs300_chg   = \"全市场每日回报率\"*取出(沪深300)"
  ],
  "reads": [
    { "output": "hs300_close", "read_mode": "range_data", "mode_params": { "lookback_days": 365 } },
    { "output": "hs300_chg",   "read_mode": "last_day_stats" }
  ],
  "ttl_days": 365
}
```

生成看板的 `spec.json` 示例：

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

> ⚠️ 提交注册的每一组公式，**必须先在 quant-buddy-skill 里用 `runMultiFormulaBatchStream` 跑通验证**（语法两边一致，可原样复用），出数后再 `register`。

## 后续维护

- **页面已分享、想改内容但保留原链接**（最常见）：重跑第 2 步生成新 HTML，再用 `update` 替换同一个 `page_id`——URL 不变，访问者刷新即见新内容，也不占新的活跃页配额。
- **数据更新了想刷新页面**：什么都不用做——页面是 live 实时取数，访问者打开即见最新。
- **下线页面**：`python scripts/static_page.py revoke '{"page_id":"page_xxx"}'`。
- **轮换公式包签名**：`python scripts/formula_package.py refresh '{"package_id":"pkg_xxx","rotate_signature":true}'`，再用新签名重建页面。

## 实时取数原理

发布的页面内嵌 `package_id + signature`，打开时即时调用 `queryFormulaPackage`（SSE 流式）拉取最新数据并渲染。两个前提（现行端点均已满足）：

1. `queryFormulaPackage` 对页面域名 `pages.quantbuddy.cn` 放开 CORS。
2. `signature` 是公式包的能力令牌，设计上即允许内嵌页面公开。

> ⚠️ 协议必须一致：页面发布在 `https://`，`config.json` 的 `endpoint` 也必须是 `https://`，否则浏览器会以 mixed-content 拦截取数。

## 安装

### npx（Node.js 包执行工具，推荐）

建议**只安装到自己正在使用的 AI Agent**，不要默认使用 `--all`。

| 你使用的 Agent | 推荐命令 |
|---|---|
| Claude Code | `npx skills add pseudo-longinus/quant-buddy-view -g -a claude-code -s quant-buddy-view -y` |
| Cursor | `npx skills add pseudo-longinus/quant-buddy-view -g -a cursor -s quant-buddy-view -y` |
| OpenClaw | `npx skills add pseudo-longinus/quant-buddy-view -g -a openclaw -s quant-buddy-view -y` |

已安装用户更新：

```bash
npx skills update quant-buddy-view -g -y
```

Windows 用户如遇 symlink（符号链接）或权限错误，可在命令后追加 `--copy`：

```bash
npx skills add pseudo-longinus/quant-buddy-view -g -a claude-code -s quant-buddy-view -y --copy
```

> 本项目与 [quant-buddy-skill](https://github.com/pseudo-longinus/quant-buddy-skills) 配合使用：先在 skill 里探索行情/因子/回测，再用 view 把指标做成看板发布。两者共用同一个 quant-buddy API Key。

## 配置 API Key

首次使用前需要配置 quant-buddy API Key：

1. 前往 <https://www.quantbuddy.cn/login> 注册并获取 API Key。
2. 编辑 skill 目录下的 `skills/quant-buddy-view/config.json`，将 `api_key` 字段填入你的 Key。
3. 或设环境变量 `QUANT_BUDDY_API_KEY`（优先级高于 config.json）。
4. 或在支持写入本地文件的 AI Agent 对话中发送：

```text
帮我配置 quant-buddy API Key：sk-xxxxxxxx
```

> 注册公式包 / 发布页面需 API Key（仅作为 `Authorization` 头发给 quantbuddy 声明域名）。看板内的**实时取数无需 API Key**，仅凭 `package_id + signature`。

## 运行环境

- **Python 3.8+**：核心流水线（注册 → 生成 → 发布）仅依赖 Python 标准库，**无需 `pip install`**。
- **Node.js 18+（可选）**：仅 `scripts/verify_page.mjs`（发布前页面验收）需要。
- **`playwright`（可选）**：`verify_page.mjs` 的视觉检查需要；缺失时自动跳过、不影响结构检查。

## 计费

创建和刷新看板按 **RU（资源用量单位）** 计费，随公式条数、数据量和重算复杂度变化。

> **当前处于限时免费体验中**：创建和刷新看板暂不消耗 RU。免费期结束后，复杂计算会按 RU 消耗。取数费用始终计入**公式包所有者**的配额，访问者免 API Key、零配置打开。实际消耗以平台账户页和接口返回为准。

## 安全与免责声明

- quant-buddy API Key 仅用于请求 quant-buddy 平台接口，只作为 HTTP `Authorization` 头发送到平台声明域名，不写入日志、不转发第三方。
- 自建服务时，API Key 必须放在服务端，不要写进浏览器代码或公开仓库；仓库内 `config.json` 的 `api_key` 默认为空，真实 Key 放 `config.local.json`（已被 .gitignore 忽略）或环境变量。
- `signature` 是公式包能力令牌，设计上会写进**公开** HTML 供实时取数；发布前请确认页面内容与可公开范围。
- 本项目用于金融数据分析、量化研究、策略验证和教育用途，不构成投资建议、交易建议、收益承诺或自动交易服务。
- 回测、筛选、因子和历史数据不代表未来收益。

## 联系作者

想看更多看板示例、接入问题、更新路线和真实投研工作流，欢迎扫码添加微信或加入交流群。

<p align="center">
  <table>
    <tr>
      <td align="center">
        <img src="assets/wechat_qr3.png" width="180" alt="个人微信二维码" />
        <br/>
        <sub>个人微信</sub>
      </td>
      <td align="center">
        <img src="assets/feishu_group_qr2.png" width="180" alt="飞书群二维码" />
        <br/>
        <sub>飞书群</sub>
      </td>
    </tr>
  </table>
  <br/>
  <sub>扫码添加微信或加入交流群，欢迎交流量化数据看板、AI Agent（智能代理）工作流和策略验证案例。</sub>
</p>

## Star History

<a href="https://www.star-history.com/?repos=pseudo-longinus%2Fquant-buddy-view&type=date&legend=top-left">
 <picture>
   <source media="(prefers-color-scheme: dark)" srcset="https://api.star-history.com/chart?repos=pseudo-longinus/quant-buddy-view&type=date&theme=dark&legend=top-left" />
   <source media="(prefers-color-scheme: light)" srcset="https://api.star-history.com/chart?repos=pseudo-longinus/quant-buddy-view&type=date&legend=top-left" />
   <img alt="Star History Chart" src="https://api.star-history.com/chart?repos=pseudo-longinus/quant-buddy-view&type=date&legend=top-left" />
 </picture>
</a>

## License

MIT
