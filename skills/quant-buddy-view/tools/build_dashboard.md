# build_dashboard — spec → 自包含看板 HTML

> 把「公式任务包 + 看板 spec」编译成一份自包含 HTML（样式内联，图表用公网 CDN ECharts）。可顺带上传发布。
> 通过本地脚本 `scripts/build_dashboard.py` 调用（单命令，无子命令）。

## 调用方式

```bash
# 写好 spec.json，生成 live 实时取数 HTML
python scripts/build_dashboard.py @spec.json

# 生成并一步发布（upload 凭 config.json 的 api_key 认身份）
BD_PARAMS='{"title":"...","panels":[...],"upload":true}' python scripts/build_dashboard.py
```

## spec 参数（优先级：BD_PARAMS > @file > 命令行 JSON > stdin）

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `title` | string | ✅ | 看板标题（`<title>` + 页头） |
| `subtitle` | string | ❌ | 副标题 |
| `description` | string | ❌ | 页面说明（≤1000 字），仅作 `static_page` 列表/详情展示；显式传才随 upload/update 透传，不传则不动 |
| `package_id` | string | ❌ | 公式包 id；缺省取**最近一次**本地凭证 |
| `signature` | string | ❌ | 缺省从本地凭证补全；会写入页面供实时取数，必须可得 |
| `panels` | object[] | ✅ | 面板数组，见下 |
| `out_file` | string | ❌ | 输出 HTML 路径，默认 `output/pages/<slug>.html` |
| `upload` | bool | ❌ | true 则生成后调用 `static_page` 上传，结果回填 `url` |
| `update_page_id` | string | ❌ | 替换已发布页面，URL/page_id 不变 |
| `verify_packages` | bool | ❌ | 上传/替换后强制解析页面内 package_id + signature 做一次轻量 query 校验；默认仅服务端提示公式包异常时触发 |
| `ttl_days` | number | ❌ | 配合 upload 透传 |
| `brand` | object | ❌ | 统一分享外壳配置，见下 |
| `official_url` | string | ❌ | 官网入口，默认 `https://www.quantbuddy.cn` |
| `show_qr` | bool | ❌ | 是否显示页面二维码，默认 `true` |
| `share_url` | string | ❌ | 二维码指定链接；缺省时浏览器用最终页面 `location.href` 生成 |
| `page_type` | string | ❌ | 页头标签，默认 `量化看板` |
| `template` | string | ❌ | 页面模板标识；单标的画像页请传 `single-stock`，会启用模板契约校验 |

### 统一分享外壳

`build_dashboard` 默认给所有标准页面加上 QuantBuddy 分享外壳：品牌页头、官网入口、扫码二维码、标准页尾和风险提示。
二维码在浏览器端生成：未传 `share_url` 时使用当前页面 `location.href`，因此上传到 `pages.quantbuddy.cn` 后，二维码自动指向最终公开链接。
二维码卡仅在桌面/宽屏展示；移动端默认隐藏二维码区域，把首屏空间留给标题、摘要和官网入口。

`brand` 可覆盖展示文案：

Share shell design and verification rules live in [`guides/share-shell.md`](../guides/share-shell.md).

Default brand logo: standard pages inline `assets/logo.svg` into the share header so uploaded HTML does not depend on a local file path. If the SVG is missing or fails the safety check, the header falls back to the text mark `QB`.

```json
{
  "brand": {
    "name": "QuantBuddy",
    "cn_name": "观照量化",
    "tagline": "Agent 调用 Skill 计算 · HTML 可调",
    "homepage": "https://www.quantbuddy.cn",
    "page_type": "个股画像",
    "official_label": "进入官网",
    "share_title": "手机扫码查看",
    "footer_note": "页面仅作市场观察与数据展示，不构成投资建议。",
    "show_qr": true
  }
}
```

### `panels[]` 元素

