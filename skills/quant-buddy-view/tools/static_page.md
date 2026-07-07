# static_page — 静态页托管（上传 / 替换 HTML → 公开可分享链接）

> 把一份自包含 HTML 看板上传到对象存储，返回 `https://pages.quantbuddy.cn/...` 公开链接，任何人凭链接即可在浏览器打开。之后凭 `page_id` 管理（替换内容 / 列表 / 撤销）。
> **替换（`update`）只换内容、不换链接**：页面已经分享出去后想再补充/调整，重建 HTML 后 `update` 同一个 `page_id` 即可，URL 不变、访问者刷新就看到新内容，也不占用新的活跃页配额。
> 通过本地脚本 `scripts/static_page.py` 调用，页面管理命令凭 `config.json` 的 API Key 认身份（归属由 api_key 推定，本技能无会话 / task_id 概念）；`verify_card_runtime` 直连 URL 模式只做公开 HTML 验收。

## 端点

| 操作 | 方法 + 路径 |
|------|-------------|
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
| 模板改写 | `POST /skill/updateTemplate`（is_test/admin；脚本命令 `update_template` 带并发复查） |

## 调用方式

```bash
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

# 浏览官方精选 / 看某个精选页面详情（拿下载链接克隆复用）
python scripts/static_page.py templates '{"page":1,"page_size":20}'
python scripts/static_page.py template  '{"template_id":"tpl_xxx"}'

# 已转 published template 的页面：保持原 page_id/public_url 安全改写
python scripts/static_page.py update_template '{"page_id":"page_xxx","html_file":"output/pages/x.html","verify_cover_card":true,"expected_metadata":{"download_url":"https://..."}}'

# 批量快速验收范式卡 card runtime artifact，不跑整页多视口
python scripts/static_page.py verify_card_runtime '{"page_ids":["page_xxx","page_yyy"],"require_browser":true}'
```

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

## 宽宝活卡发布门禁

`upload` / `update` 可传 `verify_cover_card:true`。脚本会先把最终 HTML 写入临时文件并执行两次浏览器验收：

- 默认页：`verify_page.mjs <html> --require-browser`
- 活卡页：`verify_page.mjs <html>?cover=1 --require-browser --cover-card`

任一失败都会返回 `code:1`，不会上传或覆盖线上页面。通过后，脚本会在请求体中带上 `has_cover_card:true`；如果服务端响应没有 `cover_card_url`，脚本会在返回 JSON 中补出建议值 `<url>?cover=1`。

## 范式卡 artifact 快速门禁

`upload` / `update` / `update_template` 可传 `verify_card_runtime:true`。脚本会把最终 HTML 写入临时文件，执行：

```bash
node scripts/verify_page.mjs <html> --card-runtime-only --require-browser
```

这条路径只验收嵌入的 card artifact，不跑默认页 / `?cover=1` 的整页多视口，因此适合模板库批量回归。检查项包括：

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

返回（save 时）：`{ code:0, page_id, owner, title, description, url, cover_card_url, has_cover_card, size, sha256, sha256_match, saved_to }`

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

**1) 浏览**：`templates` 列出官方精选页面

```bash
python scripts/static_page.py templates '{"page":1,"page_size":20}'
python scripts/static_page.py templates '{"category":"个股画像"}'
# 也可按标签筛选（id 来自后台标签表 / 详情回显）
python scripts/static_page.py templates '{"scene_tag_id":"tag_xxx"}'
```

返回 items 每条含：`template_id`（兼容字段，等同 `page_id`）/ `page_id` / `title` / `description` / `thumbnail_url` / `category` /
`cover_card_url` / `has_cover_card` / `is_template` / `template_status` / `download_url` /
`scene_tags` / `paradigm_tags` / `recommend_tags` 等（具体以服务端为准）。
默认已经限定 `recommend:官方精选`；可传 `scene_tag_id` / `paradigm_tag_id` / `recommend_tag_id` 作为叠加标签过滤。若服务端只返回
`has_cover_card:true`，脚本会用 `download_url/public_url/url + ?cover=1` 补出 `cover_card_url`。

**2) 看详情 / 拿下载链接**：`template`

