# quant-buddy-view

<p align="center">
  <img src="assets/banner-v3.jpg" alt="quant-buddy-view" width="100%" />
</p>

<p align="center">
  <a href="README.md">中文</a> ·
  <a href="README.en.md">English</a> ·
  <a href="#quick-start">Quick Start</a> ·
  <a href="#how-it-works">How It Works</a> ·
  <a href="https://www.quantbuddy.cn">Website</a>
</p>

<p align="center">
  <a href="https://github.com/pseudo-longinus/quant-buddy-view/stargazers"><img alt="GitHub stars" src="https://img.shields.io/github/stars/pseudo-longinus/quant-buddy-view?style=social"></a>
  <a href="https://github.com/pseudo-longinus/quant-buddy-view/blob/main/LICENSE"><img alt="License" src="https://img.shields.io/badge/license-MIT-green"></a>
  <img alt="Python" src="https://img.shields.io/badge/Python-3.8%2B-blue">
  <img alt="Serverless" src="https://img.shields.io/badge/serverless-personalized%20API-0f766e">
  <img alt="Hosting" src="https://img.shields.io/badge/hosting-free-16a34a">
  <img alt="Billing" src="https://img.shields.io/badge/RU-on%20update-orange">
</p>

<p align="center">
  <strong>Turn investment research logic into a self-updating web link.</strong>
</p>

> This project is for financial data analysis, quantitative research, strategy validation and educational use only. It is not investment advice, trading advice, a performance guarantee, or an automated-trading service.

## Real Template Screenshots