| 字段 | 必填 | 说明 |
|---|---|---|
| `output` | ✅ | 对应公式包 `reads` 的产出名（= query 返回 outputs 的 key）；`text` 面板不需要 |
| `title` | ❌ | 面板标题，缺省用 `output` |
| `type` | ❌ | `line` / `bar` / `table`（默认） / `number` / `text` / `raw` |
| `x` | ❌ | line/bar 横轴字段（缺省取首列；range_data 自动取 dates） |
| `y` | ❌ | line/bar 纵轴字段数组（缺省取除 x 外的数值列） |
| `columns` | ❌ | table 指定列（缺省自动推断） |
| `value_field` | ❌ | number 取值字段（缺省取**最后一个数值列的末个有效值**，自动跳过尾部 null；range_data 即取序列值，不会误命中日期列。仅当默认列不对时才需指定） |
| `unit` | ❌ | number 单位 |
| `description` | ❌ | 面板说明；number 面板会显示在数值下方，其它面板显示在标题下方 |
| `span` | ❌ | `full` / `wide` / `auto`；line/bar 默认 `full`，number/table 默认 `auto` |
| `height` | ❌ | 图表高度，单位 px；仅 line/bar 有效 |
| `text` | ❌ | `text` 面板正文，用于摘要、解读、风险提示等无取数输出的说明块 |

> 渲染器会自动把公式包各 read_mode 的 `data` 归一为 {列, 行}：
> `range_data.{dates,values}` → 折线；`last_day_stats` 对 1 维序列返回的 `last_value.{date,value}` → 数值；
> `last_day_stats.top_values[]` / `last_valid_per_asset[]` → 表格。多数 panel 只需写 `output` + `type`。
> 渲染器已内置：整数日期 `YYYYMMDD` → `YYYY-MM-DD`、裁掉序列尾部 null、折线 `connectNulls`、number 跳空取末个有效值——**这些后处理不必再在 spec 里手写**。
> `text` 面板不需要 `output`，构建期体检会跳过它；适合在单标的画像页里放一句摘要或观察点。

> ⚠️ **构建期取数失败即硬失败**：构建时会先取一次数做质量体检（只用于校验，不内联进 HTML）。若有任一产出失败或体检为空（如 range_data 全 null / 区间无数据），`build_dashboard` 返回 `code:1` 并在 `failed_outputs` 指明哪个 output、疑因，**不生成 HTML**。务必检查返回 `code`，不要把「没报错」当成功。

### 模板契约校验

单标的画像页必须从 `templates/single-stock/spec.template.json` 起步，并保留 `template: "single-stock"`。

如果标题或 `page_type` 表明是“个股画像”，但 spec 仍是旧版 `1 条价格线 + 少量数字卡`，`build_dashboard` 会返回 `code:1`，并提示补齐：

- 阅读摘要 `text` panel；
- 最新收盘价 `px` number panel；
- `chg` / `ret20` / `ret60` / `pe` / `pb` / `amt_yi` 默认 outputs；
- 近一年收盘价 `px` line panel。

单标的画像页还会校验 `subtitle` 和阅读摘要中的关键数值是否匹配构建期实时取数结果（最终 outputs）。若文案里写了收盘价、涨跌幅、20/60 日表现、PE、PB、成交额，但数值与最终取数不一致，脚本返回 `code:1`、`mismatches` 和 `facts`。用 `facts` 重写文案后再生成/上传。

## 实时取数

页面是实时取数的：HTML 骨架自包含（样式/脚本内联），数据在浏览器打开时实时 `fetch` 最新——底层数据更新后无需重新 build，页面打开即最新。

- HTML 内写入 `endpoint / package_id / signature`，打开时调 `queryFormulaPackage` 取数（signature 会公开在页面里）。
- 前置：端点须对页面域名放开 **CORS**，且页面与端点协议一致（https 页面配 https 端点，否则 mixed-content 被拦）。当前 `https://test.quantbuddy.cn/skill` 已满足。
- 构建期仍会取一次数，用于质量体检 + 单标的文案一致性校验 + 产出 `facts`，不会内联进 HTML。
- spec 不需要写 `mode` 字段；旧 spec 里残留的 `"mode"` 会被忽略。

## 输出

```json
{ "code": 0, "out_file": "output/pages/xxx.html", "mode": "live",
  "package_id": "pkg_...", "panels": 3, "size": 12345,
  "manifest": "output/pages/xxx.manifest.json",
  "facts": {"px":{"value": 166.41, "date": 20260616}},
  "url": "https://pages.quantbuddy.cn/..."  // 仅 upload=true 且成功时 }
```

同名 `*.manifest.json` 会记录 `page_id`、URL、HTML sha256、endpoint、公式包角色、package_id、构建时间和验证结果；不会记录 API key 或 signature。

> 端到端示例：[workflows/dashboard-end-to-end.md](../workflows/dashboard-end-to-end.md)。
