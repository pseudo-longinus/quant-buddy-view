# Page Templates

Use this directory when the user asks for a concrete reusable page shape.

Each template owns a directory:

```text
templates/<template-name>/
  README.md              # when to use it, data contract, agent-editable slots
  spec.template.json     # for standard build_dashboard pages, when applicable
  page.template.html     # for bespoke HTML pages, when applicable

templates/_shared/share-shell/
  shell.html             # shared header, footer, and share modal structure
  shell.css              # shared shell styling
  shell.js               # refresh/share/copy/download bindings
  poster.js              # fixed poster canvas renderer with dynamic body adapter
```

| Display name | Template slug | Use when | Rendering path |
|---|---|---|---|
| 个股速览 | `single-stock/` | One stock/index profile page with price trend and valuation/activity cards | `build_dashboard` spec |
| 个股估值体检 | `valuation-financial-profile/` | One stock valuation and fundamentals landing page: PE/PB/PCF water level, financial trend, cash-flow quality, and valuation attribution | Bespoke HTML template + `data-kernel.js` |
| 商品多空日报 | `commodity-daily/` | Commodity futures daily page with sector conflict, movers, and sparklines | Bespoke HTML template + `data-kernel.js` |
| 成分股异动榜 | `index-anomaly/` | Index constituent anomaly monitor with gain/loss/turnover/volume/amplitude top-lists, breadth, and index trend | Bespoke HTML template + `data-kernel.js` |
| 市场泡沫水位 | `bubble-watch/` | Multi-market bubble/froth water-level monitor with composite gauge, per-market bias/position bars, and macro backdrop | Bespoke HTML template + `data-kernel.js` |

If no template matches the user's requested page shape, use `../workflows/dashboard-end-to-end.md` for standard panels or `../guides/bespoke-page.md` for custom HTML.

All landing-page templates must use `templates/_shared/share-shell/`. A template may decide its body layout and data explanation, but it must not fork its own QuantBuddy header, footer, body QR block, refresh button, or share-poster modal. Bespoke pages should be compiled with `scripts/compile_bespoke_page.py` before local verification or publishing.

Template rule of thumb: keep data contracts and layout skeleton stable, but leave Agent-editable fields for titles, summaries, interpretation text, risk notes, panel descriptions, and optional panel additions.

Agent flexibility contract:

| Area | Keep stable | Agent may customize |
|---|---|---|
| Data contract | output names, read modes, required formula validation, query/unpack helpers | target asset, date window, optional extra outputs |
| Layout skeleton | page sections, responsive constraints, shared share shell, `getPosterData()`, error/loading states | section order when the user intent clearly asks for it, optional panels/modules |
| Copywriting | no stale placeholder text, no fake conclusions, no exposed signatures | title, subtitle, summary, interpretation, risk note, panel descriptions |
| Visual system | QuantBuddy brand shell, header actions, share poster structure, readable desktop/mobile layout | accent copy, chart emphasis, bespoke page details within the template's visual language |

When adding a new template, add a directory here instead of a loose markdown file. The directory README should answer three questions for the next Agent: when to pick it, what data outputs it needs, and which page regions are intentionally editable.