These screenshots come directly from the [QuantBuddy Template Market](https://www.quantbuddy.cn/templates). They are not static slide mockups: each template is an openable, reusable page that can fetch live data. Click a screenshot to open the online sample.

<table align="center">
  <tr>
    <td align="center" width="50%">
      <a href="https://pages.quantbuddy.cn/pages/skill_1773824558486_02dfce/page_973ce4a8bff9a7bbd814f11c.html"><img src="assets/templates/template-global-bubble-monitor.jpg" width="100%" alt="Global Asset Bubble Monitor" /></a>
      <br/><sub><b>Global Asset Bubble Monitor</b> · Market · Live 2 formula packages</sub>
    </td>
    <td align="center" width="50%">
      <a href="https://pages.quantbuddy.cn/pages/page_221a3ffae084d983d1b509d4.html"><img src="assets/templates/template-limit-updown-review.jpg" width="100%" alt="A-Share Limit-Up/Down Structure Review" /></a>
      <br/><sub><b>A-Share Limit-Up/Down Structure Review</b> · Market · Live 1 formula package</sub>
    </td>
  </tr>
  <tr>
    <td align="center" width="50%">
      <a href="https://pages.quantbuddy.cn/pages/page_4b488204774ddb45739d39cc.html"><img src="assets/templates/template-star-ai-portfolio.jpg" width="100%" alt="STAR-Market AI Hard-Tech Portfolio" /></a>
      <br/><sub><b>STAR-Market AI Hard-Tech Portfolio</b> · Portfolio · Live 3 formula packages</sub>
    </td>
    <td align="center" width="50%">
      <a href="https://pages.quantbuddy.cn/pages/page_1256a77743fab9aa39838ce9.html"><img src="assets/templates/template-index-futures-basis.jpg" width="100%" alt="Index Futures Basis Monitor" /></a>
      <br/><sub><b>Index Futures Basis Monitor</b> · Market · Live 1 formula package</sub>
    </td>
  </tr>
  <tr>
    <td align="center" width="50%">
      <a href="https://pages.quantbuddy.cn/pages/page_c0c1e05bdad501fbb40641a3.html"><img src="assets/templates/template-rsrs-research.jpg" width="100%" alt="Finding Signal in the Noise · RSRS Research" /></a>
      <br/><sub><b>Finding Signal in the Noise · RSRS Research</b> · Research · Live 1 formula package</sub>
    </td>
    <td align="center" width="50%">
      <a href="https://pages.quantbuddy.cn/pages/page_d4ca42720380d1b5bc3207c0.html"><img src="assets/templates/template-moutai-valuation.jpg" width="100%" alt="Kweichow Moutai · Valuation Check-up" /></a>
      <br/><sub><b>Kweichow Moutai · Valuation Check-up</b> · Asset · Live 1 formula package</sub>
    </td>
  </tr>
</table>

## Quick Start

If this is your first time using quant-buddy-view, start from an official template. The shortest path to success is:

1. Install the `quant-buddy-view` skill.
2. Configure your QuantBuddy API key.
3. Pick a template from the [Template Market](https://www.quantbuddy.cn/templates).
4. Ask your Agent to replace the assets, indicators, copy and formula package.
5. Publish to `pages.quantbuddy.cn` and get a shareable, self-updating web link.

### 1. Install The Skill

Choose the command for the Agent you use:

```bash
# Claude Code
npx skills add pseudo-longinus/quant-buddy-view -g -a claude-code -s quant-buddy-view -y

# Cursor
npx skills add pseudo-longinus/quant-buddy-view -g -a cursor -s quant-buddy-view -y

# OpenClaw
npx skills add pseudo-longinus/quant-buddy-view -g -a openclaw -s quant-buddy-view -y
```

On Windows, if you hit symlink or permission errors, append `--copy`:

```bash
npx skills add pseudo-longinus/quant-buddy-view -g -a claude-code -s quant-buddy-view -y --copy
```

Update for existing users:

```bash
npx skills update quant-buddy-view -g -y
```

Live-data pages also need `quant-buddy-skill` to validate formulas before registration. If your Agent reports that the companion skill is missing, let it install the bundle, or install / refresh the Quant Buddy skills bundle directly:

```bash
npx skills add pseudo-longinus/quant-buddy-skills -g --all
# If already installed and you only need a refresh
npx skills update pseudo-longinus/quant-buddy-skills -y
```

New to Agents and skills? Follow the [step-by-step illustrated tutorial](https://tcn8bvcbyokw.feishu.cn/wiki/E1zswck3oiiJjJkP07QcmSG3nle?from=from_copylink).

### 2. Configure The API Key

Before first use, configure a quant-buddy API key:

1. Sign up and get a key at <https://www.quantbuddy.cn/login>.
2. Recommended: set the environment variable `QUANT_BUDDY_API_KEY`.
3. Or create `skills/quant-buddy-view/config.local.json` under the skill directory and put your local key there.
4. Or, in an Agent that can write local files, send:

```text
Configure my quant-buddy API key: <your API key>
```

> Registering formula packages, uploading pages and updating pages require the API key. Live fetching inside a published dashboard does not require the API key. Do not commit real keys to a public repository.

### 3. Ask The Agent To Publish

After installation and key setup, you can tell your Agent:

```text
Use the "Global Asset Bubble Monitor" template from the QuantBuddy Template Market.
Replace it with the assets and indicators I care about.
Register my own formula package.
Publish it as a shareable, self-updating web dashboard.
```

Or make the request more specific:

```text
Build a valuation check-up dashboard for Kweichow Moutai.
Use the "Kweichow Moutai · Valuation Check-up" template as the page reference.
Register my formulas as a new data interface.
Publish the page and give me the public link.
```

The Agent will use `quant-buddy-skill` to validate quotes, financials, factors or backtest formulas first, then use `quant-buddy-view` to register the Serverless data interface and publish the page.

## How It Works

<p align="center">
  <img src="assets/diagrams/workflow.svg" alt="quant-buddy-view workflow: research question, formula validation, Serverless data interface, hosted web dashboard, live access" width="100%" />
</p>

Key design points:

| Design point | What it means |
|---|---|
| Static page | The published artifact is HTML, so you do not maintain a server, database or scheduler |
| Serverless formula package | Each dashboard has its own formula package and read pattern, customized to your question |
| Live data | The page calls `queryFormulaPackage` on open, so visitors see the latest result after the underlying data updates |
| API key stays out of the frontend | The frontend only uses `signature` to fetch data; the API key is only used for registering, publishing and management |
| Stable share URL | Use `update` to replace the HTML behind the same `page_id`; the public URL stays unchanged |

## Templates And Custom Pages

### Official Template Market

Reusable public templates live in the [QuantBuddy Template Market](https://www.quantbuddy.cn/templates), served by the platform API rather than hard-coded in this repository. Each template lets you:

| Action | Use |
|---|---|
| Preview sample | Check whether the page matches your question |
| Download template HTML | Reuse the page structure and interactions |
| Copy prompt | Hand the template instructions to your Agent |
| Replace formula package | Swap the template author's data source for your own formula package |
| Upload and publish | Generate your own public dashboard page |

### No Bundled Offline Examples

This repository no longer ships offline examples as a page starting point, and legacy demo HTML is not bundled into the skill. Fixed page types should start from the Template Market / online template API: your Agent selects a public live page, downloads the template HTML, validates and registers your own formula package, then replaces the copy and credentials before publishing your own link.

### Custom Pages

Official public templates are the default starting point. If the Template Market does not have a matching page, ask your Agent to build a custom dashboard and publish it with quant-buddy-view as the same kind of shareable, self-updating web link. Custom pages should only own the page body; the header, footer, refresh button and share/poster modal come from `assets/share-shell/`. Advanced notes live in `skills/quant-buddy-view/guides/bespoke-page.md`.

## Page Maintenance

| What you want to do | Command |
|---|---|
| Change a shared page while keeping the same link | `python scripts/static_page.py update '{"page_id":"page_xxx","html_file":"output/pages/new.html"}'` |
| Show the latest values after the underlying data changes | Nothing to do; visitors fetch live data when they open the page |
| Take a page down | `python scripts/static_page.py revoke '{"page_id":"page_xxx"}'` |
| Rotate the formula package signature | `python scripts/formula_package.py refresh '{"package_id":"pkg_xxx","rotate_signature":true}'` |
| Set a page thumbnail | `python scripts/static_page.py thumbnail '{"page_id":"page_xxx","image_file":"cover.png"}'` |

`update` is the common path after a page has been shared: it replaces the HTML behind the same `page_id`, keeps the URL unchanged, and does not consume another active-page slot.

## Runtime

- **Python 3.8+**: the core pipeline for registering, building and publishing uses only the Python standard library; no `pip install` needed.
- **Node.js 18+ (recommended)**: used by `scripts/verify_page.mjs` for pre-publish page verification.
- **Playwright / Chrome / Edge (at least one recommended)**: `verify_page.mjs` tries Playwright first, then falls back to the system Chrome / Edge browser. Use `--require-browser` before publishing; a `static-only` result is not a complete browser verification.

## Billing

quant-buddy-view has a simple billing model: **hosting is free, page visits are free, and RU is only used for server-side compute/update work**.

| Scenario | RU usage |
|---|---|
| A visitor opens a published page | Not billed by PV |
| The page is hosted on `pages.quantbuddy.cn` | Free hosting |
| Downloading template HTML / copying prompts | No RU |
| Registering formula packages, refreshing packages, rotating signatures, or updating data that needs recomputation | RU based on formula count, data volume and compute complexity |

> The product is currently in a limited-time free trial: creating and refreshing dashboards does not consume RU for now. After the free period ends, complex computations will consume RU. Usage is charged to the formula-package owner's quota; visitors open pages with no API key and no setup. Actual usage is subject to the platform account page and API responses.

## Security & Disclaimer

- The quant-buddy API key is only used to call QuantBuddy platform APIs, sent as an HTTP `Authorization` header to declared platform domains. It is not logged or forwarded to third parties.
- When self-hosting, keep the API key server-side. Do not put it in browser code or a public repository. The repo's `config.json` ships with an empty `api_key`; put real keys in `config.local.json` (git-ignored) or an environment variable.
- `signature` is a formula-package capability token and is written into public HTML for live fetching by design. Confirm the page content and public scope before publishing.
- This project is for financial data analysis, quantitative research, strategy validation and educational use only. It is not investment advice, trading advice, a performance guarantee, or an automated-trading service.
- Backtests, screens, factors and historical data do not represent future returns.

## Contact

For more dashboard examples, integration questions, roadmap updates and real research workflows, scan the QR codes below to add WeChat or join the community groups.

<p align="center">
  <table>
    <tr>
      <td align="center">
        <img src="assets/wechat_qr3.png" width="180" alt="Personal WeChat QR" />
        <br/>
        <sub>Personal WeChat</sub>
      </td>
      <td align="center">
        <img src="assets/wechat_group_qr9.jpg" width="180" alt="WeChat group QR" />
        <br/>
        <sub>WeChat group</sub>
      </td>
      <td align="center">
        <img src="assets/feishu_group_qr2.png" width="180" alt="Feishu group QR" />
        <br/>
        <sub>Feishu group</sub>
      </td>
    </tr>
  </table>
  <br/>
  <sub>Scan to discuss quantitative dashboards, AI Agent workflows and strategy validation cases.</sub>
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
