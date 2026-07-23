# Share Shell Guide

Use this guide when changing the shared QuantBuddy landing-page shell: header, footer, refresh action, share-poster modal, poster canvas, QR code, copy image, and download PNG behavior.

## Product Intent

Every generated landing page should feel like one QuantBuddy artifact even when the body template is different:

- the body answers the user's concrete data question;
- the shell provides the fixed QuantBuddy brand frame;
- the refresh action reloads live formula-package data;
- the share action creates a paste-ready poster with a fixed header, fixed footer, and dynamic body content;
- the final HTML remains self-contained after build or publish.

## Source Of Truth

Shared component files live in:

```text
assets/share-shell/
  shell.html
  shell.css
  shell.js
  poster.js
  README.md
```

Templates must not fork private header/footer/share-modal implementations. If the shell needs a visual or behavioral change, update the shared files and recompile affected pages.

## Public Interface

Each bespoke template must expose:

```js
function load() { /* refresh live data */ }
function getPosterData() {
  return {
    headline: "...",
    summary: "...",
    metrics: [{ label: "...", value: "...", sub: "..." }],
    sections: [{ title: "...", type: "list|bars|water", items: [] }],
    asof: "..."
  };
}

QBShareShell.init({
  templateName: "个股估值体检",
  onRefresh: load,
  getPosterData
});
```

The shell owns:

- header brand text: `QuantBuddy · 宽宝`;
- header actions: `刷新数据 / 分享 / 开始使用`;
- footer risk note and official-site link;
- share modal structure;
- poster copy/download behavior;
- poster header/footer and large QR code.

The template owns:

- page body layout;
- data loading and rendering;
- dynamic poster headline, summary, metrics, sections, and `asof`.

The poster preview is intentionally empty until the user opens the share modal. Any `<img>` whose `src` is assigned only at runtime must declare `data-qb-runtime-src`; ordinary content images still require a non-empty static `src`. Do not add a transparent placeholder image, because `shell.js` uses an empty `src` to decide whether poster generation must run before download.

## Theming

公共页头和页尾的布局固定，模板或迁移脚本只能通过 CSS 变量换颜色：

```css
:root {
  --qb-shell-chrome-bg: #101827;
  --qb-shell-header-bg: var(--qb-shell-chrome-bg);
  --qb-shell-footer-bg: var(--qb-shell-chrome-bg);
  --qb-shell-accent: #d8a54b;
  --qb-shell-accent-strong: #d8a54b;
  --qb-shell-line: rgba(216,165,75,.35);
}
```

`--qb-shell-header-bg` 和 `--qb-shell-footer-bg` 可分别覆盖；不传时都跟随 `--qb-shell-chrome-bg`。不要为了主题色复制一份 header/footer DOM。

## Build-Time Inlining

Compile bespoke pages with:

```powershell
python scripts/compile_bespoke_page.py @params.json
```

The compiler replaces these placeholders:

```html
<!-- QB_SHARED_SHELL_CSS -->
<!-- QB_SHARED_SHELL_HEADER -->
<!-- QB_SHARED_SHELL_FOOTER -->
<!-- QB_SHARED_SHELL_MODAL -->
<!-- QB_SHARED_QR_MINI -->
<!-- QB_DATA_KERNEL -->
<!-- QB_SHARED_SHELL_JS -->
```

Final HTML must not contain local `script src` references to `qr-mini.js`, `data-kernel.js`, or `_shared` files.

## Retrofitting Old Pages

旧页面已经生成或发布后，不要靠提示词手工删除二维码、页头、页尾。使用迁移工具：

```powershell
python scripts/retrofit_share_shell.py '{"url":"https://pages.quantbuddy.cn/pages/.../page_xxx.html","out_file":"output/pages/page_xxx-retrofit.html","theme":{"chrome_bg":"#101827","accent":"#d8a54b"}}'
```

确认本地 HTML 后，覆盖原链接：

```powershell
python scripts/retrofit_share_shell.py '{"page_id":"page_xxx","update":true,"theme":{"chrome_bg":"#101827","accent":"#d8a54b"}}'
```

详情见 [`tools/retrofit_share_shell.md`](../tools/retrofit_share_shell.md)。

## Verification Checklist

- Run `python -m py_compile scripts/build_dashboard.py scripts/compile_bespoke_page.py scripts/retrofit_share_shell.py`.
- Confirm generated HTML has no `QB_SHARED_`, `__PLACEHOLDER__`, `pkg_replace`, or `replace_with_signature` residue.
- Verify desktop, 390px, and 320px widths have no horizontal overflow.
- Verify header actions show `刷新数据 / 分享 / 开始使用`.
- Verify the old body QR block (`手机扫码查看`) is absent.
- Verify share modal generates a `900x1400` PNG poster.
- Verify copy image works, or degrades to a clear fallback message when Clipboard permissions are unavailable.
- For public pages, use `static_page.py update` when preserving an already shared URL.
