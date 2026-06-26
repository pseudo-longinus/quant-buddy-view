# QuantBuddy Share Shell

公共落地页组件，供 `quant-buddy-view` 的 bespoke 模板和 `build_dashboard.py` 标准页在构建期内联使用。

## 文件

- `shell.html`：固定页头、页尾、分享海报弹层结构。
- `shell.css`：暗色品牌外壳、白底 logo、页头按钮、弹层、移动端约束。
- `poster.js`：固定海报页头/页尾、大二维码、canvas 绘制；默认前端截取页面主体作为预览，失败时再程序化降级，宁缺毋滥。
- `shell.js`：刷新、分享弹层、复制链接、复制图片、下载 PNG 行为。

## 模板契约

模板负责主体内容和数据解释，必须暴露：

- `load()`：刷新当前页面实时数据。
- `getPosterData()`：返回当前模板的动态海报内容。

接入方式：

```html
<!-- QB_SHARED_SHELL_CSS -->
<!-- QB_SHARED_SHELL_HEADER -->
<main>模板主体内容</main>
<!-- QB_SHARED_SHELL_FOOTER -->
<!-- QB_SHARED_SHELL_MODAL -->
<!-- QB_SHARED_QR_MINI -->
<!-- QB_DATA_KERNEL -->
<!-- QB_SHARED_SHELL_JS -->
<script>
function getPosterData(){ return { headline, summary, metrics, sections, asof }; }
QBShareShell.init({ onRefresh: load, getPosterData, templateName: "个股估值体检" });
load();
</script>
```

最终发布前用 `scripts/compile_bespoke_page.py` 编译，输出 HTML 必须自包含，不保留本地 `script src`、公共组件占位符或模板凭证占位符。

## 海报策略

默认海报不理解业务结构，而是前端截取当前页面状态：

- 优先截 `[data-qb-poster-target]`；
- 没有标记时截 `main`；
- 再没有则截 `.wrap` / `body`；
- 截图会自动排除公共页头、页尾、分享弹层、按钮、旧二维码以及 `[data-qb-poster-exclude]`。

模板可以给最想展示的主体容器加 `data-qb-poster-target`，但不要为海报单独复制一套 DOM。截图失败或显式传 `posterMode: "structured"` 时，才使用下面的结构化候选数据兜底。

## `getPosterData()` 返回结构

```js
{
  headline: "贵州茅台 个股估值体检报告",
  summary: "1-2 行核心说明",
  metrics: [{ label: "PE(TTM)", value: "23.1", sub: "实时取数" }],
  sections: [
    { title: "估值水位", type: "water", items: [{ label: "PB", value: 55, display: "55%" }] },
    { title: "归因拆解", type: "bars", items: [{ label: "价格变化", value: -8.2, display: "-8.2%" }] }
  ],
  asof: "2026.06.23"
}
```

结构化兜底会再次程序化筛选：

- `metrics` 最多展示 6 个，空值、占位值、口径类字段会被丢弃；
- `sections` 最多展示 1 个，高优先级为 `water` / `bars`，口径提示、免责声明等不会上图；
- 数据不够干净时不硬凑模块，只保留标题、摘要、二维码和“打开完整实时页”提示；
- 模板不要为了海报美观手搓 canvas，也不要把整页内容塞进 `sections`。

## 验收

- 页头固定为 `QuantBuddy · 宽宝`，右侧固定 `刷新数据 / 分享 / 开始使用`。
- 页面中不再出现旧的“手机扫码查看”二维码块或模板自带刷新按钮。
- 分享海报可预览、复制链接、复制图片、下载 PNG，二维码尺寸可扫。
- 移动端 320px 无横向溢出，弹层可滚动。
