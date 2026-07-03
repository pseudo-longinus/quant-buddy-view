# Guide · 宽宝活卡（精华卡 / 封面卡模式）

> 场景：用户要把一个 QuantBuddy 页面浓缩成一张固定 4:3 卡片，用作官网卡片流、封面、缩略图源图、分享素材或「一眼看懂」摘要。
> 这不是另做一个静态截图页，而是在同一份实时 HTML 里加一个可通过 URL 参数进入的 card-only 模式。
> 功能和对外称呼仍可叫「宽宝活卡」；但卡片内部不再内置可见的左上角「宽宝活卡」文案，左上角只预留给官网后续统一注入标签。「精华卡 / 封面卡 / cover card」只作为开发和路由别名保留。

## 触发词

用户提到这些词时默认走本指南：

- 精华卡、摘要卡、封面卡、cover card、card-only；
- 4:3 卡片、封面、缩略图源图、单独拎出来；
- “URL 后面拼 `?cover=1`，只显示这张 card，其它元素隐藏”。

## 必须满足的契约

1. **同一份 HTML**：在目标页面里新增卡片模式，不另起一个脱离原页面的数据副本。
2. **实时更新**：卡片内容必须复用页面同一轮 `QB.query` 结果、`STATE.metrics`、outputs 或等价状态；不要把日期、分数、价格、涨跌幅、榜单等数值写死。
3. **默认隐藏**：普通 URL 打开完整页面，卡片不显示且不占位。
4. **URL 参数进入封面模式**：标准入口只用 `?cover=1`，只显示 4:3 卡片，其它页面元素全部隐藏。为兼容旧页，可继续识别 `?essence=1` / `?cardOnly=1`，但新文案、新官网入口不要再使用它们。
5. **参数可关闭**：`?cover=0` / `?essence=0` / `?hideCover=1` / `?hideEssence=1` 应回到完整页面。
6. **4:3 固定比例**：普通页面里的卡片预览可用 `aspect-ratio: 4 / 3`。进入 `?cover=1` 后，浏览器视口本身就是 4:3 卡片画布，官网 iframe / 截图工具会提供 720×540、580×435、390×292、320×240 等 4:3 视口；卡片必须填满整个视口，不要靠截图裁切伪造比例，也不要新增 `ratio` / `gallery` 等尺寸参数。
7. **封面模式视口即卡片**：`?cover=1` 不是「页面里居中放一张 4:3 卡片」，而是「整个 viewport 就是一张宽宝活卡」。禁止出现页面级灰底、外边距、内边距、留白、letterbox、滚动条或卡片外框之外的背景。
8. **官网浅色系**：宽宝活卡必须是浅色卡片系统，禁止整卡暗色、黑底、深蓝底或靠深色大面积背景形成主题。主题色可以是红、蓝、绿、橙等，但只能作为强调色，用在顶部细线、核心图形、关键数字、标签或结构条。
9. **固定信息骨架**：顶部左侧只放官方标签预留位，不显示固定品牌文案；右侧显示 `YYYY-MM-DD` 更新日期；第二行是标题或一句重点结论；第三行是描述；第四个区域是核心表达区。标题、描述、顶部 meta 的字号必须使用统一 token，不要每张卡自由发挥。
10. **可验收 DOM 标记**：新卡片根节点必须带 `data-qb-live-card`，并给左上角标签预留位、日期、标题、描述、核心区分别加 `data-qb-live-card-brand` / `data-qb-live-card-date` / `data-qb-live-card-title` / `data-qb-live-card-description` / `data-qb-live-card-core`。`data-qb-live-card-brand` 可以为空；`#essenceCard` 仅作为兼容旧页保留。
11. **本地先对齐**：先下载/生成本地 HTML 修改并截图给用户确认；用户确认后才走 `static_page.py update` / 模板维护路径。

## 视觉系统

宽宝活卡 = 统一浅色官网外壳 + 固定信息层级 + 可变核心可视化。

推荐 token：

```css
:root {
  --qb-live-bg: #fffaf2;
  --qb-live-surface: #ffffff;
  --qb-live-ink: #201713;
  --qb-live-muted: #6f5a43;
  --qb-live-border: #ead8c6;
  --qb-live-brand: #ffd45a;
  --qb-live-accent: #d71920;
  --qb-live-pad-x: clamp(18px, 5.6vw, 44px);
  --qb-live-pad-y: clamp(16px, 5vw, 38px);
  --qb-live-core-gap: clamp(8px, 1.5vw, 12px);
  --qb-live-meta-size: 11px;
  --qb-live-title-size: 28px;
  --qb-live-desc-size: 13px;
  --qb-live-body-size: 12px;
}

@media (max-width: 420px) {
  :root {
    --qb-live-meta-size: 9px;
    --qb-live-title-size: 18px;
    --qb-live-desc-size: 11px;
    --qb-live-body-size: 10px;
  }
}
```