```bash
python scripts/static_page.py template '{"template_id":"tpl_xxx"}'
```

返回：`{ code:0, template_id, page_id, title, description, thumbnail_url, category, is_template, template_status,
download_url, cover_card_url, has_cover_card, is_live, package_ids, packages,
scene_tags, paradigm_tags, recommend_tags }`。其中：

- `download_url` 是模板 HTML 的**公开下载链接**（OSS public-read），直接 GET 即得整页 HTML。
- `is_live` / `package_ids` / `packages` 说明该模板是否实时取数页、关联了哪些公式包（克隆后通常要
  换成你自己注册的公式包 signature 才能取你关心的标的数据）。

**3) 复用成自己的页**：取回模板 HTML → 改资产/文案/公式包 → `upload` 发布

```bash
# download_url 是 public-read，直接拉回本地（与 download 命令的「直连 OSS」同理）
curl -s "<download_url>" -o output/pages/from_tpl.html
# 改完（换公式包 signature、标的、解读文案）后，发布成自己的新页面
python scripts/static_page.py upload '{"html_file":"output/pages/from_tpl.html","title":"我的看板"}'
```

> 复用要点：模板里内嵌的是**原作者**的公式包 `signature`。若你要展示自己关心的标的，应在
> quant-buddy-skill 验证公式后用 `formula_package register` 注册**你自己的**包，把页面里的
> package_id + signature 换掉再 `upload`；否则页面取的还是模板原本那套数据。

### 公共模板：安全改写（`update_template`）

当一个原页面已被转成 published template，普通 `download/update` 可能返回 `PAGE_NOT_FOUND`。此时如果必须保持原模板链接，只能走 `update_template`，不要创建新页面顶替。

`update_template` 的安全流程：

1. 先调用 `template` 读取当前 metadata。
2. 如传入 `expected_metadata`，脚本比较 `download_url/title/description/category/size/sha256/updated_at` 等字段；发现变化就停止。
3. 编译公共 share shell；如传 `verify_cover_card:true`，先跑默认页和 `?cover=1` 浏览器验收；如传 `verify_card_runtime:true`，先跑 artifact 快速门禁。
4. 调 `POST /skill/updateTemplate` 写回同一个 `template_id/page_id`。
5. 写后再次 `template` 回查，并把 `preflight_template/postflight_template` 放进返回 JSON。

常用参数：`template_id` 或 `page_id`、`html/html_file`、`title`、`description`、`category`、`cover_card_url`、`has_cover_card`、`verify_cover_card`、`verify_card_runtime`、`expected_metadata`。

写回后必须以 `template` / `templates` 回查为准。若服务端暂未持久化 `cover_card_url` / `has_cover_card`，脚本返回里可能会根据本次参数补出建议值，但模板列表仍可能显示 `has_cover_card:false`。这种情况下 HTML 与 `?cover=1` 已经可用，前端可临时由 `download_url + "?cover=1"` 派生 iframe；metadata 持久化要作为后端阻塞项单独交接。

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
| `cover_card_url` | string | ❌ | 无 | 宽宝活卡 iframe URL；通常为发布 URL + `?cover=1` |
| `has_cover_card` | bool | ❌ | false | 模板库是否可展示 live card |
| `verify_cover_card` | bool | ❌ | false | 发布前本地验收默认页和 `?cover=1 --cover-card`；失败不上传 |
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
| `cover_card_url` | string | ❌ | 无 | 宽宝活卡 iframe URL；通常为原页面 URL + `?cover=1` |
| `has_cover_card` | bool | ❌ | false | 模板库是否可展示 live card |
| `verify_cover_card` | bool | ❌ | false | 替换前本地验收默认页和 `?cover=1 --cover-card`；失败不覆盖 |
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
  "expires_at": "2027-..." }
```

`url` 即对外分享链接，浏览器直接可开（自定义域名内联渲染，不触发下载）。

> `scene_tags` / `paradigm_tags` 回显解析后的 `{tag_id,name,source}`；范式里现写的新名 `source=user`。`update` 响应同结构。读接口（`getStaticPage` / `list` / `templates` / `template`）也透出 `scene_tags` / `paradigm_tags`，并附后台维护的 `recommend_tags`（**只读**）。

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