主题色可以覆盖 `--qb-live-accent`，但不要覆盖成暗色整卡背景。浅色主题可以这样做：

```css
.essence-card[data-theme="red"] { --qb-live-accent: #d71920; }
.essence-card[data-theme="blue"] { --qb-live-accent: #1f5fbf; }
.essence-card[data-theme="green"] { --qb-live-accent: #278a5b; }
.essence-card[data-theme="orange"] { --qb-live-accent: #ef7a1a; }
```

## 固定四行骨架与空间预算

宽宝活卡的外壳必须稳定，差异只落在第四个核心表达区。生成或改造 card HTML 时，先把卡片拆成四行再做内容：

1. **Meta 行**：左侧是官方标签预留位，可为空，不显示固定「宽宝活卡」文案；右侧是 `YYYY-MM-DD` 日期。日期使用 muted 色，字重通常为 `700`，字号走 `--qb-live-meta-size` 或同级 token，不要比标题或描述抢眼。
2. **标题行**：一句重点结论，使用统一标题 token，字重通常为 `900`，行高约 `1.05-1.12`。不要因某个模板单独放大或缩小标题；如果标题与原页面标题重复，改成判断句。
3. **描述行**：一句解释依据，使用 muted 文本色，字号走 `--qb-live-desc-size`，字重通常 `500-600`，行高约 `1.25-1.45`。默认 1 行，必要时最多 2 行；不要把方法说明、长脚注或榜单解释塞进这里。
4. **核心表达区**：前三行之后的全部剩余空间都属于 `data-qb-live-card-core`。这里根据原页面精华选择视觉主导或数字主导，内部可以有图形、主数字、结构条、指标 chip，但不能复制完整页面。

布局实现建议：

```css
.essence-card[data-qb-live-card] {
  aspect-ratio: 4 / 3;
  padding: var(--qb-live-pad-y) var(--qb-live-pad-x);
  display: grid;
  grid-template-rows: auto auto auto minmax(0, 1fr);
  gap: var(--qb-live-core-gap);
}

[data-qb-live-card-core] {
  min-height: 0;
  overflow: hidden;
}
```

卡片外层内边距要四周一致，并随视口等比例收敛；不要只压缩顶部或只扩大底部。第四区的内部留白应小于外层留白，通常用 `4-12px` 的 gap / padding 即可；如果内层卡片、图表或指标组离核心区边界太远，封面会显得松散。

第四区必须“吃满”剩余空间：不要让核心区是内容的自然高度后在底部留下大块空白；也不要保留空的 `1fr` 行、隐藏模块遗留轨道或无内容分隔线。若核心区包含“主图形 + 指标 chip”，应让主图形填满上方/左侧剩余空间，指标 chip 固定高度并贴近核心区底部或侧边；若是数字主导，主数字/等级与 2-3 个解释指标要共同占满核心区，而不是漂在中间。

## 推荐结构

默认使用 qbv 内置 live-card 资产，不要每个页面重新设计一套外壳。bespoke HTML 模板里放：

```html
<!-- QB_LIVE_CARD_CSS -->
<!-- QB_LIVE_CARD_JS -->
```

再通过 `scripts/compile_bespoke_page.py` 编译，脚本会内联 `assets/live-card.css` 和 `assets/live-card.js`。如果页面不走编译脚本，也必须复制这两个资产的等价 CSS/JS 规则，不能另起暗色或不统一的卡片系统。

如果模板里还没有卡片 DOM，可以直接给编译器传 `live_card` 参数生成标准 cardHTML：

```json
{
  "template": "output/pages/source.html",
  "out_file": "output/pages/with-live-card.html",
  "live_card": {
    "theme": "blue",
    "title": "页面核心结论一眼看懂",
    "description": "核心指标实时刷新，打开即取最新公式包输出。",
    "metrics": [
      {"label": "主指标", "output": "SCORE", "field": "value", "unit": "分"}
    ],
    "tags": ["实时取数", "重点摘要"]
  }
}
```

已有 `data-qb-live-card` 的页面不会重复插入第二张卡；编译器只补齐 live-card CSS/JS 和运行时绑定。

卡片放在 `main` 顶部，默认 `hidden`：

```html
<main data-qb-poster-target>
  <section class="essence-section" id="essenceSection" hidden>
    <article class="essence-card" id="essenceCard" data-qb-live-card>
      <div class="live-card-meta">
        <span data-qb-live-card-brand></span>
        <time data-qb-live-card-date datetime="2026-07-01">2026-07-01</time>
      </div>
      <h1 data-qb-live-card-title>页面核心结论标题</h1>
      <p data-qb-live-card-description>用一行描述说明核心判断依据。</p>
      <section class="live-card-core" data-qb-live-card-core>
        <!-- 数字、图标、圆环、结构条、曲线图、小图表或指标矩阵 -->
      </section>
    </article>
  </section>

  <!-- 原页面主体继续保留 -->
</main>
```

CSS 用 HTML class 控制封面模式：

```css
<!-- QB_LIVE_CARD_CSS already provides the standard styles. -->
```

> 注意：完整页面模式可以把卡片居中展示；封面模式必须让卡片根节点贴齐 viewport。不要在封面模式的 `html`、`body`、`main`、`#essenceSection` 上留下固定 `padding`、`margin`、`min-height` 或页面背景。

## 核心表达区

核心区可以根据页面类型变化，但只在 `data-qb-live-card-core` 容器里变化：

先判断原页面最有辨识度的“玩法”是什么，再把它浓缩成一个轻量可视化。宽宝活卡不是把所有模板都改成大数字 + 四宫格，也不是把完整页面缩小塞进去；统一的是浅色外壳、信息骨架和“扫一眼能懂”的信息密度，差异应该落在核心表达区。

优先在两种结构里选择，不要为每个模板发明完全不同的骨架：

- **数字主导 numeric-focus**：适合市场温度、涨跌停结构、估值水位、风险评分等指标型页面。版式为一句结论标题 + 1 个大数字/等级 + 2-3 个解释指标 + 1 条结构条或进度条 + 2-3 个短标签。
- **视觉主导 visual-focus**：适合组合画像、多因子、趋势曲线、雷达图、泡沫场等有标志性图形的页面。版式为一句结论标题 + 1 个简化图形 + 2-3 个指标/chip；图形只表达主判断，不复制整页图表和表格。

两种结构必须先二选一：大数字/等级和主图形不要同时作为核心表达。允许在标题或 chip 里出现数字，但卡片主视觉只能有一个。机器验收会按内容预算检查：标题不超过 24 个紧凑字符，描述不超过 56 个紧凑字符，整卡文本不超过 170 个紧凑字符，解释指标不超过 3 个，短标签不超过 3 个，不保留二级阅读块、排行榜或脚注式方法说明。

- 市场温度、泡沫监测：圆环、温度计、mini 泡沫场、分层结构条，浅底上使用主题色强调。若原页主视觉是“哪些市场在沸腾”，卡片应保留 4-5 个随评分改变大小/颜色的泡泡，而不是只放普通横向条。
- 涨跌停、异动复盘：大数字、红绿结构条、涨跌/炸板/连板的指标矩阵。
- 多因子选股、组合跟踪：雪花图、雷达图或单条权重/回撤/信号结构，不要在卡片里再放 TopN 排行榜。
- 估值财务：估值水位仪表、PE/PB 分位、财务趋势小曲线。
- 研究/回测：信号曲线、净值小图、关键统计卡。

不要为了差异化改变顶部、标题、描述、日期、字体尺度或浅色外壳。
不要把页面特色降级成截图，也不要把完整页面的小号版本塞进卡片。正确的压缩方式是：保留 1 个主判断、1 个大数或页面标志性小图、2-3 个解释指标。
删掉排行榜、脚注或多段说明后，要同步收紧 grid/flex 轨道；不要留下空的 `1fr` 行、底部分隔线或大片无内容区域。主视觉和 2-3 个指标块应共同吃满核心区，并且在 390×292、320×240 等小视口下仍贴近核心区边界，不要因为内层 padding 过大显得内容悬空。

## 推荐参数逻辑

```js
function truthyParam(v) {
  return ["1", "true", "yes", "on", "show", "visible"].includes(String(v || "").toLowerCase());
}

function falsyParam(v) {
  return ["0", "false", "no", "off", "hide", "hidden"].includes(String(v || "").toLowerCase());
}

function shouldShowEssenceCard() {
  const params = new URLSearchParams(window.location.search);
  if (truthyParam(params.get("hideEssence")) || truthyParam(params.get("hideCover"))) return false;
  const value = params.get("cover") || params.get("essence") || params.get("cardOnly");
  if (value != null) {
    if (truthyParam(value)) return true;
    if (falsyParam(value)) return false;
  }
  return false;
}

function applyEssenceVisibility() {
  if (window.QBLiveCard) return window.QBLiveCard.applyVisibility();
  const show = shouldShowEssenceCard();
  document.documentElement.classList.toggle("essence-cover-mode", show);
  const section = document.getElementById("essenceSection");
  if (section) section.hidden = !show;
  return show;
}
applyEssenceVisibility();
```

使用内置脚本时只需要：

```js
QBLiveCard.applyVisibility();
QBLiveCard.setDate(document, STATE.tradeDate || new Date());
QBLiveCard.setText(document, "[data-qb-live-card-title]", title);
QBLiveCard.setText(document, "[data-qb-live-card-description]", summary);
```

## 内容口径

卡片应该浓缩全页最核心的判断，而不是复制整页：

- 左上角：保留 `data-qb-live-card-brand` 作为官方标签预留位，默认不显示「宽宝活卡」或「精华卡」等固定文案。
- 日期：实时数据口径对应的更新日期，展示为 `YYYY-MM-DD`。
- 标题：优先写一句重点结论；如果外层模板标题已经说明对象，卡片内标题不要重复同一句标题。
- 主指标：优先放全页最重要的 1 个分数/价格/热度/风险等级。
- 标志性小图：保留原页面最能被记住的可视化语言，例如泡沫场、涨跌停结构、估值水位或净值曲线。
- 指标组：放 2-3 个能解释结论的核心指标；只有当它确实服务页面判断时才使用，不要让四宫格成为默认答案。
- 结构条或小趋势：只保留最能说明方向的一条，或换成与页面主题更贴切的轻量图形。
- 三条读法：用实时数据生成“广度 / 承接 / 高度”或该页面对应的三类解释。
- 标签：2-3 个短标签，避免长句。

不要把整页的表格、长解释、公式审计搬进卡片。卡片是封面，不是报告正文。
不要把暗色 dashboard 截图直接嵌进卡片当背景；官网范式库里所有宽宝活卡都应读成同一个浅色产品系统。

## 验收清单

至少检查两种 URL：

1. 默认 URL：
   - 完整页面正常；
   - 精华卡不可见、不占位；
   - `verify_page.mjs <html_file> --require-browser` 通过。
2. 封面 URL，如 `?cover=1`：
   - 页面只显示 4:3 卡片；
   - 卡片根节点填满 4:3 viewport，无外层灰底、留白、滚动条或黑屏；
   - 页头、页尾、原主体模块、分享弹层不显示；
   - 顶部左侧有官方标签预留位但不显示固定「宽宝活卡」文案，右侧日期为 `YYYY-MM-DD`；
   - 标题、描述、核心区分别带 `data-qb-live-card-title` / `data-qb-live-card-description` / `data-qb-live-card-core`；
   - 第一行日期、第二行标题、第三行描述的颜色、字号、粗细使用统一 token；不要让某张卡自由改字体层级；
   - 卡片外层内边距四周一致，第四个核心表达区吃满前三行之后的剩余空间；
   - 核心区内部图形、数字和指标 chip 不离边界过远，不留下大块空白或隐藏模块遗留轨道；
   - 卡片内标题不与外层模板标题机械重复；重复时改成一句重点结论；
   - 卡片根背景是浅色官网系，不是整卡暗色；
   - 卡片先选择 `numeric-focus` 或 `visual-focus`：大数字/等级与主图形二选一，解释指标不超过 3 个，短标签不超过 3 个；
   - 不保留二级阅读块、TopN 排行、脚注式方法说明或完整页面缩略内容；
   - 卡片数值来自实时取数结果，不长期停在“取数中 / 判断生成中 / —”等占位态；
   - 截图画面可作为封面源图。
   - 运行 `node scripts/verify_page.mjs "<html_or_url>?cover=1" --require-browser --cover-card` 通过。

如要更新线上已分享页面，仍按原页面性质选择路径：

- 普通静态页：`static_page.py update`，保持同一个 `page_id` / URL。
- 已转公共模板且普通 update 报 `PAGE_NOT_FOUND`：先 `template --page_id` 确认，再走后台/admin `updateTemplate` 路径，不要新建链接冒充原链接。
